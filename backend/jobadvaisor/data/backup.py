"""Back up the data repository: stage, commit and push what the app and the user changed.

Runs the `git` command (`git -C <root> ...`), never a git library. Every call sets
`GIT_TERMINAL_PROMPT=0`, so git never waits for input; status calls also set
`GIT_OPTIONAL_LOCKS=0`, so a poll never takes `index.lock` while a backup commits.
"""

import json
import logging
import os
import re
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jobadvaisor.data.writer import write_gate

logger = logging.getLogger(__name__)

HISTORY_FILE = "backup.json"

STATUS_TIMEOUT = 30
COMMIT_TIMEOUT = 60
PUSH_TIMEOUT = 60

# Variables that point git at a repository other than the one `-C` names.
GIT_REDIRECTS = {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"}

# The author when the repository has no identity of its own and the machine no global one.
FALLBACK_NAME = "JobAdvAIsor"
FALLBACK_EMAIL = "jobadvaisor@localhost"

# A crashed write leaves `.<name>.tmp` or `.<random>.new`; neither is pending nor committed.
TEMPORARY_EXCLUDES = (":(exclude,glob)**/.*.tmp", ":(exclude,glob)**/.*.new")

# Files in the git directory, and directories, that mark an operation stopped on a conflict.
_OPERATIONS = {"MERGE_HEAD": "merge", "CHERRY_PICK_HEAD": "cherry-pick", "REVERT_HEAD": "revert",
               "rebase-merge": "rebase", "rebase-apply": "rebase"}


# Kind by first path segment, in message order: (directory, singular, plural). Anything else
# counts as "other file".
_KINDS = (("labels", "rating", "ratings"), ("scores", "score", "scores"),
          ("postings", "posting", "postings"),
          ("companies", "company record", "company records"))


def commit_message(paths: list[str]) -> str:
    """The one-line commit message for the staged `paths` (relative to the repository), e.g.
    `Backup: 2 ratings, 12 scores, 1 posting, 1 company record, 1 other file`. Kinds come from
    the first path segment, appear in a fixed order, only with a count, singular for 1."""
    counts = {directory: 0 for directory, _, _ in _KINDS} | {"": 0}
    for path in paths:
        first = path.split("/", 1)[0] if "/" in path else ""
        counts[first if first in counts else ""] += 1
    names = [(counts[directory], one, many) for directory, one, many in _KINDS]
    names.append((counts[""], "other file", "other files"))
    return "Backup: " + ", ".join(f"{n} {one if n == 1 else many}" for n, one, many in names if n)


class BackupUnavailable(Exception):
    """The data directory cannot be backed up (no git, not a repository, not its top level).
    `str(error)` is the reason, shown to the user."""


@dataclass(frozen=True)
class Status:
    """What a backup would do now.

    `uncommitted`: changed or new files, also those changed outside the app, without temporary
    files. `unpushed`: commits the upstream lacks as of the last push or fetch. `branch`: the
    current branch, `None` on a detached HEAD. `remote`: the upstream as `origin/main`, `None`
    without one. `operation`: `merge`, `rebase`, `cherry-pick` or `revert` while one is stopped
    on a conflict, else `None`.
    """

    uncommitted: int
    unpushed: int
    branch: str | None
    remote: str | None
    operation: str | None


@dataclass(frozen=True)
class Result:
    """A finished backup: `result` is `pushed`, `committed` (no upstream, so nothing pushed) or
    `up_to_date`; `commit` is the full SHA of `HEAD` afterwards; `at` the UTC time it
    finished, as in `History`."""

    result: str
    commit: str
    at: str


@dataclass(frozen=True)
class History:
    """What `backup.json` holds: `last_success` as a UTC time (`2026-11-12T13:40:00Z`) and
    `last_failure` as `{at, step, reason}` since then, each `None` when there is none."""

    last_success: str | None
    last_failure: dict[str, str] | None


class BackupRefused(Exception):
    """A backup that must not start: another branch than `main`, or a git operation stopped on
    a conflict. `str(error)` names which; nothing was changed."""


class BackupRunning(Exception):
    """`Backup.start()` while a backup already runs; the second one is refused, not queued."""


class BackupFailed(Exception):
    """A commit or push that did not succeed. `step` is `commit` or `push`, `reason` is git's
    message. A failed commit leaves every change pending; a failed push keeps the commit."""

    def __init__(self, step: str, reason: str):
        super().__init__(f"{step} failed: {reason}")
        self.step = step
        self.reason = reason


class Backup:
    """The backup of the git repository at `root`; `state_path` is the state directory that
    holds `backup.json` (last success and failure)."""

    def __init__(self, root: Path, state_path: Path):
        self.root = root
        self.state_path = state_path
        self.last_result: Result | None = None  # of the last backup `start()` finished
        self._running = threading.Lock()
        self._progress: dict[str, object] = {"step": "staging", "files": 0, "percent": None}

    def run(self) -> Result:
        """Stage and commit what is pending (under the write gate, temporary files excluded),
        then push to the upstream of `main` when there is one, and return when it is done. Never
        forces a push. Raises `BackupRunning` while another backup runs, `BackupUnavailable` and
        `BackupRefused` before changing anything, `BackupFailed` for a commit or push that git
        rejects or any other git call that fails. A finished or failed run is recorded in
        `history()` and `last_result`; a refused one is not."""
        if not self._running.acquire(blocking=False):
            raise BackupRunning("a backup is running")
        try:
            return self._finish()
        finally:
            self._running.release()

    def _finish(self) -> Result:
        """One backup with its record: `last_result` and `history()` follow its outcome."""
        self._reset_progress()
        try:
            result = self._backup()
        except BackupFailed as failure:
            self._fail(failure)
            raise
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            failure = BackupFailed("push" if self._progress["step"] == "pushing" else "commit",
                                   _git_reason(error))
            self._fail(failure)
            raise failure from error
        self.last_result = result
        self._record(last_success=_now(), last_failure=None)
        return result

    def _fail(self, failure: BackupFailed) -> None:
        self.last_result = None
        self._record(last_failure={"at": _now(), "step": failure.step, "reason": failure.reason})

    def history(self) -> History:
        """The time of the last successful backup and the last failure since then, from
        `backup.json` in the state directory. A missing or unreadable file, or a field of the
        wrong shape, reads as `None`: it holds only the display, and the next backup rewrites
        it."""
        try:
            data = json.loads((self.state_path / HISTORY_FILE).read_text())
        except (OSError, ValueError):
            return History(None, None)
        if not isinstance(data, dict):
            return History(None, None)
        success, failure = data.get("last_success"), data.get("last_failure")
        if not isinstance(success, str):
            success = None
        if not (isinstance(failure, dict) and all(
                isinstance(failure.get(key), str) for key in ("at", "step", "reason"))):
            failure = None
        return History(success, failure)

    def _record(self, **changes: object) -> None:
        """Write `changes` into `backup.json`, keeping the other field. A state directory that
        cannot be written loses only the display, so the failure is logged, not raised."""
        history = self.history()
        data = {"last_success": history.last_success, "last_failure": history.last_failure,
                **changes}
        try:
            self.state_path.mkdir(parents=True, exist_ok=True)
            temporary = self.state_path / f".{HISTORY_FILE}.tmp"
            temporary.write_text(json.dumps(data, indent=2) + "\n")
            os.replace(temporary, self.state_path / HISTORY_FILE)
        except OSError:
            logger.warning("cannot write %s", self.state_path / HISTORY_FILE, exc_info=True)

    def _backup(self) -> Result:
        status = self.status()
        _refuse(status)
        committed = self._commit()
        pushed = False
        if status.remote and (committed or status.unpushed):
            self._push()
            pushed = True
        head = self._git("rev-parse", "HEAD").stdout.strip()
        return Result("pushed" if pushed else "committed" if committed else "up_to_date", head,
                      _now())

    def start(self) -> None:
        """Start a backup in a thread and return at once; poll `running`, `progress`,
        `last_result` and `history()` for its course. Raises `BackupRunning` while one runs (it
        is not queued), and `BackupUnavailable` or `BackupRefused` when it could not start, all
        before the thread starts. A failure in the thread lands in `history()`."""
        if not self._running.acquire(blocking=False):
            raise BackupRunning("a backup is running")
        self._reset_progress()  # not the last run's, while the checks below take their time
        try:
            _refuse(self.status())
        except BaseException:
            self._running.release()
            raise
        threading.Thread(target=self._run_in_thread, daemon=True).start()

    @property
    def running(self) -> bool:
        """Whether a backup started with `start()` is still running."""
        return self._running.locked()

    @property
    def progress(self) -> dict[str, object] | None:
        """`{step, files, percent}` while a backup runs, else `None`. `step` is `staging`,
        `committing` or `pushing`; `files` the staged file count; `percent` the push's
        `Writing objects` percentage, `None` until git reports one."""
        return self._progress if self.running else None

    def _run_in_thread(self) -> None:
        try:
            self._finish()
        except BackupFailed:
            pass  # recorded by `_finish`
        except (BackupRefused, BackupUnavailable) as error:  # the state changed since `start()`
            self._fail(BackupFailed("commit", str(error)))
        except Exception as error:  # not a git failure, for instance an unreadable directory
            logger.exception("backup failed unexpectedly")
            self._fail(BackupFailed("push" if self._progress["step"] == "pushing" else "commit",
                                    f"{type(error).__name__}: {error}"))
        finally:
            self._running.release()

    def _reset_progress(self) -> None:
        self._progress = {"step": "staging", "files": 0, "percent": None}

    def _set_progress(self, **changes: object) -> None:
        self._progress = {**self._progress, **changes}

    def _commit(self) -> bool:
        """Stage and commit all pending changes under the write gate; `False` if none."""
        with write_gate:
            self._set_progress(step="staging")
            self._git("add", "-A", "--", ".", *TEMPORARY_EXCLUDES)
            # `add` only skips temporary files; one staged by hand would be committed.
            self._git("reset", "-q", "--", ":(glob)**/.*.tmp", ":(glob)**/.*.new", check=False)
            staged = self._git("diff", "--cached", "--name-only", "-z").stdout
            paths = [path for path in staged.split("\0") if path]
            if not paths:
                return False
            self._set_progress(step="committing", files=len(paths))
            try:
                commit = self._git("commit", "-m", commit_message(paths), check=False,
                                   env=self._identity(), timeout=COMMIT_TIMEOUT)
            except subprocess.TimeoutExpired:
                raise BackupFailed("commit", f"timed out after {COMMIT_TIMEOUT} seconds") \
                    from None
        if commit.returncode != 0:
            raise BackupFailed("commit", _reason(commit))
        return True

    def _identity(self) -> dict[str, str]:
        """The author and committer environment for one commit: empty when git knows a
        `user.name` and `user.email`, else the fallback identity (the container has no
        global git configuration)."""
        if all(self._git("config", key, check=False).returncode == 0
               for key in ("user.name", "user.email")):
            return {}
        return {f"GIT_{role}_{field}": value for role in ("AUTHOR", "COMMITTER")
                for field, value in (("NAME", FALLBACK_NAME), ("EMAIL", FALLBACK_EMAIL))}

    def _push(self) -> None:
        remote = self._git("config", "branch.main.remote").stdout.strip()
        branch = self._git("config", "branch.main.merge").stdout.strip()
        self._set_progress(step="pushing")

        def on_stderr(line: str) -> None:
            percent = push_percent(line)
            if percent is not None:
                self._set_progress(percent=percent)

        try:
            push = self._git("push", "--progress", remote, f"HEAD:{branch}", check=False,
                             timeout=PUSH_TIMEOUT, on_stderr=on_stderr)
        except subprocess.TimeoutExpired:
            raise BackupFailed("push", f"timed out after {PUSH_TIMEOUT} seconds") from None
        if push.returncode != 0:
            raise BackupFailed("push", _reason(push))

    def status(self) -> Status:
        """The current `Status`, without changing anything. Raises `BackupUnavailable` when
        `root` is not the top level of its own git repository, so a commit never lands in an
        enclosing repository."""
        self._require_own_repository()
        porcelain = self._git("status", "--porcelain=v1", "-z", "--no-renames",
                              "--untracked-files=all", "--", ".", *TEMPORARY_EXCLUDES,
                              optional_locks=False).stdout
        branch = self._git("symbolic-ref", "--short", "-q", "HEAD", check=False,
                           optional_locks=False).stdout.strip() or None
        # The upstream comes from the branch's configuration, not from `@{upstream}`, which
        # fails until a remote-tracking ref exists (a first push to an empty remote).
        upstream = self._upstream(branch)
        remote = f"{upstream[0]}/{upstream[1].removeprefix('refs/heads/')}" if upstream else None
        unpushed = 0
        if upstream:
            counted = self._git("rev-list", "--count", "@{upstream}..HEAD", check=False,
                                optional_locks=False)
            if counted.returncode != 0:  # no tracking ref yet: nothing was ever pushed
                counted = self._git("rev-list", "--count", "HEAD", check=False,
                                    optional_locks=False)
            unpushed = int(counted.stdout) if counted.returncode == 0 else 0
        return Status(uncommitted=len([entry for entry in porcelain.split("\0") if entry]),
                      unpushed=unpushed, branch=branch, remote=remote,
                      operation=self._operation())

    def _upstream(self, branch: str | None) -> tuple[str, str] | None:
        """The remote name and the merge ref (`refs/heads/main`) `branch` is configured to push
        to, or `None` for a detached HEAD or a branch without both settings."""
        if branch is None:
            return None
        values = [self._git("config", f"branch.{branch}.{key}", check=False,
                            optional_locks=False) for key in ("remote", "merge")]
        if any(value.returncode != 0 or not value.stdout.strip() for value in values):
            return None
        return values[0].stdout.strip(), values[1].stdout.strip()

    def _require_own_repository(self) -> None:
        try:
            top = self._git("rev-parse", "--show-toplevel", check=False, optional_locks=False)
        except FileNotFoundError:
            raise BackupUnavailable("git is not installed") from None
        if top.returncode != 0:
            raise BackupUnavailable(f"{self.root} is not a git repository")
        if Path(top.stdout.strip()).resolve() != self.root.resolve():
            raise BackupUnavailable(f"{self.root} is not the top level of its git repository")

    def _operation(self) -> str | None:
        git_dir = Path(self._git("rev-parse", "--absolute-git-dir",
                                 optional_locks=False).stdout.strip())
        for name, operation in _OPERATIONS.items():
            if (git_dir / name).exists():
                return operation
        return None

    def _git(self, *args: str, check: bool = True, optional_locks: bool = True,
             timeout: float = STATUS_TIMEOUT, env: dict[str, str] | None = None,
             on_stderr: Callable[[str], None] | None = None,
             ) -> subprocess.CompletedProcess[str]:
        """Run `git -C root args`. `on_stderr` gets each stderr line while git runs (a `\\r`
        counts as a line end, so progress updates arrive one by one). Raises
        `subprocess.TimeoutExpired` after `timeout` seconds, having killed git and its
        children, and `subprocess.CalledProcessError` for a failure when `check` is set."""
        # `-C root` must decide the repository: a GIT_DIR of the process (the tests run from a
        # git hook, for instance) would send the backup to another repository.
        environment = {name: value for name, value in os.environ.items()
                       if name not in GIT_REDIRECTS}
        environment |= {"GIT_TERMINAL_PROMPT": "0", **(env or {})}
        if not optional_locks:
            environment["GIT_OPTIONAL_LOCKS"] = "0"
        command = ["git", "-C", str(self.root), *args]
        # Own process group: on a timeout the kill reaches ssh and hooks too, which would
        # otherwise keep the output pipes open and block the caller past the timeout.
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              env=environment, start_new_session=True) as process:
            try:
                stdout, stderr = _communicate(process, timeout, on_stderr)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                raise
        if check and process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, command, stdout, stderr)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _refuse(status: Status) -> None:
    """Raise `BackupRefused` for a git operation stopped on a conflict or a branch other than
    `main`."""
    if status.operation:
        raise BackupRefused(f"a {status.operation} is in progress")
    if status.branch != "main":
        raise BackupRefused(f"on branch {status.branch}" if status.branch
                            else "on a detached HEAD")


