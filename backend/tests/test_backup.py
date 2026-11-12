"""The backup of the data repository, against real git and a local bare repository as the remote
(`data-repository` → Backup of the data repository)."""

import itertools
import re
import subprocess
import threading
import time
from datetime import UTC, datetime

import pytest
from conftest import git

from jobadvaisor.data.backup import (
    Backup,
    BackupFailed,
    BackupRefused,
    BackupRunning,
    BackupUnavailable,
    History,
    commit_message,
    push_percent,
)
from jobadvaisor.data.models import Label, Score
from jobadvaisor.data.writer import write_gate, write_label, write_score


@pytest.fixture
def backup(backed_up, tmp_path) -> Backup:
    return Backup(backed_up.root, tmp_path / "state")


def _edit_profile(root, summary: str) -> None:
    (root / "profile.json").write_text(f'{{"schema_version": "1", "summary": "{summary}"}}\n')


def _commit_edit(root, summary: str) -> None:
    _edit_profile(root, summary)
    git(root, "commit", "-am", summary)


def _diverge(root) -> None:
    """Leave `main` and a branch `other` with different edits of `profile.json`."""
    git(root, "checkout", "-b", "other")
    _commit_edit(root, "on other")
    git(root, "checkout", "main")
    _commit_edit(root, "on main")


def test_a_clean_repository_has_nothing_pending(backup):
    status = backup.status()
    assert (status.uncommitted, status.unpushed) == (0, 0)
    assert (status.branch, status.remote, status.operation) == ("main", "origin/main", None)


def test_a_hand_edited_file_is_uncommitted(backup, backed_up):
    _edit_profile(backed_up.root, "edited by hand")
    assert backup.status().uncommitted == 1


def test_an_untracked_new_posting_is_uncommitted(backup, backed_up):
    (backed_up.root / "postings" / "new-posting.json").write_text("{}\n")
    assert backup.status().uncommitted == 1


def test_a_leftover_temporary_file_is_not_pending(backup, backed_up):
    (backed_up.root / ".pool.json.tmp").write_text("{}")
    (backed_up.root / "postings" / ".abc123.new").write_text("{}")
    assert backup.status().uncommitted == 0


def test_a_commit_ahead_of_the_upstream_is_unpushed(backup, backed_up):
    _commit_edit(backed_up.root, "ahead")
    status = backup.status()
    assert (status.uncommitted, status.unpushed) == (0, 1)


def test_without_a_remote_there_is_no_upstream_and_nothing_unpushed(backup, backed_up):
    git(backed_up.root, "remote", "remove", "origin")
    status = backup.status()
    assert (status.remote, status.unpushed) == (None, 0)


def test_another_branch_is_named(backup, backed_up):
    git(backed_up.root, "checkout", "-b", "other")
    assert backup.status().branch == "other"


def test_a_merge_stopped_on_a_conflict_is_an_operation(backup, backed_up):
    _diverge(backed_up.root)
    merge = subprocess.run(["git", "-C", str(backed_up.root), "merge", "other"],
                           capture_output=True)
    assert merge.returncode != 0
    assert backup.status().operation == "merge"


def test_a_rebase_stopped_on_a_conflict_is_an_operation_on_a_detached_head(backup, backed_up):
    _diverge(backed_up.root)
    git(backed_up.root, "checkout", "other")
    rebase = subprocess.run(["git", "-C", str(backed_up.root), "rebase", "main"],
                            capture_output=True)
    assert rebase.returncode != 0
    status = backup.status()
    assert (status.branch, status.operation) == (None, "rebase")


def test_a_plain_directory_is_unavailable(demo_copy, tmp_path):
    with pytest.raises(BackupUnavailable, match="not a git repository"):
        Backup(demo_copy, tmp_path / "state").status()


def test_a_subdirectory_of_another_repository_is_unavailable(backed_up, tmp_path):
    with pytest.raises(BackupUnavailable, match="not the top level"):
        Backup(backed_up.root / "labels", tmp_path / "state").status()


def test_message_for_three_ratings_and_a_posting_names_nothing_else():
    paths = ["labels/a.json", "labels/b.json", "labels/c.json", "postings/new.json"]
    assert commit_message(paths) == "Backup: 3 ratings, 1 posting"


