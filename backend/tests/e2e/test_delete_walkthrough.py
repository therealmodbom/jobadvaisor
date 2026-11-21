"""Browser walkthrough of deleting a posting: a rated one from its pool row and an unrated one from
its page, each through the confirmation dialog (the page returns to the pool), the data repository
that still loads, a fresh posting when a deleted one's link is submitted again, and the four
controls of the posting page's head row, which are one height at desktop and phone width. Real app
(`create_app` served by uvicorn) over a copy of the demo persona, the built frontend in Chromium;
the link submission's fetch is stubbed, so no request leaves the machine. The tests share one
server and run in order, each building on the one before; run them as a set: `pytest -m e2e` after
`npm --prefix frontend run build`."""

import shutil
import threading
import time

import pytest
import uvicorn
from conftest import ScriptedModel, ToolScriptModel
from playwright.sync_api import Page, expect, sync_playwright
from test_triage_graph import Harness

from jobadvaisor.api.app import create_app
from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import load
from jobadvaisor.intake import postings as postings_module
from jobadvaisor.intake.fetch import Page as FetchedPage
from jobadvaisor.intake.ladder import LadderResult
from jobadvaisor.intake.postings import Intake
from jobadvaisor.settings import REPOSITORY_ROOT
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.triage.runs import Runs

pytestmark = pytest.mark.e2e

FRONTEND = REPOSITORY_ROOT / "frontend/dist"
RATED = "demo-001"  # an imported "yes" without a strength; the dialog says "Ja"
RATED_TITLE = "Flutter Developer"
RATED_COMPANY = "Demo Co. Oak"
UNRATED = "demo-010"
UNRATED_TITLE = "Mobile QA Engineer"
UNRATED_LINK = "https://careers.example.org/yew/010"
HEAD_ROW = "demo-002"  # a posting that stays, for the head row's measurements
PAGE_TEXT = "We look for a mobile tester who owns the release process. " * 5


@pytest.fixture(scope="module")
def data_root(tmp_path_factory):
    """A copy of the demo persona."""
    root = tmp_path_factory.mktemp("e2e-delete") / "data"
    shutil.copytree(FIXTURE_DIRECTORY, root)
    return root


@pytest.fixture(scope="module")
def app_url(data_root, tmp_path_factory):
    """Base URL of the real app on a free localhost port over `data_root`; fails with a build hint
    when `frontend/dist` is missing and stops the server afterwards."""
    if not (FRONTEND / "index.html").is_file():
        pytest.fail("frontend/dist is missing: run `npm --prefix frontend run build` first")
    harness = Harness(tmp_path_factory.mktemp("e2e-delete-state"), data_root)
    app = create_app(
        Runs(harness.graph, harness.context),
        Intake(data_root, ScriptedModel(lambda schema, prompt: {}), ContentGuard(None, {}),
               loop_model=ToolScriptModel(plan=[])),
        agent=lambda messages: pytest.fail("the walkthrough never chats"), frontend=FRONTEND)
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
    """One Chromium page for the whole walkthrough, desktop width; default timeout 10 s."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.set_default_timeout(10_000)
        yield page
        browser.close()


def pool_row(page: Page, posting_id: str):
    """The pool row of the posting `posting_id`, found by its link (demo titles repeat)."""
    return page.get_by_role("list", name="Anzeigen").get_by_role("listitem").filter(
        has=page.locator(f'a[href="#/anzeigen/{posting_id}"]'))


def record_files(root, posting_id: str) -> list[str]:
    """The files of the posting's own records still on disk (posting, label, score)."""
    return [f"{folder}/{posting_id}.json" for folder in ("postings", "labels", "scores")
            if (root / folder / f"{posting_id}.json").exists()]


def confirm_delete(page: Page, trigger) -> None:
    """Press `trigger` (a trash button), check the dialog names the posting, and confirm."""
    trigger.click()
    dialog = page.get_by_role("alertdialog", name="Anzeige löschen?")
    expect(dialog).to_be_visible()
    expect(dialog.get_by_role("button", name="Abbrechen")).to_be_focused()
    dialog.get_by_role("button", name="Endgültig löschen").click()
    expect(dialog).to_have_count(0)


