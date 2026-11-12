"""`GET /backup` and `POST /backup` over a real git repository and a local bare remote
(`data-repository` → Backup status, Backup of the data repository)."""

import subprocess
import time
from types import SimpleNamespace

import pytest
from conftest import FakeStructuredModel, git
from fastapi.testclient import TestClient

from jobadvaisor.api.app import create_app
from jobadvaisor.data.backup import Backup
from jobadvaisor.intake.postings import Intake
from jobadvaisor.tools.guard import ContentGuard


def _client(root, state) -> SimpleNamespace:
    app = create_app(runs=SimpleNamespace(),
                     intake=Intake(root, FakeStructuredModel(), ContentGuard(None, {})),
                     backup=Backup(root, state), frontend=root / "no-frontend-build")
    return SimpleNamespace(http=TestClient(app, raise_server_exceptions=False))


@pytest.fixture
def api(backed_up, tmp_path) -> SimpleNamespace:
    api = _client(backed_up.root, tmp_path / "state")
    api.root, api.remote = backed_up.root, backed_up.remote
    return api


def _edit(api, summary="edited by hand") -> None:
    (api.root / "profile.json").write_text(f'{{"schema_version": "1", "summary": "{summary}"}}\n')


def _settled(api) -> dict:
    """`GET /backup` once the backup no longer runs."""
    deadline = time.monotonic() + 10
    while (body := api.http.get("/backup").json())["running"]:
        assert time.monotonic() < deadline, "backup never finished"
        time.sleep(0.02)
    return body


def test_a_clean_repository_reports_nothing_pending(api):
    response = api.http.get("/backup")
    assert response.status_code == 200
    assert response.json() == {
        "pending": False, "uncommitted": 0, "unpushed": 0, "branch": "main",
        "remote": "origin/main", "operation": None, "running": False, "progress": None,
        "last_result": None, "last_success": None, "last_failure": None}


def test_a_changed_file_is_pending(api):
    _edit(api)
    body = api.http.get("/backup").json()
    assert (body["pending"], body["uncommitted"]) == (True, 1)


def test_a_commit_the_remote_lacks_is_pending(api):
    _edit(api)
    git(api.root, "commit", "-am", "ahead")
    body = api.http.get("/backup").json()
    assert (body["pending"], body["uncommitted"], body["unpushed"]) == (True, 0, 1)


def test_post_starts_the_backup_at_once_with_running_true(api, tmp_path):
    release = tmp_path / "release"
    hook = api.root / ".git" / "hooks" / "pre-push"
    hook.write_text(f'#!/bin/sh\nwhile [ ! -e "{release}" ]; do sleep 0.02; done\n')
    hook.chmod(0o755)
    _edit(api)
    response = api.http.post("/backup")
    assert response.status_code == 202
    assert response.json()["status"]["running"] is True
    release.write_text("")
    _settled(api)


def test_a_finished_push_is_reported_as_pushed_with_nothing_pending(api):
    _edit(api)
    api.http.post("/backup")
    body = _settled(api)
    assert body["last_result"]["result"] == "pushed"
    assert body["last_result"]["commit"] == git(api.root, "rev-parse", "HEAD").strip()
    assert body["last_success"] is not None
    assert (body["pending"], body["last_failure"], body["progress"]) == (False, None, None)


def test_a_backup_without_a_remote_is_reported_as_committed(api):
    git(api.root, "remote", "remove", "origin")
    _edit(api)
    api.http.post("/backup")
    body = _settled(api)
    assert body["last_result"]["result"] == "committed"
    assert body["remote"] is None


def test_a_backup_with_nothing_to_do_is_reported_as_up_to_date(api):
    api.http.post("/backup")
    assert _settled(api)["last_result"]["result"] == "up_to_date"


def test_a_second_press_while_one_runs_is_409_backup_running(api, tmp_path):
    release = tmp_path / "release"
    hook = api.root / ".git" / "hooks" / "pre-push"
    hook.write_text(f'#!/bin/sh\nwhile [ ! -e "{release}" ]; do sleep 0.02; done\n')
    hook.chmod(0o755)
    _edit(api)
    api.http.post("/backup")
    second = api.http.post("/backup")
    assert second.status_code == 409
    assert second.json()["error"] == "backup running"
    release.write_text("")
    _settled(api)


def test_another_branch_is_409_backup_refused_naming_it(api):
    git(api.root, "checkout", "-b", "other")
    response = api.http.post("/backup")
    assert response.status_code == 409
    assert response.json()["error"] == "backup refused"
    assert "other" in response.json()["detail"]


def test_a_merge_stopped_on_a_conflict_is_409_backup_refused_naming_it(api):
    git(api.root, "checkout", "-b", "other")
    _edit(api, "on other")
    git(api.root, "commit", "-am", "on other")
    git(api.root, "checkout", "main")
    _edit(api, "on main")
    git(api.root, "commit", "-am", "on main")
    subprocess.run(["git", "-C", str(api.root), "merge", "other"], capture_output=True)
    assert api.http.get("/backup").json()["operation"] == "merge"
    response = api.http.post("/backup")
    assert response.status_code == 409
    assert response.json()["error"] == "backup refused"
    assert "merge" in response.json()["detail"]


def test_a_directory_that_is_no_repository_is_409_backup_unavailable(demo_copy, tmp_path):
    api = _client(demo_copy, tmp_path / "state")
    for response in (api.http.get("/backup"), api.http.post("/backup")):
        assert response.status_code == 409
        assert response.json()["error"] == "backup unavailable"
        assert "not a git repository" in response.json()["detail"]


def test_the_default_backup_is_built_over_the_intake_root(demo_copy):
    app = create_app(runs=SimpleNamespace(),
                     intake=Intake(demo_copy, FakeStructuredModel(), ContentGuard(None, {})),
                     frontend=demo_copy / "no-frontend-build")
    response = TestClient(app, raise_server_exceptions=False).get("/backup")
    assert response.json()["error"] == "backup unavailable"  # reached the backup of that root


def test_a_failed_push_shows_in_last_failure_with_git_s_reason(api, tmp_path):
    git(api.root, "remote", "set-url", "origin", str(tmp_path / "missing.git"))
    _edit(api)
    api.http.post("/backup")
    body = _settled(api)
    assert body["last_failure"]["step"] == "push"
    assert "missing.git" in body["last_failure"]["reason"]
    assert body["last_result"] is None
    assert body["pending"] is True  # the commit stays, unpushed
    assert body["unpushed"] == 1


def test_a_failed_commit_shows_in_last_failure_and_keeps_the_changes_pending(api):
    hook = api.root / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho rejected by hook\nexit 1\n")
    hook.chmod(0o755)
    _edit(api)
    api.http.post("/backup")
    body = _settled(api)
    assert body["last_failure"]["step"] == "commit"
    assert "rejected by hook" in body["last_failure"]["reason"]
    assert body["uncommitted"] == 1