def test_message_names_every_kind_in_a_fixed_order_with_singular_for_one():
    paths = ["README.md", "companies/acme.json", "postings/p.json", "scores/s.json",
             "labels/l.json"]
    assert commit_message(paths) == ("Backup: 1 rating, 1 score, 1 posting, 1 company record, "
                                     "1 other file")


def test_message_counts_plural_and_sorts_other_paths_into_other_files():
    paths = [f"scores/s{n}.json" for n in range(12)] + ["pool.json", "profile.json"]
    assert commit_message(paths) == "Backup: 12 scores, 2 other files"


def test_message_for_a_path_below_a_known_directory_counts_that_kind():
    assert commit_message(["labels/deep/x.json"]) == "Backup: 1 rating"


def _remote_subject(remote) -> str:
    return git(remote, "log", "-1", "--format=%s", "main").strip()


def test_pending_changes_are_committed_and_pushed(backup, backed_up):
    _edit_profile(backed_up.root, "edited by hand")
    result = backup.run()
    assert result.result == "pushed"
    assert result.commit == git(backed_up.root, "rev-parse", "HEAD").strip()
    assert _remote_subject(backed_up.remote) == "Backup: 1 other file"
    assert git(backed_up.remote, "rev-parse", "main") == git(backed_up.root, "rev-parse", "HEAD")
    status = backup.status()
    assert (status.uncommitted, status.unpushed) == (0, 0)


def test_an_unpushed_commit_is_pushed_when_nothing_is_pending(backup, backed_up):
    _commit_edit(backed_up.root, "ahead")
    assert backup.run().result == "pushed"
    assert _remote_subject(backed_up.remote) == "ahead"


def test_nothing_to_do_is_up_to_date_and_adds_no_commit(backup, backed_up):
    head = git(backed_up.root, "rev-parse", "HEAD")
    assert backup.run().result == "up_to_date"
    assert git(backed_up.root, "rev-parse", "HEAD") == head


def test_without_an_upstream_the_backup_commits_only_and_adds_no_remote(backup, backed_up):
    git(backed_up.root, "remote", "remove", "origin")
    _edit_profile(backed_up.root, "no remote")
    assert backup.run().result == "committed"
    assert git(backed_up.root, "log", "-1", "--format=%s").strip() == "Backup: 1 other file"
    assert git(backed_up.root, "remote") == ""


def test_another_branch_is_refused_and_changes_nothing(backup, backed_up):
    git(backed_up.root, "checkout", "-b", "other")
    _edit_profile(backed_up.root, "on other")
    head = git(backed_up.root, "rev-parse", "HEAD")
    with pytest.raises(BackupRefused, match="other"):
        backup.run()
    assert git(backed_up.root, "rev-parse", "HEAD") == head
    assert backup.status().uncommitted == 1


def test_a_merge_stopped_on_a_conflict_is_refused_naming_the_operation(backup, backed_up):
    _diverge(backed_up.root)
    subprocess.run(["git", "-C", str(backed_up.root), "merge", "other"], capture_output=True)
    head = git(backed_up.root, "rev-parse", "HEAD")
    with pytest.raises(BackupRefused, match="merge"):
        backup.run()
    assert git(backed_up.root, "rev-parse", "HEAD") == head


def test_a_subdirectory_of_another_repository_commits_nothing_there(backed_up, tmp_path):
    _edit_profile(backed_up.root, "edited by hand")
    head = git(backed_up.root, "rev-parse", "HEAD")
    with pytest.raises(BackupUnavailable):
        Backup(backed_up.root / "labels", tmp_path / "state").run()
    assert git(backed_up.root, "rev-parse", "HEAD") == head


def test_a_temporary_file_staged_by_hand_is_not_committed(backup, backed_up):
    (backed_up.root / ".pool.json.tmp").write_text("{}")
    git(backed_up.root, "add", "-f", ".pool.json.tmp")
    _edit_profile(backed_up.root, "edited by hand")
    backup.run()
    assert ".pool.json.tmp" not in git(backed_up.root, "ls-tree", "-r", "--name-only", "HEAD")
    assert ".pool.json.tmp" not in git(backed_up.remote, "ls-tree", "-r", "--name-only", "main")
    assert backup.status().uncommitted == 0


