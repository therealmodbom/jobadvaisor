"""Browser walkthrough of the alert-mail intake: paste a mail (a synthetic paste event carrying
`text/html`, as a mail client's copy does), see the pick list with a stored entry marked, add the
rest, see each outcome including one closed and one failed entry, and see the run again after a
reload. Real app (`create_app` served by uvicorn) over a temporary data repository, the built
frontend in Chromium, fake models and fake fetchers (no request leaves the machine). The tests
share one server and run in order, each building on the one before; run them as a set:
`pytest -m e2e` after `npm --prefix frontend run build`."""

import json
import threading
import time
import zlib

import pytest
import uvicorn
from conftest import ScriptedModel, ToolScriptModel, write_json
from playwright.sync_api import Page, expect, sync_playwright
from test_triage_graph import POLICY_PACK, Harness, add_posting

from jobadvaisor.api.app import create_app
from jobadvaisor.data.loader import load
from jobadvaisor.intake.fetch import FetchError
from jobadvaisor.intake.fetch import Page as FetchedPage
from jobadvaisor.intake.postings import Intake
from jobadvaisor.settings import REPOSITORY_ROOT
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.triage.runs import Runs

pytestmark = pytest.mark.e2e

FRONTEND = REPOSITORY_ROOT / "frontend/dist"
MAIL_DIR = REPOSITORY_ROOT / "fixtures/intake/alert-mails"
MAIL = (MAIL_DIR / "linkedin-digest.html").read_text()
MAIL_EXPECTED = MAIL_DIR / "linkedin-digest.json"
JOBS = json.loads(MAIL_EXPECTED.read_text())
STORED_URL = JOBS[0]["url"]  # the posting stored before the walkthrough starts
DEAD_URL = JOBS[3]["url"]  # the page that answers 404 on every step: the posting is closed
FAILING_URL = JOBS[5]["url"]  # the page that answers 503 on every step: unreadable, not closed
WAIT = 60_000  # ms; five fake fetches take well under a second


def fill_by_text(schema, prompt) -> dict:
    """A field-fill answer that differs per posting text: title, company and location carry the
    text's checksum, so no two postings share a value."""
    n = zlib.crc32(prompt.encode()) % 10_000
    return {"title": f"Stelle {n}", "company": f"Firma {n}", "location_raw": f"Ort {n}"}


def inert_agent(messages):
    """The chat agent of the app under test: the walkthrough never chats, so any call is a
    test bug."""
    raise AssertionError("the walkthrough must not call the chat agent")


def fake_page(url: str) -> FetchedPage:
    """The page behind a fake fetch: a short text of its own per URL (a text under 40 shingles
    is compared by hash, so no two fake postings count as similar). A dead URL raises the
    ladder's 404 (the posting is gone), a failing URL a 503 (the page could not be read)."""
    if url == DEAD_URL:
        raise FetchError("HTTP 404")
    if url == FAILING_URL:
        raise FetchError("HTTP 503")
    return FetchedPage(url, f"Wir suchen Verstärkung im Team, Kennung {url.rsplit('/', 1)[-1]}.")


