"""Browser walkthrough of the availability check: start it from the pool, see its report list a
posting whose link answers 404 and one whose link redirects to a closed marker, find both under the
filter "Stelle geschlossen", rate one of them, reopen the other by hand on its page (the note says
the next check checks again), and start a second check, which closes that posting again and reports
the other one as still closed. Real app (`create_app` served by uvicorn) over a copy of the demo
persona, the built frontend in Chromium. The demo links are answered by an httpx mock transport
behind the check (`AvailabilityChecks(http=...)`), so no request leaves the machine; the per-host
spacing is 0. The tests share one server and run in order, each building on the one before; run
them as a set: `pytest -m e2e` after `npm --prefix frontend run build`."""

import shutil
import threading
import time

import httpx
import pytest
import uvicorn
from conftest import ScriptedModel, ToolScriptModel
from playwright.sync_api import Page, expect, sync_playwright
from test_triage_graph import Harness

from jobadvaisor.api.app import create_app
from jobadvaisor.availability import AvailabilityChecks, check_batch
from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import load
from jobadvaisor.intake.company_facts import Throttle
from jobadvaisor.intake.postings import Intake
from jobadvaisor.settings import REPOSITORY_ROOT
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.triage.runs import Runs

pytestmark = pytest.mark.e2e

FRONTEND = REPOSITORY_ROOT / "frontend/dist"
GONE = "demo-010"  # no rating; its link answers 404
GONE_TITLE = "Mobile QA Engineer"
MOVED = "demo-020"  # no rating; its link redirects to a LinkedIn "expired" address
MOVED_TITLE = "Game Client Developer"
EXPIRED = "https://www.linkedin.com/jobs/search?trk=expired_jd_redirect"
PAGE = "<html><body><main>" + "We look for a developer. " * 40 + "</main></body></html>"
WAIT = 60_000  # ms; about a hundred stubbed fetches take well under a second


def answer(request: httpx.Request) -> httpx.Response:
    """The stubbed web: one demo link answers 404, another redirects to the closed marker, every
    other link answers 200 with a posting text."""
    url = str(request.url)
    if url.endswith("/yew/010"):
        return httpx.Response(404)
    if url.endswith("/elm/020"):
        return httpx.Response(302, headers={"Location": EXPIRED})
    return httpx.Response(200, text=PAGE)


@pytest.fixture(scope="module")
def requested():
    """Every URL the stubbed web was asked for, in order."""
    return []


@pytest.fixture(scope="module")
def data_root(tmp_path_factory):
    """A copy of the demo persona."""
    root = tmp_path_factory.mktemp("e2e-availability") / "data"
    shutil.copytree(FIXTURE_DIRECTORY, root)
    return root