def test_a_rejected_commit_keeps_every_change_pending(backup, backed_up):
    hook = backed_up.root / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho rejected by hook\nexit 1\n")
    hook.chmod(0o755)
    _edit_profile(backed_up.root, "edited by hand")
    with pytest.raises(BackupFailed, match="commit failed") as failure:
        backup.run()
    assert failure.value.step == "commit"
    assert "rejected by hook" in failure.value.reason
    assert backup.status().uncommitted == 1


def test_an_unreachable_remote_keeps_the_commit_and_a_later_backup_pushes(
        backup, backed_up, tmp_path):
    git(backed_up.root, "remote", "set-url", "origin", str(tmp_path / "missing.git"))
    _edit_profile(backed_up.root, "while offline")
    with pytest.raises(BackupFailed) as failure:
        backup.run()
    assert failure.value.step == "push"
    assert "missing.git" in failure.value.reason
    assert git(backed_up.root, "log", "-1", "--format=%s").strip() == "Backup: 1 other file"
    assert backup.status().unpushed == 1
    git(backed_up.root, "remote", "set-url", "origin", str(backed_up.remote))
    assert backup.run().result == "pushed"
    assert _remote_subject(backed_up.remote) == "Backup: 1 other file"


def test_a_rejected_push_keeps_the_commit_and_leaves_the_remote_alone(
        backup, backed_up, tmp_path):
    other = tmp_path / "other-clone"
    git(tmp_path, "clone", str(backed_up.remote), str(other))
    git(other, "config", "user.name", "Other")
    git(other, "config", "user.email", "other@example.com")
    _commit_edit(other, "pushed first")
    git(other, "push", "origin", "main")
    remote_head = git(backed_up.remote, "rev-parse", "main")
    _edit_profile(backed_up.root, "pushed second")
    with pytest.raises(BackupFailed) as failure:
        backup.run()
    assert failure.value.step == "push"
    assert "rejected" in failure.value.reason
    assert git(backed_up.remote, "rev-parse", "main") == remote_head
    assert git(backed_up.root, "log", "-1", "--format=%s").strip() == "Backup: 1 other file"


def test_a_push_that_exceeds_the_timeout_counts_as_failed(
        backup, backed_up, tmp_path, monkeypatch):
    fake_ssh = tmp_path / "slow-ssh"
    fake_ssh.write_text("#!/bin/sh\nsleep 5\n")
    fake_ssh.chmod(0o755)
    monkeypatch.setenv("GIT_SSH_COMMAND", str(fake_ssh))
    monkeypatch.setattr("jobadvaisor.data.backup.PUSH_TIMEOUT", 1)
    git(backed_up.root, "remote", "set-url", "origin", "ssh://localhost/data.git")
    _edit_profile(backed_up.root, "slow remote")
    started = time.monotonic()
    with pytest.raises(BackupFailed, match="timed out") as failure:
        backup.run()
    assert failure.value.step == "push"
    assert time.monotonic() - started < 4  # the timeout cuts the push off, ssh included


def test_without_a_backup_there_is_no_history(backup):
    assert backup.history() == History(last_success=None, last_failure=None)


def test_a_successful_backup_is_recorded_in_the_state_directory(backup, backed_up, tmp_path):
    _edit_profile(backed_up.root, "edited by hand")
    backup.run()
    history = backup.history()
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", history.last_success)
    assert history.last_failure is None
    assert (tmp_path / "state" / "backup.json").is_file()
    assert Backup(backed_up.root, tmp_path / "state").history() == history  # read from the file