@pytest.fixture(scope="module")
def data_root(tmp_path_factory):
    """The temporary data repository: profile, policy pack and one posting `p1` that carries
    the digest's first LinkedIn link, so the pick list marks it as stored."""
    root = tmp_path_factory.mktemp("e2e-alert") / "data"
    write_json(root / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(root / "policy-pack.json", POLICY_PACK)
    add_posting(root, "p1", "Schon gespeicherte Stelle")
    path = root / "postings" / "p1.json"
    urls = f'"urls": ["{STORED_URL}"], "source_type"'
    path.write_text(path.read_text().replace('"source_type"', urls, 1))
    return root


@pytest.fixture(scope="module")
def app_url(data_root, tmp_path_factory):
    """Base URL of the real app on a free localhost port over `data_root`, with the ladder's
    plain and rendered fetch replaced by `fake_page` and no content-guard classifier. Fails
    with a build hint when `frontend/dist` is missing; stops the server afterwards."""
    if not (FRONTEND / "index.html").is_file():
        pytest.fail("frontend/dist is missing: run `npm --prefix frontend run build` first")
    patch = pytest.MonkeyPatch()
    thread = None
    try:
        patch.setenv("STATE_DIRECTORY", str(tmp_path_factory.mktemp("e2e-alert-state")))
        patch.setattr("jobadvaisor.intake.ladder.fetch_plain", fake_page)
        patch.setattr("jobadvaisor.intake.ladder.fetch_rendered", fake_page)
        harness = Harness(tmp_path_factory.mktemp("e2e-alert-triage"), data_root)
        app = create_app(
            Runs(harness.graph, harness.context),
            Intake(data_root, ScriptedModel(fill_by_text), ContentGuard(None, {}),
                   loop_model=ToolScriptModel(plan=[])),
            agent=inert_agent, frontend=FRONTEND)
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        assert server.started, "the app did not start"
        yield f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"
    finally:
        if thread:
            server.should_exit = True
            thread.join(10)
        patch.undo()


@pytest.fixture(scope="module")
def page(app_url):
    """One Chromium page for the whole walkthrough (its session storage carries the run ID
    from step to step, as in a real tab); default timeout 10 s."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_default_timeout(10_000)
        yield page
        browser.close()


PASTE = """([html, plain]) => {
  const data = new DataTransfer()
  data.setData('text/html', html)
  data.setData('text/plain', plain)
  const field = document.getElementById('alert-mail')
  const init = { clipboardData: data, bubbles: true, cancelable: true }
  field.dispatchEvent(new ClipboardEvent('paste', init))
}"""


def source(page: Page, name: str):
    """The source button `name` of the intake view's "Quelle der Anzeige" group."""
    return page.get_by_role("group", name="Quelle der Anzeige").get_by_role("button", name=name)


def paste_mail(page: Page, app_url: str) -> None:
    """Open "Anzeige hinzufügen", choose the source "Alert-Mail", paste the digest as a mail client
    would (HTML flavor plus a plain flavor without any URL) and press "Stellen finden"."""
    page.goto(f"{app_url}/#/hinzufuegen")
    source(page, "Alert-Mail").click()
    page.evaluate(PASTE, [MAIL, "Deine Jobbenachrichtigung"])
    expect(page.get_by_label("Alert-Mail")).to_have_value("Deine Jobbenachrichtigung")
    page.get_by_role("button", name="Stellen finden").click()


def stored_urls(root) -> set[str]:
    """The first URL of every posting stored in the data repository on disk."""
    return {p.urls[0] for p in load(root).postings.values() if p.urls}


def test_the_pasted_mail_lists_its_postings_and_marks_the_stored_one(page, app_url):
    paste_mail(page, app_url)
    expect(page.get_by_role("heading", name="6 Stellen in der Mail gefunden")).to_be_visible()
    expect(page.get_by_text("Gelesen über die feste Regel für LinkedIn")).to_be_visible()
    boxes = page.get_by_role("list", name="Gefundene Stellen").get_by_role("checkbox")
    expect(boxes).to_have_count(6)
    stored = page.get_by_role("checkbox", name=JOBS[0]["title"])
    expect(stored).to_be_disabled()
    expect(stored).not_to_be_checked()
    expect(page.get_by_text("Schon gespeichert")).to_be_visible()
    expect(page.get_by_role("link", name="Gespeicherte Anzeige ansehen")).to_have_attribute(
        "href", "#/anzeigen/p1")
    for job in JOBS[1:]:
        expect(page.get_by_role("checkbox", name=job["title"])).to_be_checked()
    expect(page.get_by_role("button", name="5 Anzeigen hinzufügen")).to_be_enabled()
    expect(page.get_by_role("note")).to_have_count(0)  # nothing left unread


def test_the_run_stores_three_and_reports_the_closed_and_the_unreadable_link(page, data_root):
    page.get_by_role("button", name="5 Anzeigen hinzufügen").click()
    expect(page.get_by_role("heading", name="5 von 5 erledigt")).to_be_visible(timeout=WAIT)
    rows = page.get_by_role("list", name="Stand je Anzeige").locator("> li")
    expect(rows).to_have_count(5)
    expect(page.get_by_text("Hinzugefügt", exact=True)).to_have_count(3)
    expect(page.get_by_role("link", name="Anzeige ansehen")).to_have_count(3)
    closed = rows.filter(has_text=JOBS[3]["title"])  # the 404: the posting is gone, a result
    expect(closed).to_contain_text("Stelle geschlossen")
    expect(closed).to_contain_text("Einfacher Abruf: Stelle geschlossen")
    expect(closed).to_contain_text("HTTP 404")
    expect(closed.get_by_role("button")).to_have_count(0)  # no text or PDF option
    failed = rows.filter(has_text=JOBS[5]["title"])  # the 503: unreadable, a failure
    expect(failed).to_contain_text("Nicht gelesen")
    expect(failed).to_contain_text("Einfacher Abruf: fehlgeschlagen")
    expect(failed).to_contain_text("HTTP 503")
    expect(failed.get_by_role("button", name="Text einfügen")).to_be_visible()
    expect(failed.get_by_role("button", name="PDF hochladen")).to_be_visible()
    expect(page.get_by_text("3 hinzugefügt, 1 geschlossen, 1 nicht gelesen")).to_be_visible()

    expected = {job["url"] for job in JOBS if job["url"] not in (DEAD_URL, FAILING_URL)}
    assert stored_urls(data_root) == expected  # the three new ones, canonical, and the old one


def test_the_report_survives_a_reload(page):
    page.reload()  # the intake view opens on its first source, the run is still attached
    source(page, "Alert-Mail").click()
    expect(page.get_by_role("heading", name="5 von 5 erledigt")).to_be_visible()
    expect(page.get_by_text("Hinzugefügt", exact=True)).to_have_count(3)
    expect(page.get_by_text("Stelle geschlossen").first).to_be_visible()


def test_a_second_paste_marks_everything_stored(page, app_url):
    page.get_by_role("button", name="Andere Mail einfügen").click()
    expect(page.get_by_label("Alert-Mail")).to_have_value("")
    page.evaluate(PASTE, [MAIL, "Deine Jobbenachrichtigung"])
    page.get_by_role("button", name="Stellen finden").click()
    expect(page.get_by_role("heading", name="6 Stellen in der Mail gefunden")).to_be_visible()
    expect(page.get_by_text("Schon gespeichert")).to_have_count(4)  # the old one and the three new
    # the closed one and the unreadable one are still not stored
    expect(page.get_by_role("button", name="2 Anzeigen hinzufügen")).to_be_enabled()


def test_a_failed_entry_leads_to_the_text_source(page, app_url):
    page.get_by_role("button", name="2 Anzeigen hinzufügen").click()
    expect(page.get_by_role("heading", name="2 von 2 erledigt")).to_be_visible(timeout=WAIT)
    run = page.get_by_role("list", name="Stand je Anzeige")
    expect(run).to_contain_text("Stelle geschlossen")  # the closed one is done, with no option
    run.get_by_role("button", name="Text einfügen").click()  # only the unreadable one offers it
    expect(page.get_by_label("Anzeigentext")).to_be_visible()
    expect(source(page, "Text einfügen")).to_have_attribute("aria-pressed", "true")