@pytest.fixture(scope="module")
def app_url(data_root, requested, tmp_path_factory):
    """Base URL of the real app on a free localhost port over `data_root`, whose availability
    checks fetch through `answer` without any spacing; fails with a build hint when
    `frontend/dist` is missing and stops the server afterwards."""
    if not (FRONTEND / "index.html").is_file():
        pytest.fail("frontend/dist is missing: run `npm --prefix frontend run build` first")

    def record(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return answer(request)

    harness = Harness(tmp_path_factory.mktemp("e2e-availability-state"), data_root)
    http = httpx.Client(transport=httpx.MockTransport(record), follow_redirects=True)
    app = create_app(
        Runs(harness.graph, harness.context),
        Intake(data_root, ScriptedModel(lambda schema, prompt: {}), ContentGuard(None, {}),
               loop_model=ToolScriptModel(plan=[])),
        agent=lambda messages: pytest.fail("the walkthrough never chats"),
        checks=AvailabilityChecks(data_root, http=http, throttle=Throttle(0)), frontend=FRONTEND)
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
    """One Chromium page for the whole walkthrough (its local storage keeps the check ID from step
    to step, as in a real tab); default timeout 10 s."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_default_timeout(10_000)
        yield page
        browser.close()


def availability(root, posting_id):
    """The stored availability of `posting_id`, read from the data repository on disk."""
    return load(root).postings[posting_id].availability


def pool_row(page: Page, posting_id: str):
    """The pool row of the posting `posting_id`, found by its link (demo titles repeat)."""
    return page.get_by_role("list", name="Anzeigen").get_by_role("listitem").filter(
        has=page.locator(f'a[href="#/anzeigen/{posting_id}"]'))


def start_check(page: Page, app_url: str, covered: int) -> None:
    """Open the pool and press "Verfügbarkeit prüfen" with its count of `covered` postings."""
    page.goto(f"{app_url}/#/pool")
    page.get_by_role("button", name=f"Verfügbarkeit prüfen ({covered})").click()


def test_a_check_reports_the_postings_it_closed(page, app_url, data_root, requested):
    covered = len(check_batch(load(data_root)))
    assert 0 < covered < 150  # only the postings with a link
    start_check(page, app_url, covered)
    heading = page.get_by_role("heading", name="Prüfung fertig: 2 Stellen neu geschlossen")
    expect(heading).to_be_visible(timeout=WAIT)
    closed = page.get_by_role("list", name="Geschlossene Stellen")
    expect(closed.get_by_role("link")).to_have_count(2)
    expect(closed.get_by_role("link", name=f"{GONE_TITLE}, ")).to_have_attribute(
        "href", f"#/anzeigen/{GONE}")
    expect(closed.get_by_role("link", name=f"{MOVED_TITLE}, ")).to_have_attribute(
        "href", f"#/anzeigen/{MOVED}")
    expect(page.get_by_text(f"{covered - 2} verfügbar.")).to_be_visible()
    assert availability(data_root, GONE).state == "closed"
    assert availability(data_root, MOVED).state == "closed"
    assert availability(data_root, MOVED).set_by == "check"
    assert len(requested) == covered  # one request per posting; the 302 sent no second hop
    assert not any("linkedin.com" in url for url in requested)  # the marker's target was never sent


def test_both_postings_are_listed_under_the_filter_stelle_geschlossen(page, app_url):
    page.goto(f"{app_url}/#/pool")
    page.get_by_role("button", name="Stelle geschlossen").click()
    expect(pool_row(page, GONE)).to_be_visible()
    expect(pool_row(page, MOVED)).to_be_visible()
    expect(pool_row(page, GONE).get_by_text("Stelle geschlossen")).to_be_visible()
    expect(page.get_by_role("list", name="Anzeigen").get_by_role("listitem")).to_have_count(2)


def test_a_closed_posting_can_still_be_rated(page, app_url, data_root):
    page.goto(f"{app_url}/#/anzeigen/{MOVED}")
    rate = page.get_by_role("button", name=f"Ja, auf jeden Fall: {MOVED_TITLE}")
    with page.expect_response(lambda r: r.request.method == "PUT" and r.url.endswith("/rating")):
        rate.click()  # the button shows the choice at once; the pool reads it once it is saved
    page.goto(f"{app_url}/#/pool")
    page.get_by_role("button", name="Stelle geschlossen").click()
    expect(pool_row(page, MOVED).get_by_role("button", name=f"Ja, auf jeden Fall: {MOVED_TITLE}")
           ).to_have_attribute("aria-pressed", "true")
    assert load(data_root).labels[MOVED].verdict == "positive"
    assert availability(data_root, MOVED).state == "closed"  # a rating does not reopen it


def test_reopening_by_hand_says_the_next_check_checks_again(page, app_url, data_root):
    page.goto(f"{app_url}/#/anzeigen/{GONE}")
    select = page.get_by_label("Verfügbarkeit", exact=True)
    expect(select).to_have_value("closed")
    expect(page.get_by_text("laut Prüfung vom")).to_be_visible()
    with page.expect_response(lambda r: r.request.method == "PATCH"):
        select.select_option(label="verfügbar")
    expect(page.get_by_text(", die nächste Prüfung prüft neu")).to_be_visible()
    expect(page.get_by_text("von dir gesetzt am")).to_be_visible()
    assert availability(data_root, GONE).state == "available"
    assert availability(data_root, GONE).set_by == "user"
    page.goto(f"{app_url}/#/pool")
    page.get_by_role("button", name="Stelle geschlossen").click()
    expect(pool_row(page, MOVED)).to_be_visible()
    expect(pool_row(page, GONE)).to_have_count(0)


def test_a_second_check_closes_the_reopened_posting_again(page, app_url, data_root, requested):
    covered = len(check_batch(load(data_root)))  # the hand setting does not take a posting out
    before = len(requested)
    start_check(page, app_url, covered)
    heading = page.get_by_role("heading", name="Prüfung fertig: 1 Stelle neu geschlossen")
    expect(heading).to_be_visible(timeout=WAIT)
    closed = page.get_by_role("list", name="Geschlossene Stellen")
    expect(closed.get_by_role("link")).to_have_count(1)
    expect(page.get_by_role("link", name=f"{GONE_TITLE}, ")).to_be_visible()
    expect(page.get_by_text("1 weiterhin geschlossen.")).to_be_visible()  # the redirect one
    assert availability(data_root, GONE).state == "closed"
    assert availability(data_root, GONE).set_by == "check"  # the check replaced the hand setting
    assert availability(data_root, MOVED).state == "closed"
    assert load(data_root).labels[MOVED].verdict == "positive"
    assert len(requested) - before == covered  # every posting again, no marker target sent
    assert not any("linkedin.com" in url for url in requested)
    page.get_by_role("button", name="Stelle geschlossen").click()
    expect(pool_row(page, GONE)).to_be_visible()
    expect(pool_row(page, MOVED)).to_be_visible()
