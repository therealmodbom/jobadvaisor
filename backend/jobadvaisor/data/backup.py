"""Back up the data repository: stage, commit and push what the app and the user changed.

Runs the `git` command (`git -C <root> ...`), never a git library. Every call sets
`GIT_TERMINAL_PROMPT=0`, so git never waits for input; status calls also set
`GIT_OPTIONAL_LOCKS=0`, so a poll never takes `index.lock` while a backup commits.
"""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from jobadvaisor.data.writer import write_gate

STATUS_TIMEOUT = 30
COMMIT_TIMEOUT = 60
PUSH_TIMEOUT = 60

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
    `up_to_date`; `commit` is the full SHA of `HEAD` afterwards."""

    result: str
    commit: str


class BackupRefused(Exception):
    """A backup that must not start: another branch than `main`, or a git operation stopped on
    a conflict. `str(error)` names which; nothing was changed."""


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

    def run(self) -> Result:
        """Stage and commit what is pending (under the write gate, temporary files excluded),
        then push to the upstream of `main` when there is one. Never forces a push. Raises
        `BackupUnavailable` and `BackupRefused` before changing anything, `BackupFailed` for a
        commit or push that git rejects."""
        status = self.status()
        if status.operation:
            raise BackupRefused(f"a {status.operation} is in progress")
        if status.branch != "main":
            raise BackupRefused(f"on branch {status.branch}" if status.branch
                                else "on a detached HEAD")
        committed = self._commit()
        pushed = False
        if status.remote and (committed or status.unpushed):
            self._push()
            pushed = True
        head = self._git("rev-parse", "HEAD").stdout.strip()
        return Result("pushed" if pushed else "committed" if committed else "up_to_date", head)

    def _commit(self) -> bool:
        """Stage and commit all pending changes under the write gate; `False` if none."""
        with write_gate:
            self._git("add", "-A", "--", ".", *TEMPORARY_EXCLUDES)
            # `add` only skips temporary files; one staged by hand would be committed.
            self._git("reset", "-q", "--", ":(glob)**/.*.tmp", ":(glob)**/.*.new", check=False)
            staged = self._git("diff", "--cached", "--name-only", "-z").stdout
            paths = [path for path in staged.split("\0") if path]
            if not paths:
                return False
            commit = self._git("commit", "-m", commit_message(paths), check=False,
                               env=self._identity(), timeout=COMMIT_TIMEOUT)
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
        push = self._git("push", "--progress", remote, f"HEAD:{branch}", check=False,
                         timeout=PUSH_TIMEOUT)
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
        upstream = self._git("rev-parse", "--abbrev-ref", "@{upstream}", check=False,
                             optional_locks=False)
        remote = upstream.stdout.strip() if upstream.returncode == 0 else None
        unpushed = 0
        if remote:
            unpushed = int(self._git("rev-list", "--count", "@{upstream}..HEAD",
                                     optional_locks=False).stdout)
        branch = self._git("symbolic-ref", "--short", "-q", "HEAD", check=False,
                           optional_locks=False).stdout.strip() or None
        return Status(uncommitted=len([entry for entry in porcelain.split("\0") if entry]),
                      unpushed=unpushed, branch=branch, remote=remote,
                      operation=self._operation())

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
             timeout: float = STATUS_TIMEOUT,
             env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0", **(env or {})}
        if not optional_locks:
            environment["GIT_OPTIONAL_LOCKS"] = "0"
        return subprocess.run(["git", "-C", str(self.root), *args], capture_output=True,
                              text=True, check=check, timeout=timeout, env=environment)


def _reason(process: subprocess.CompletedProcess[str]) -> str:
    """Git's message for a failed command: its output, whichever stream a hook or git used."""
    return (process.stderr + process.stdout).strip() or f"git exited with {process.returncode}"
