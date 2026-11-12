"""Browser walkthrough of the backup: rate a posting, the button is highlighted, press it, the
button is quiet again and the bare remote holds the rating; then the remote goes away, the press
fails, the failure shows its toggle and the app keeps working, and a press after the remote is back
succeeds. Real app (`create_app` served by uvicorn) over a copy of the demo persona made a git
repository with a local bare remote, the built frontend in Chromium. The tests share one server and
run in order; run them as a set: `pytest -m e2e` after `npm --prefix frontend run build`."""

import shutil
import threading
import time

import pytest
import uvicorn
from conftest import ScriptedModel, ToolScriptModel, git
from playwright.sync_api import expect, sync_playwright
from test_triage_graph import Harness

from jobadvaisor.api.app import create_app
from jobadvaisor.data.backup import Backup
from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.intake.postings import Intake
from jobadvaisor.settings import REPOSITORY_ROOT
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.triage.runs import Runs

pytestmark = pytest.mark.e2e

FRONTEND = REPOSITORY_ROOT / "frontend/dist"
POSTING = "demo-010"  # a posting of the demo persona without a rating
TITLE = "Mobile QA Engineer"


@pytest.fixture(scope="module")
def repository(tmp_path_factory):
    """The demo persona as a git repository on `main` with a local bare repository `remote` as its
    upstream, with no global git configuration (identity, hooks) in the way. Has `root`, `remote`
    and `moved`, where the remote is put to make a push fail."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
        patch.setenv("GIT_CONFIG_NOSYSTEM", "1")
        base = tmp_path_factory.mktemp("e2e-backup")
        root, remote = base / "data", base / "remote.git"
        shutil.copytree(FIXTURE_DIRECTORY, root)
        git(base, "init", "--bare", "-b", "main", str(remote))
        git(root, "init", "-b", "main")
        git(root, "config", "user.name", "Test")
        git(root, "config", "user.email", "test@example.com")
        git(root, "add", "-A")
        git(root, "commit", "-m", "Initial data")
        git(root, "remote", "add", "origin", str(remote))
        git(root, "push", "-u", "origin", "main")
        yield type("Repository", (), {"root": root, "remote": remote, "moved": base / "away.git"})


@pytest.fixture(scope="module")
def app_url(repository, tmp_path_factory):
    """Base URL of the real app on a free localhost port; fails with a build hint when
    `frontend/dist` is missing and stops the server afterwards."""
    if not (FRONTEND / "index.html").is_file():
        pytest.fail("frontend/dist is missing: run `npm --prefix frontend run build` first")
    harness = Harness(tmp_path_factory.mktemp("e2e-backup-state"), repository.root)
    app = create_app(
        Runs(harness.graph, harness.context),
        Intake(repository.root, ScriptedModel(lambda schema, prompt: {}), ContentGuard(None, {}),
               loop_model=ToolScriptModel(plan=[])),
        agent=lambda messages: pytest.fail("the walkthrough never chats"),
        backup=Backup(repository.root, tmp_path_factory.mktemp("e2e-backup-history")),
        frontend=FRONTEND)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "the app did not start"
    yield f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"
    server.should_exit = True
    thread.join(10)


@pytest.fixture(scope="module")
def page(app_url):
    """One Chromium page for the whole walkthrough; default timeout 10 s."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_default_timeout(10_000)
        yield page
        browser.close()


def rate_positive(page):
    """Rate the posting "Ja, auf jeden Fall" on its page."""
    page.get_by_role("button", name=f"Ja, auf jeden Fall: {TITLE}").click()


def test_a_rating_highlights_the_button_and_a_press_pushes_it(page, app_url, repository):
    page.goto(f"{app_url}/#/anzeigen/{POSTING}")
    quiet = page.get_by_role("button", name="Gesichert – jetzt erneut sichern")
    expect(quiet).to_be_visible()
    rate_positive(page)
    pending = page.get_by_role("button", name="Sichern (1)")
    expect(pending).to_be_visible()
    pending.click()
    expect(quiet).to_be_visible()
    expect(page.get_by_text("Gepusht, gerade eben")).to_be_visible()
    rating = git(repository.remote, "show", f"main:labels/{POSTING}.json")
    assert '"verdict": "positive"' in rating


def test_a_failed_push_shows_the_failure_and_the_app_keeps_working(page, app_url, repository):
    repository.remote.rename(repository.moved)  # the remote is gone
    page.get_by_role("button", name=f"Nein, eher nicht: {TITLE}").click()
    page.get_by_role("button", name="Sichern (1)").click()
    toggle = page.get_by_role("button", name="Nicht gepusht")
    expect(toggle).to_be_visible()
    expect(page.get_by_role("button", name="Erneut sichern (1)")).to_be_enabled()
    toggle.click()
    expect(page.get_by_role("dialog", name="Push fehlgeschlagen")).to_be_visible()
    page.keyboard.press("Escape")
    page.goto(f"{app_url}/#/pool")  # the pool still loads, with its rows
    expect(page.get_by_role("list", name="Anzeigen")).to_be_visible()
    expect(page.get_by_role("button", name="Erneut sichern (1)")).to_be_visible()


def test_a_press_after_the_remote_is_back_succeeds_and_clears_the_failure(page, repository):
    repository.moved.rename(repository.remote)
    page.get_by_role("button", name="Erneut sichern (1)").click()
    expect(page.get_by_role("button", name="Gesichert – jetzt erneut sichern")).to_be_visible()
    expect(page.get_by_role("button", name="Nicht gepusht")).to_have_count(0)
    rating = git(repository.remote, "show", f"main:labels/{POSTING}.json")
    assert '"verdict": "negative"' in rating
