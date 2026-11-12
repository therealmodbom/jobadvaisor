"""Browser walkthrough of scoring: a pass that scores a rated posting without a score, a score from
a posting's page, a re-score from a pool row, and the blocked button. Real app (`create_app` served
by uvicorn) over a temporary data repository, the built frontend in Chromium, fake models. The
tests share one server and run in order, each building on the data of the one before; run them as
a set: `pytest -m e2e` after `npm --prefix frontend run build`."""

import threading
import time

import pytest
import uvicorn
from conftest import LABEL, ScriptedModel, ToolScriptModel, write_json
from playwright.sync_api import expect, sync_playwright
from test_triage_graph import POLICY_PACK, Harness, add_posting

from jobadvaisor.api.app import create_app
from jobadvaisor.data.loader import load
from jobadvaisor.data.writer import read_scores
from jobadvaisor.intake.postings import Intake
from jobadvaisor.settings import REPOSITORY_ROOT
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.triage.runs import Runs

pytestmark = pytest.mark.e2e

FRONTEND = REPOSITORY_ROOT / "frontend/dist"
RATED = "Bewertete Stelle 8"  # the fake judge scores the first number of the title
FRESH = "Neue Stelle 6"
SALES = "Sales Manager 5"  # excluded by the policy pack's rule `no-sales`


@pytest.fixture(scope="module")
def data_root(tmp_path_factory):
    """The temporary data repository: a posting the user rated before any score existed, a new
    one and an excluded one."""
    root = tmp_path_factory.mktemp("e2e-score") / "data"
    write_json(root / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(root / "policy-pack.json", POLICY_PACK)
    add_posting(root, "rated", RATED)
    write_json(root / "labels/rated.json", LABEL)
    add_posting(root, "fresh", FRESH)
    add_posting(root, "sales", SALES)
    return root


@pytest.fixture(scope="module")
def harness(data_root, tmp_path_factory):
    """The triage harness the app runs on; a test swaps `harness.judge` to change the next score."""
    return Harness(tmp_path_factory.mktemp("e2e-score-state"), data_root)


@pytest.fixture(scope="module")
def app_url(data_root, harness):
    """Base URL of the real app on a free localhost port; fails with a build hint when
    `frontend/dist` is missing and stops the server afterwards."""
    if not (FRONTEND / "index.html").is_file():
        pytest.fail("frontend/dist is missing: run `npm --prefix frontend run build` first")
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
    """One Chromium page for the whole walkthrough, in the Europe/Berlin time zone so the added
    date reads the same on every machine; default timeout 10 s."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(timezone_id="Europe/Berlin")
        page.set_default_timeout(10_000)
        yield page
        browser.close()


def stored_scores(root) -> dict[str, int]:
    """The score of each posting that has one, read from the data repository on disk."""
    scores, _ = read_scores(root)
    return {posting_id: score.score for posting_id, score in scores.items()}


def pool_row(page, title):
    """The pool row of the posting `title`."""
    return page.get_by_role("list", name="Anzeigen").get_by_role("listitem").filter(
        has=page.get_by_role("heading", name=title))


def test_a_pass_scores_a_rated_posting_without_a_score(page, app_url, data_root):
    page.goto(f"{app_url}/#/pool")
    expect(pool_row(page, RATED).get_by_text("noch kein Score")).to_be_visible()
    page.get_by_role("button", name="Neue Anzeigen bewerten (2)").click()  # rated and fresh
    expect(pool_row(page, RATED).get_by_text("8", exact=True)).to_be_visible(timeout=60_000)
    assert stored_scores(data_root) == {"rated": 8, "fresh": 6}
    assert set(load(data_root).labels) == {"rated"}  # the pass kept the user's rating


def test_a_score_from_the_posting_page_lands_in_the_pool(page, app_url, data_root, harness):
    (data_root / "scores/fresh.json").unlink()  # the new posting has no score again
    harness.judge = ScriptedModel(lambda schema, prompt: {"score": 4, "reasoning": "Passt teils."})
    page.goto(f"{app_url}/#/anzeigen/fresh")
    score = page.get_by_role("region", name="Score")
    expect(score.get_by_text("Noch kein Score")).to_be_visible()
    score.get_by_role("button", name="Score berechnen").click()
    expect(score.get_by_text("Passt teils.")).to_be_visible()
    expect(score.get_by_role("button", name="Neu berechnen")).to_be_enabled()
    assert stored_scores(data_root)["fresh"] == 4
    page.goto(f"{app_url}/#/pool")
    expect(pool_row(page, FRESH).get_by_text("4", exact=True)).to_be_visible()


def test_a_re_score_from_a_pool_row_replaces_the_score(page, app_url, data_root, harness):
    harness.judge = ScriptedModel(lambda schema, prompt: {"score": 9, "reasoning": "Doch besser."})
    page.goto(f"{app_url}/#/pool")
    row = pool_row(page, FRESH)
    row.get_by_role("button", name="Neu berechnen").click()
    expect(row.get_by_text("9", exact=True)).to_be_visible()
    assert stored_scores(data_root)["fresh"] == 9


def test_the_added_date_shows_in_the_browsers_time_zone_in_the_pool_and_on_the_posting_page(
        page, app_url):
    """The fixture's `added_at` is 09:00 UTC; the page's zone is Europe/Berlin, so it reads 10:00."""
    added = "Hinzugefügt 05.01.2026, 10:00"
    page.goto(f"{app_url}/#/pool")
    expect(pool_row(page, RATED).get_by_text(added)).to_be_visible()
    page.goto(f"{app_url}/#/anzeigen/rated")
    expect(page.get_by_role("heading", level=1, name=RATED)).to_be_visible()
    # a role query skips the pool, which stays in the DOM but hidden
    expect(page.get_by_role("time").filter(has_text=added)).to_be_visible()


def test_an_excluded_posting_has_a_disabled_button_with_its_reason(page, app_url, data_root):
    page.goto(f"{app_url}/#/pool")
    row = pool_row(page, SALES)
    expect(row.get_by_role("button", name="Score berechnen")).to_be_disabled()
    row.get_by_role("button", name="Warum nicht verfügbar?").focus()
    expect(row.get_by_role("tooltip")).to_contain_text("Eine Ausschlussregel greift: no-sales")
    assert "sales" not in stored_scores(data_root)