def test_a_rated_posting_is_deleted_from_its_pool_row(page, app_url, data_root):
    assert record_files(data_root, RATED) == [f"postings/{RATED}.json", f"labels/{RATED}.json"]
    page.goto(f"{app_url}/#/pool")
    row = pool_row(page, RATED)
    expect(row).to_be_visible()
    row.get_by_role("button", name="Anzeige löschen").click()
    dialog = page.get_by_role("alertdialog", name="Anzeige löschen?")
    expect(dialog).to_contain_text(f"{RATED_TITLE} ({RATED_COMPANY}) wird endgültig gelöscht")
    expect(dialog).to_contain_text("Du hast sie mit „Ja“ bewertet")
    dialog.get_by_role("button", name="Abbrechen").click()  # a cancel deletes nothing
    expect(dialog).to_have_count(0)
    assert record_files(data_root, RATED) == [f"postings/{RATED}.json", f"labels/{RATED}.json"]
    confirm_delete(page, row.get_by_role("button", name="Anzeige löschen"))
    expect(pool_row(page, RATED)).to_have_count(0)
    assert record_files(data_root, RATED) == []
    repository = load(data_root)  # the repository still loads
    assert RATED not in repository.postings and RATED not in repository.labels


def test_an_unrated_posting_is_deleted_from_its_page_and_the_page_returns_to_the_pool(
        page, app_url, data_root):
    page.goto(f"{app_url}/#/anzeigen/{UNRATED}")
    expect(page.get_by_role("heading", level=1, name=UNRATED_TITLE)).to_be_visible()
    dialog = page.get_by_role("alertdialog", name="Anzeige löschen?")
    page.get_by_role("button", name="Anzeige löschen").click()
    expect(dialog).to_contain_text(f"{UNRATED_TITLE} (Demo Co. Yew) wird endgültig gelöscht")
    expect(dialog).not_to_contain_text("bewertet")  # no rating line for an unrated posting
    dialog.get_by_role("button", name="Endgültig löschen").click()
    expect(dialog).to_have_count(0)
    page.wait_for_url(f"{app_url}/#/pool")
    expect(page.get_by_role("list", name="Anzeigen")).to_be_visible()
    expect(pool_row(page, UNRATED)).to_have_count(0)
    assert record_files(data_root, UNRATED) == []
    assert UNRATED not in load(data_root).postings


def test_both_postings_stay_gone_after_a_reload_and_the_repository_loads(page, app_url, data_root):
    page.goto(f"{app_url}/#/pool")
    page.reload()
    expect(pool_row(page, HEAD_ROW)).to_be_visible()
    for posting_id in (RATED, UNRATED):
        expect(pool_row(page, posting_id)).to_have_count(0)
    page.goto(f"{app_url}/#/anzeigen/{UNRATED}")
    expect(page.get_by_text("Diese Anzeige gibt es nicht (mehr).")).to_be_visible()
    postings = load(data_root).postings
    assert len(postings) == len(load(FIXTURE_DIRECTORY).postings) - 2
    assert {RATED, UNRATED}.isdisjoint(postings)


def test_submitting_a_deleted_link_again_stores_a_new_posting(page, app_url, data_root):
    """`find_posting` answers the link with a page, so the app fetches nothing."""
    fetched = FetchedPage(UNRATED_LINK, PAGE_TEXT, {
        "title": UNRATED_TITLE, "company": "Demo Co. Yew", "location_raw": "Eastmere"}, None)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(postings_module, "find_posting",
                      lambda intake, url, *args, **kwargs: LadderResult(fetched, []))
        patch.setattr(postings_module, "look_up", lambda *args, **kwargs: None)
        answer = page.request.post(f"{app_url}/postings", form={"url": UNRATED_LINK})
    assert answer.status == 201, answer.text()
    body = answer.json()
    assert body["duplicate"] is False and body["posting_id"] != UNRATED
    stored = load(data_root).postings[body["posting_id"]]
    assert stored.urls == [UNRATED_LINK] and stored.title == UNRATED_TITLE
    page.goto(f"{app_url}/#/pool")
    expect(pool_row(page, body["posting_id"])).to_be_visible()
    expect(pool_row(page, UNRATED)).to_have_count(0)


@pytest.mark.parametrize("width", [1280, 390])
def test_the_head_rows_four_controls_have_the_same_height(page, app_url, width):
    """"Bearbeiten", the application status, the availability and the trash button measure the same
    height (within 1 px) at desktop and at phone width."""
    page.set_viewport_size({"width": width, "height": 844})
    try:
        page.goto(f"{app_url}/#/anzeigen/{HEAD_ROW}")
        controls = {
            "Bearbeiten": page.get_by_role("button", name="Bearbeiten"),
            "Bewerbungsstatus": page.locator("#posting-status"),
            "Verfügbarkeit": page.locator("#posting-availability"),
            "Anzeige löschen": page.get_by_role("button", name="Anzeige löschen"),
        }
        for control in controls.values():
            expect(control).to_be_visible()
        heights = {name: control.bounding_box()["height"] for name, control in controls.items()}
        print(f"\n{width} px: {heights}")
        assert max(heights.values()) - min(heights.values()) <= 1, heights
        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    finally:  # desktop width again
        page.set_viewport_size({"width": 1280, "height": 720})