def _communicate(process: subprocess.Popen[str], timeout: float,
                 on_stderr: Callable[[str], None] | None) -> tuple[str, str]:
    """`process.communicate(timeout=timeout)`, handing stderr lines to `on_stderr` as they
    arrive when it is given. Raises `subprocess.TimeoutExpired` (the caller kills the group)."""
    if on_stderr is None:
        return process.communicate(timeout=timeout)
    streams: dict[str, list[str]] = {"out": [], "err": []}

    def pump(stream, name: str) -> None:
        for line in stream:
            streams[name].append(line)
            if name == "err":
                on_stderr(line)

    readers = [threading.Thread(target=pump, args=(process.stdout, "out"), daemon=True),
               threading.Thread(target=pump, args=(process.stderr, "err"), daemon=True)]
    for reader in readers:
        reader.start()
    deadline = time.monotonic() + timeout
    process.wait(timeout=timeout)
    for reader in readers:
        reader.join(max(0.0, deadline - time.monotonic()))
    if any(reader.is_alive() for reader in readers):
        # A child (a hook, an ssh master) outlives git and still holds its output open.
        raise subprocess.TimeoutExpired(process.args, timeout)
    return "".join(streams["out"]), "".join(streams["err"])


def push_percent(output: str) -> int | None:
    """The last `Writing objects:  60% (12/20)` percentage in git's push `output` (updates are
    separated by `\\r` or newlines), or `None` when it has none, as for a push too small to
    print progress."""
    found = re.findall(r"Writing objects:\s+(\d+)%", output)
    return int(found[-1]) if found else None


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_reason(error: subprocess.CalledProcessError | subprocess.TimeoutExpired) -> str:
    """The reason of a git call that raised: git's own output, or the time it ran out of."""
    if isinstance(error, subprocess.TimeoutExpired):
        return f"timed out after {error.timeout:g} seconds"
    return (str(error.stderr or "") + str(error.stdout or "")).strip() \
        or f"git exited with {error.returncode}"


def _reason(process: subprocess.CompletedProcess[str]) -> str:
    """Git's message for a failed command: its output, whichever stream a hook or git used."""
    return (process.stderr + process.stdout).strip() or f"git exited with {process.returncode}"