def test_a_failed_push_is_recorded_beside_the_earlier_success(backup, backed_up, tmp_path):
    _edit_profile(backed_up.root, "first")
    backup.run()
    success = backup.history().last_success
    git(backed_up.root, "remote", "set-url", "origin", str(tmp_path / "missing.git"))
    _edit_profile(backed_up.root, "second")
    with pytest.raises(BackupFailed):
        backup.run()
    history = backup.history()
    assert history.last_success == success
    assert history.last_failure["step"] == "push"
    assert "missing.git" in history.last_failure["reason"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", history.last_failure["at"])


def test_a_failed_commit_is_recorded_with_its_step(backup, backed_up):
    hook = backed_up.root / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho rejected by hook\nexit 1\n")
    hook.chmod(0o755)
    _edit_profile(backed_up.root, "edited by hand")
    with pytest.raises(BackupFailed):
        backup.run()
    assert backup.history().last_failure["step"] == "commit"


def test_a_success_clears_the_failure(backup, backed_up, tmp_path):
    git(backed_up.root, "remote", "set-url", "origin", str(tmp_path / "missing.git"))
    _edit_profile(backed_up.root, "while offline")
    with pytest.raises(BackupFailed):
        backup.run()
    git(backed_up.root, "remote", "set-url", "origin", str(backed_up.remote))
    backup.run()
    history = backup.history()
    assert history.last_failure is None
    assert history.last_success is not None


def test_a_refused_backup_is_not_recorded(backup, backed_up):
    git(backed_up.root, "checkout", "-b", "other")
    with pytest.raises(BackupRefused):
        backup.run()
    assert backup.history() == History(last_success=None, last_failure=None)


@pytest.mark.parametrize("content", ["not json", "[1, 2]", '{"last_success": 5}'])
def test_an_unreadable_history_file_reads_as_none(backup, tmp_path, content):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "backup.json").write_text(content)
    assert backup.history() == History(last_success=None, last_failure=None)


def _wait_until(condition, seconds: float = 10.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "timed out waiting for the condition"
        time.sleep(0.02)


def _hold_pushes(root, release) -> None:
    """A `pre-push` hook that blocks until the file `release` exists."""
    hook = root / ".git" / "hooks" / "pre-push"
    hook.write_text(f'#!/bin/sh\nwhile [ ! -e "{release}" ]; do sleep 0.02; done\n')
    hook.chmod(0o755)


def test_a_second_backup_while_one_runs_is_refused_and_progress_shows_the_push(
        backup, backed_up, tmp_path):
    release = tmp_path / "release"
    _hold_pushes(backed_up.root, release)
    _edit_profile(backed_up.root, "edited by hand")
    (backed_up.root / "postings" / "new.json").write_text("{}\n")
    backup.start()
    _wait_until(lambda: backup.progress and backup.progress["step"] == "pushing")
    assert backup.running
    assert backup.progress["files"] == 2
    with pytest.raises(BackupRunning):
        backup.start()
    release.write_text("")
    _wait_until(lambda: not backup.running)
    assert backup.progress is None
    assert backup.last_result.result == "pushed"
    assert backup.last_result.commit == git(backed_up.root, "rev-parse", "HEAD").strip()
    assert _remote_subject(backed_up.remote) == "Backup: 1 posting, 1 other file"


def test_a_refusal_is_raised_before_the_thread_starts(backup, backed_up):
    git(backed_up.root, "checkout", "-b", "other")
    with pytest.raises(BackupRefused):
        backup.start()
    assert not backup.running


def test_a_failure_in_the_thread_is_recorded_and_the_next_backup_may_start(
        backup, backed_up, tmp_path):
    git(backed_up.root, "remote", "set-url", "origin", str(tmp_path / "missing.git"))
    _edit_profile(backed_up.root, "while offline")
    backup.start()
    _wait_until(lambda: not backup.running)
    assert backup.history().last_failure["step"] == "push"
    assert backup.last_result is None
    backup.start()  # not refused as running
    _wait_until(lambda: not backup.running)


@pytest.mark.parametrize("output, percent", [
    ("Writing objects:   2% (1/42)", 2),
    ("Counting objects: 100% (5/5), done.\rWriting objects:  60% (12/20)\r"
     "Writing objects:  65% (13/20)", 65),
    ("Writing objects: 100% (3/3), 300 bytes | 300.00 KiB/s, done.\n", 100),
    ("Everything up-to-date\n", None),
    ("", None),
])
def test_the_push_percentage_comes_from_the_writing_objects_lines(output, percent):
    assert push_percent(output) == percent


def _rating(note: str) -> Label:
    return Label(schema_version="1", kind="rating", verdict="positive", note=note,
                 rated_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC))


def _score(value: int) -> Score:
    return Score(schema_version="1", score=value, reasoning="Fits.",
                 scored_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC))


