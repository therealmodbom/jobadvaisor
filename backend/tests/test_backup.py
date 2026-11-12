"""The backup of the data repository, against real git and a local bare repository as the remote
(`data-repository` → Backup of the data repository)."""

import subprocess

import pytest
from conftest import git

from jobadvaisor.data.backup import (
    Backup,
    BackupFailed,
    BackupRefused,
    BackupUnavailable,
    commit_message,
)


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


def test_the_fallback_identity_is_used_without_a_repository_identity(backup, backed_up):
    git(backed_up.root, "config", "--unset", "user.name")
    git(backed_up.root, "config", "--unset", "user.email")
    _edit_profile(backed_up.root, "edited by hand")
    backup.run()
    author = git(backed_up.root, "log", "-1", "--format=%an <%ae>").strip()
    assert author == "JobAdvAIsor <jobadvaisor@localhost>"