def test_writes_during_repeated_backups_are_never_half_committed_or_lost(backup, backed_up):
    stop = threading.Event()
    last_note: dict[str, str] = {}
    errors: list[BaseException] = []

    def write_ratings():
        try:
            for n in itertools.count():
                if stop.is_set():
                    return
                write_label(backed_up.root, "demo-001", _rating(f"rating {n}"))
                last_note["demo-001"] = f"rating {n}"
        except BaseException as error:  # noqa: BLE001 - surfaced by the assertion below
            errors.append(error)

    def write_scores():
        try:
            for n in itertools.count():
                if stop.is_set():
                    return
                write_score(backed_up.root, "demo-002", _score(n % 10 + 1))
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    writers = [threading.Thread(target=write_ratings), threading.Thread(target=write_scores)]
    for writer_thread in writers:
        writer_thread.start()
    for _ in range(8):
        backup.run()
    stop.set()
    for writer_thread in writers:
        writer_thread.join(timeout=10)
    assert not errors
    backup.run()  # whatever the last writes left pending

    commits = git(backed_up.root, "rev-list", "--reverse", "HEAD").split()
    assert len(commits) > 2, "the backups committed nothing while the writers ran"
    checked = 0
    for commit in commits:
        changed = git(backed_up.root, "diff-tree", "-r", "--root", "--no-commit-id",
                      "--name-only", commit).split()
        for path in changed:
            blob = git(backed_up.root, "show", f"{commit}:{path}")
            if path.startswith("labels/"):
                Label.model_validate_json(blob, strict=True)
                checked += 1
            elif path.startswith("scores/"):
                Score.model_validate_json(blob, strict=True)
                checked += 1
    assert checked > 0
    final = git(backed_up.root, "show", "HEAD:labels/demo-001.json")
    assert last_note["demo-001"] in final  # the last rating written is in a commit
    assert backup.status().uncommitted == 0


def test_a_backup_waits_for_a_write_in_progress_before_it_stages(backup, backed_up):
    _edit_profile(backed_up.root, "edited by hand")
    with write_gate:  # a write is in progress
        backup.start()
        time.sleep(0.5)
        assert backup.running
        assert backup.progress["files"] == 0  # not past staging
        assert git(backed_up.root, "diff", "--cached", "--name-only") == ""  # nothing staged
    _wait_until(lambda: not backup.running)
    assert backup.last_result.result == "pushed"


def test_a_write_waits_while_the_backup_commits_and_runs_afterwards(
        backup, backed_up, tmp_path):
    release = tmp_path / "release"
    hook = backed_up.root / ".git" / "hooks" / "pre-commit"
    hook.write_text(f'#!/bin/sh\nwhile [ ! -e "{release}" ]; do sleep 0.02; done\n')
    hook.chmod(0o755)
    _edit_profile(backed_up.root, "edited by hand")
    backup.start()
    _wait_until(lambda: backup.progress and backup.progress["step"] == "committing")
    written = threading.Event()

    def rate():
        write_label(backed_up.root, "demo-001", _rating("during the commit"))
        written.set()

    threading.Thread(target=rate).start()
    assert not written.wait(0.5), "the write ran while the backup was committing"
    release.write_text("")
    assert written.wait(10)
    _wait_until(lambda: not backup.running)
    # The rating missed the commit and is pending, not lost.
    assert "during the commit" not in git(backed_up.remote, "show", "main:labels/demo-001.json")
    assert "during the commit" in (backed_up.root / "labels" / "demo-001.json").read_text()
    assert backup.status().uncommitted == 1


def test_a_rating_during_a_slow_push_is_stored_at_once_and_stays_pending(
        backup, backed_up, tmp_path):
    release = tmp_path / "release"
    _hold_pushes(backed_up.root, release)
    _edit_profile(backed_up.root, "edited by hand")
    backup.start()
    _wait_until(lambda: backup.progress and backup.progress["step"] == "pushing")
    started = time.monotonic()
    write_label(backed_up.root, "demo-001", _rating("during the push"))
    assert time.monotonic() - started < 1
    release.write_text("")
    _wait_until(lambda: not backup.running)
    assert "during the push" not in git(backed_up.remote, "show", "main:labels/demo-001.json")
    assert backup.status().uncommitted == 1  # shows as pending


def test_the_fallback_identity_is_used_without_a_repository_identity(backup, backed_up):
    git(backed_up.root, "config", "--unset", "user.name")
    git(backed_up.root, "config", "--unset", "user.email")
    _edit_profile(backed_up.root, "edited by hand")
    backup.run()
    author = git(backed_up.root, "log", "-1", "--format=%an <%ae>").strip()
    assert author == "JobAdvAIsor <jobadvaisor@localhost>"
