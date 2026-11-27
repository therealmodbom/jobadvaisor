"""Browser walkthrough of the mailbox source: set the account up on the settings page, check the
mailbox, see the pick list grouped by mail, collapse one mail, clear another, add the rest, and
check again to see that nothing is offered twice. Real app (`create_app` served by uvicorn) over a
temporary data repository, the built frontend in Chromium, the fake IMAP client of
`tests/fake_imap.py` injected through `create_app(connect=...)`, the mails of the `.eml` fixtures
(three rule senders, so no model reads them), and fake page fetches (no request leaves the
machine). The tests share one server and run in order, each building on the one before; run them
as a set: `pytest -m e2e` after `npm --prefix frontend run build`. The last tests add two mails that
offer one posting and a link whose fetch is disputed: the run, the next check (which does not
offer the mails again), the link under „Offene Links“ at a phone's width, a retry and a removal."""

import json
import threading
import time
import zlib
from datetime import UTC, datetime, timedelta

import pytest
import uvicorn
from conftest import ScriptedModel, SpacingClock, ToolScriptModel, write_json
from cryptography.fernet import Fernet
from fake_imap import FakeFolder, FakeImap, FakeMail, build_mail
from playwright.sync_api import Page, expect, sync_playwright
from test_triage_graph import POLICY_PACK, Harness

from jobadvaisor.api.app import create_app
from jobadvaisor.data.loader import load
from jobadvaisor.data.writer import read_mailbox, read_unsettled_links
from jobadvaisor.intake.alert_runs import AlertRuns
from jobadvaisor.intake.fetch import FetchError
from jobadvaisor.intake.fetch import Page as FetchedPage
from jobadvaisor.intake.mailbox import imap_errors
from jobadvaisor.intake.postings import Intake
from jobadvaisor.settings import REPOSITORY_ROOT
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.triage.runs import Runs

pytestmark = pytest.mark.e2e

FRONTEND = REPOSITORY_ROOT / "frontend/dist"
MAIL_DIR = REPOSITORY_ROOT / "fixtures/intake/alert-mails"
KEY = Fernet.generate_key().decode()
PASSWORD = "app-password-for-the-walkthrough"
WAIT = 60_000  # ms; four fake fetches take well under a second
# The three mails with postings, in UID order: the fixture, its subject and the heading text
# the pick list shows. The fourth mail lists no posting.
LINKEDIN, BA, CAREER = "linkedin-mime", "ba-mime", "career-site-mime"
SUBJECTS = {LINKEDIN: "Neue Stellen für Sie: Leitung Softwarebetrieb",
            BA: "2 neue Treffer für Ihre Suche: Datenschutz",
            CAREER: "Neue Positionen für dich"}
# The two mails of the last test: both list SHARED, the second also DISPUTED, whose plain fetch
# answers 404 and every other request 429.
FIRST, SECOND = "Stellen im Kundendienst", "Stellen in der Beschaffung"
SHARED = "https://www.linkedin.com/jobs/view/4100000401"
OWN = "https://www.linkedin.com/jobs/view/4100000402"
DISPUTED = "https://www.linkedin.com/jobs/view/4100000403"
TITLES = {SHARED: "Leitung Kundendienst (m/w/d)", OWN: "Fachkraft Lagerlogistik (m/w/d)",
          DISPUTED: "Referent Beschaffung (m/w/d)"}
fetched: list[str] = []  # every URL the fake fetches were asked for, in order


def expected(case: str) -> list[dict]:
    """The postings the fixture mail lists: `[{url, title}]` as the finder cleans them."""
    return json.loads((MAIL_DIR / f"{case}.json").read_text())


def fill_by_text(schema, prompt) -> dict:
    """A field-fill answer that differs per posting text, so no two postings share a value."""
    n = zlib.crc32(prompt.encode()) % 10_000
    return {"title": f"Stelle {n}", "company": f"Firma {n}", "location_raw": f"Ort {n}"}


def inert_agent(messages):
    """The chat agent of the app under test: the walkthrough never chats, so any call is a bug."""
    raise AssertionError("the walkthrough must not call the chat agent")


def fake_plain(url: str) -> FetchedPage:
    """The plain fetch: a short text of its own per URL (no two fake postings count as similar),
    except for `DISPUTED`, which answers 404. Records the URL in `fetched`."""
    fetched.append(url)
    if url == DISPUTED:
        raise FetchError("HTTP 404")
    tail = url.rstrip("/").rsplit("/", 1)[-1]
    return FetchedPage(url, f"Wir suchen Verstärkung im Team, Kennung {tail}.")


def fake_rendered(url: str) -> FetchedPage:
    """The rendered fetch: as `fake_plain`, but `DISPUTED` answers 429."""
    if url == DISPUTED:
        fetched.append(url)
        raise FetchError("HTTP 429")
    return fake_plain(url)


def mailbox_server() -> FakeImap:
    """The fake account: the inbox with the three alert mails and one mail without a posting, and
    a trash folder with a LinkedIn mail that no check may read (a system folder)."""
    received = datetime.now(UTC) - timedelta(days=2)
    inbox = [FakeMail(uid, (MAIL_DIR / f"{case}.eml").read_bytes(), received + timedelta(hours=uid))
             for uid, case in enumerate((LINKEDIN, BA, CAREER), start=1)]
    inbox.append(FakeMail(4, build_mail("<no-postings-1@example.org>", subject="Willkommen",
                                        text="Schön, dass Sie da sind."),
                          received + timedelta(hours=4)))
    trash = [FakeMail(1, build_mail(
        "<trash-1@example.org>", subject="Alte Stelle",
        html='<a href="https://www.linkedin.com/jobs/view/4100000299">Alte Stelle (m/w/d)</a>'),
        received)]
    return FakeImap({"Posteingang": FakeFolder(validity=7, mails=inbox),
                     "Papierkorb": FakeFolder(flags=(b"\\Trash",), validity=8, mails=trash)},
                    password=PASSWORD)


@pytest.fixture(scope="module")
def fake():
    """The fake mailbox the app under test connects to; tests read its recorded calls."""
    return mailbox_server()


@pytest.fixture(scope="module")
def data_root(tmp_path_factory):
    """The temporary data repository: a profile and a policy pack, no posting."""
    root = tmp_path_factory.mktemp("e2e-mailbox") / "data"
    write_json(root / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(root / "policy-pack.json", POLICY_PACK)
    return root


@pytest.fixture(scope="module")
def state_root(tmp_path_factory):
    """The state directory of the app under test, where the encrypted password goes."""
    return tmp_path_factory.mktemp("e2e-mailbox-state")


@pytest.fixture(scope="module")
def app_url(data_root, state_root, fake, tmp_path_factory):
    """Base URL of the real app on a free localhost port over `data_root`, with a valid mailbox
    key, the IMAP connection replaced by `fake`, the ladder's fetches by `fake_plain` and
    `fake_rendered`, the alert runs' host spacing by a fake clock and no content-guard classifier.
    Fails with a build hint when `frontend/dist` is missing; stops the server afterwards."""
    if not (FRONTEND / "index.html").is_file():
        pytest.fail("frontend/dist is missing: run `npm --prefix frontend run build` first")

    def connect(account, password):
        with imap_errors():
            fake.login(account.user, password)
        return fake

    patch = pytest.MonkeyPatch()
    thread = None
    try:
        patch.setenv("STATE_DIRECTORY", str(state_root))
        patch.setenv("MAILBOX_KEY", KEY)
        patch.setattr("jobadvaisor.intake.ladder.fetch_plain", fake_plain)
        patch.setattr("jobadvaisor.intake.ladder.fetch_rendered", fake_rendered)
        harness = Harness(tmp_path_factory.mktemp("e2e-mailbox-triage"), data_root)
        intake = Intake(data_root, ScriptedModel(fill_by_text), ContentGuard(None, {}),
                        loop_model=ToolScriptModel(plan=[]))
        app = create_app(
            Runs(harness.graph, harness.context), intake, agent=inert_agent,
            frontend=FRONTEND, connect=connect,
            alert_runs=AlertRuns(intake, throttle=SpacingClock().throttle()))
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
    """One Chromium page for the whole walkthrough (its browser storage carries the check and run
    IDs from step to step, as in a real tab); default timeout 10 s."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_default_timeout(10_000)
        yield page
        browser.close()


def source(page: Page, name: str):
    """The source button `name` of the intake view's "Quelle der Anzeige" group."""
    return page.get_by_role("group", name="Quelle der Anzeige").get_by_role("button", name=name)


def mail_item(page: Page, case: str):
    """The pick list's item of the mail of fixture `case`, found by its subject."""
    return page.get_by_role("list", name="Mails der Prüfung").locator("> li").filter(
        has_text=SUBJECTS[case])


def mail_boxes(page: Page, case: str):
    """The mail head's checkbox and its collapse button for the mail of fixture `case`."""
    subject = SUBJECTS[case]
    return (page.get_by_role("checkbox", name=f"Alle Anzeigen der Mail „{subject}“"),
            page.get_by_role("button", name=f"Anzeigen der Mail „{subject}“"))


def full_reads(fake: FakeImap) -> int:
    """How many whole mails the app has fetched so far (the `BODY.PEEK[]` fetches)."""
    return sum(1 for call in fake.calls if call[0] == "fetch" and "BODY.PEEK[]" in call[2])


def stored_urls(root) -> set[str]:
    """The first URL of every posting stored in the data repository on disk."""
    return {p.urls[0] for p in load(root).postings.values() if p.urls}


def test_the_account_is_set_up_on_the_settings_page_and_the_password_is_kept_secret(
        page, app_url, fake, data_root, state_root):
    page.goto(f"{app_url}/#/einstellungen/postfach")
    expect(page.get_by_role("heading", name="Postfach", exact=True)).to_be_visible()
    page.get_by_label("Server").fill("imap.example.org")
    page.get_by_label("Benutzername").fill("name@example.org")
    page.get_by_label("Passwort", exact=True).fill(PASSWORD)
    page.get_by_role("button", name="Verbinden und Ordner laden").click()
    expect(page.get_by_text("Verbunden. 2 Ordner gefunden.")).to_be_visible()
    expect(page.get_by_role("radio", name="Alle Ordner")).to_be_checked()
    expect(page.get_by_label("Passwort · gespeichert")).to_have_value("")  # the field is empty
    page.get_by_role("button", name="Speichern").click()
    expect(page.get_by_text("Gespeichert.", exact=True)).to_be_visible()

    account = read_mailbox(data_root)
    assert (account.host, account.port, account.user) == ("imap.example.org", 993,
                                                          "name@example.org")
    assert account.folders.all is True and account.since is None
    stored = page.request.get(f"{app_url}/mailbox")
    assert stored.json()["password"] == "stored" and PASSWORD not in stored.text()
    for root in (data_root, state_root):  # the password is in no file, not even the state's
        for path in root.rglob("*"):
            if path.is_file():
                assert PASSWORD.encode() not in path.read_bytes(), path
    assert list(state_root.rglob("mailbox-password"))  # but the encrypted one is stored
    assert fake.violations == []


def test_the_check_offers_the_postings_of_three_mails_grouped_by_mail(page, app_url, fake):
    page.goto(f"{app_url}/#/hinzufuegen")
    source(page, "Postfach").click()
    expect(page.get_by_text("name@example.org auf imap.example.org")).to_be_visible()
    expect(page.get_by_label("Mails ab")).to_be_visible()  # the first check asks for its start
    page.get_by_role("button", name="Postfach prüfen").click()
    mails = page.get_by_role("list", name="Mails der Prüfung").locator("> li")
    expect(mails).to_have_count(3, timeout=WAIT)  # the mail without a posting is not listed
    for case in (LINKEDIN, BA, CAREER):
        expect(mail_item(page, case)).to_contain_text("2 von 2 ausgewählt")
        for job in expected(case):
            expect(mail_item(page, case).get_by_role("checkbox", name=job["title"])).to_be_checked()
    expect(page.get_by_text("Alte Stelle")).to_have_count(0)  # the trash folder is never read
    expect(page.get_by_role("button", name="6 Anzeigen hinzufügen")).to_be_enabled()
    assert full_reads(fake) == 4  # the three alert mails and the one without a posting
    assert all(call[1] != "Papierkorb" for call in fake.calls if call[0] == "select_folder")


def test_one_mail_is_collapsed_and_another_is_cleared(page):
    _, collapse = mail_boxes(page, LINKEDIN)
    entries = page.get_by_role("list", name=f"Anzeigen der Mail „{SUBJECTS[LINKEDIN]}“")
    expect(collapse).to_have_attribute("aria-expanded", "true")
    collapse.click()
    expect(collapse).to_have_attribute("aria-expanded", "false")
    expect(entries).to_be_hidden()
    expect(mail_item(page, LINKEDIN)).to_contain_text("2 von 2 ausgewählt")  # still selected
    box, _ = mail_boxes(page, BA)
    box.uncheck()  # clears both entries of the mail at once
    expect(mail_item(page, BA)).to_contain_text("0 von 2 ausgewählt")
    for job in expected(BA):
        expect(mail_item(page, BA).get_by_role("checkbox", name=job["title"])).not_to_be_checked()
    expect(page.get_by_role("button", name="4 Anzeigen hinzufügen")).to_be_enabled()


def test_adding_stores_the_chosen_postings_and_counts_every_mail_as_handled(
        page, data_root):
    page.get_by_role("button", name="4 Anzeigen hinzufügen").click()
    expect(page.get_by_role("heading", name="4 von 4 erledigt")).to_be_visible(timeout=WAIT)
    expect(page.get_by_text("Hinzugefügt", exact=True)).to_have_count(4)
    chosen = {job["url"] for case in (LINKEDIN, CAREER) for job in expected(case)}
    cleared = {job["url"] for job in expected(BA)}
    assert stored_urls(data_root) == chosen  # the collapsed mail's entries are added too
    assert not cleared & stored_urls(data_root)
    handled = read_mailbox(data_root).handled
    # the three alert mails, the cleared one included, and the one without a posting
    assert len(handled.ids) == 4
    assert handled.uids["Posteingang"].uids == [1, 2, 3, 4]
    assert read_mailbox(data_root).last_check_at is not None


def test_a_second_check_finds_nothing_new(page, fake):
    reads = full_reads(fake)
    page.get_by_role("button", name="Zurück zum Postfach").click()
    expect(page.get_by_text("Letzte Prüfung:")).to_be_visible()
    page.get_by_role("button", name="Postfach prüfen").click()
    expect(page.get_by_text("Keine neuen Mails seit dem")).to_be_visible(timeout=WAIT)
    expect(page.get_by_role("list", name="Mails der Prüfung")).to_have_count(0)
    assert full_reads(fake) == reads  # no mail was fetched again, the cleared one included
    assert fake.violations == []
    assert not any(call[0] == "login" and call[1] != "name@example.org" for call in fake.calls)


def alert_mail(uid: int, subject: str, links: list[str], received: datetime) -> FakeMail:
    """A fictional LinkedIn-style alert mail with one anchor per link in `links` (title from
    `TITLES`); the rules read it without a model."""
    html = "".join(f'<p><a href="{link}">{TITLES[link]}</a></p>' for link in links)
    return FakeMail(uid, build_mail(f"<shared-link-{uid}@example.org>", subject=subject, html=html),
                    received)


def test_a_posting_in_two_mails_is_fetched_once_and_a_disputed_link_does_not_bring_its_mail_back(
        page, fake, data_root):
    now = datetime.now(UTC)
    fake.folders["Posteingang"].mails += [
        alert_mail(5, FIRST, [SHARED, OWN], now - timedelta(hours=2)),
        alert_mail(6, SECOND, [SHARED, DISPUTED], now - timedelta(hours=1))]
    reads = full_reads(fake)
    page.get_by_role("button", name="Postfach prüfen").click()
    mails = page.get_by_role("list", name="Mails der Prüfung").locator("> li")
    expect(mails).to_have_count(2, timeout=WAIT)
    first, second = (page.get_by_role("listitem", name=f"Mail „{subject}“", exact=True)
                     for subject in (FIRST, SECOND))  # by name: the note names the first mail
    expect(first).to_contain_text("2 von 2 ausgewählt")
    expect(second).to_contain_text("1 von 1 ausgewählt")  # the copy of the link does not count
    expect(second).to_contain_text(f"Auch in der Mail von jobs@example.org, „{FIRST}“")
    copy = second.get_by_role("checkbox", name=TITLES[SHARED])  # shown, but not to be ticked
    expect(copy).to_be_disabled()
    expect(copy).not_to_be_checked()
    expect(first).not_to_contain_text("Auch in der Mail")
    expect(page.get_by_text("Jede Mail dieser Liste gilt als gelesen")).to_be_visible()
    expect(page.get_by_role("button", name="3 Anzeigen hinzufügen")).to_be_enabled()
    assert full_reads(fake) == reads + 2

    fetched.clear()
    page.get_by_role("button", name="3 Anzeigen hinzufügen").click()
    expect(page.get_by_role("heading", name="3 von 3 erledigt")).to_be_visible(timeout=WAIT)
    rows = page.get_by_role("list", name="Stand je Anzeige").locator("> li")
    expect(rows).to_have_count(3)  # the link of both mails is in the run once
    expect(page.get_by_text("Hinzugefügt", exact=True)).to_have_count(2)
    expect(page.get_by_text("Gleicher Link wie oben")).to_have_count(0)
    disputed = rows.filter(has_text=DISPUTED)
    expect(disputed.get_by_text("Nicht beurteilbar", exact=True)).to_be_visible()
    expect(disputed).to_contain_text("andere Abrufe wurden aber abgewiesen")
    expect(rows.get_by_text("Stelle geschlossen", exact=True)).to_have_count(0)  # not closed
    expect(page.get_by_role("button", name="Lauf abbrechen")).to_have_count(0)  # the run is over
    expect(page.get_by_text(
        "Die Links, die nicht gelesen, nicht beurteilbar oder nicht gestartet sind, stehen unter "
        "„Offene Links“. Ihre Mails gelten als gelesen.")).to_be_visible()
    expect(page.get_by_text("wieder an")).to_have_count(0)  # no mail is offered again
    expect(page.get_by_role("link", name="Offene Links ansehen")).to_have_attribute(
        "href", "#/offene-links")
    assert fetched.count(SHARED) == 1  # one fetch for the link both mails list
    assert fetched.count(OWN) == 1
    assert fetched.count(DISPUTED) == 2  # the plain 404, then the rendered 429
    assert {SHARED, OWN} <= stored_urls(data_root)
    assert DISPUTED not in stored_urls(data_root)
    handled = read_mailbox(data_root).handled
    assert handled.uids["Posteingang"].uids == [1, 2, 3, 4, 5, 6]  # both mails are handled
    (row,) = read_unsettled_links(data_root).links  # the disputed link is kept, and nothing else
    assert (row.url, row.title, row.source, row.state, row.tries) == (
        DISPUTED, TITLES[DISPUTED], "mailbox", "unclear", 1)
    assert not {FIRST, SECOND, "jobs@example.org"} & {
        str(value) for value in row.model_dump().values()}  # no sender, no subject

    filters = page.get_by_role("group", name="Filter")
    unclear = filters.get_by_role("button", name="1 nicht beurteilbar", exact=True)
    unclear.click()  # only the disputed entry is left, and the filter says it is pressed
    expect(unclear).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_text("Zeigt 1 von 3 Anzeigen: nicht beurteilbar")).to_be_visible()
    expect(rows).to_have_count(1)
    link = rows.get_by_role(
        "link", name=f"Anzeige „{TITLES[DISPUTED]}“ öffnen, neuer Tab: {DISPUTED}", exact=True)
    expect(link).to_have_attribute("href", DISPUTED)  # the posting's address, as the mail gave it
    expect(link).to_have_attribute("target", "_blank")  # in a new tab
    page.context.route(  # the address is answered here, so no real host is ever asked
        "https://www.linkedin.com/jobs/view/**",
        lambda route: route.fulfill(status=200, content_type="text/html",
                                    body="<title>Fictional posting</title>"))
    link.focus()
    with page.context.expect_page() as opened:
        link.press("Enter")  # the keyboard opens the original ad in a new tab
    posting = opened.value
    posting.wait_for_load_state()
    assert posting.url == DISPUTED
    posting.close()
    expect(unclear).to_have_attribute("aria-pressed", "true")  # the run view is as it was
    expect(page.get_by_text("Zeigt 1 von 3 Anzeigen: nicht beurteilbar")).to_be_visible()
    expect(rows).to_have_count(1)
    unclear.click()  # the second press ends the filter
    expect(rows).to_have_count(3)



def test_the_next_check_does_not_offer_the_mail_of_the_disputed_link_and_the_list_keeps_it(
        page, fake):
    reads = full_reads(fake)
    page.get_by_role("button", name="Zurück zum Postfach").click()
    page.get_by_role("button", name="Postfach prüfen").click()
    expect(page.get_by_text("Keine neuen Mails seit dem")).to_be_visible(timeout=WAIT)
    expect(page.get_by_role("list", name="Mails der Prüfung")).to_have_count(0)
    assert full_reads(fake) == reads  # neither mail was read again
    # the badge's hidden text is part of each name, with no space before its comma
    expect(page.get_by_role("link", name="Anzeige hinzufügen, 1 offener Link", exact=True)
           ).to_be_visible()
    expect(source(page, "Offene Links, 1 offener Link")).to_be_visible()

    source(page, "Offene Links").click()
    expect(page.get_by_role("heading", name="1 offener Link")).to_be_visible()
    rows = page.get_by_role("list", name="Offene Links").locator("> li")
    expect(rows).to_have_count(1)
    row = rows.first
    expect(row.get_by_text("Nicht beurteilbar", exact=True)).to_be_visible()
    expect(row).to_contain_text(TITLES[DISPUTED])
    expect(row).to_contain_text("Postfach · in 1 Lauf abgerufen")
    expect(row.get_by_role(
        "link", name=f"Anzeige „{TITLES[DISPUTED]}“ öffnen, neuer Tab: {DISPUTED}", exact=True)
           ).to_have_attribute("href", DISPUTED)
    expect(row.get_by_role("button", name="Erneut versuchen")).to_be_enabled()
    expect(row.get_by_role("button", name="Entfernen")).to_be_enabled()
    assert fake.violations == []


def box(locator) -> dict:
    """The bounding box `{x, y, width, height}` of the one element `locator` finds."""
    found = locator.bounding_box()
    assert found is not None, locator
    return found


def test_on_a_phone_the_retry_buttons_sit_below_their_text_at_full_width(page):
    page.set_viewport_size({"width": 390, "height": 844})
    try:
        # the buttons animate their layout (`transition-all`) when the media query switches on,
        # so measure only once every transition has ended
        page.wait_for_function("document.getAnimations().length === 0")
        heading = page.get_by_role("heading", name="1 offener Link")
        head_text = box(heading.locator(".."))
        all_button = box(page.get_by_role("button", name="Alle erneut versuchen (1)"))
        listing = box(page.get_by_role("list", name="Offene Links"))
        assert all_button["y"] >= head_text["y"] + head_text["height"] - 1  # below the head text
        assert abs(all_button["width"] - listing["width"]) <= 2  # at the list's width
        assert abs(all_button["x"] - listing["x"]) <= 2

        row = page.get_by_role("list", name="Offene Links").locator("> li").first
        outer = box(row)
        text = box(row.locator("> div").first)
        retry, remove = (box(row.get_by_role("button", name=name))
                         for name in ("Erneut versuchen", "Entfernen"))
        for button in (retry, remove):
            assert button["y"] >= text["y"] + text["height"] - 1  # below the row's text
            assert abs(button["width"] - retry["width"]) <= 1
        assert remove["y"] >= retry["y"] + retry["height"] - 1  # stacked, not side by side
        # at the row's width: its inner width, less the border and the padding of 16 px a side
        assert abs(retry["width"] - (outer["width"] - 34)) <= 2
        assert page.evaluate(  # the page does not scroll sideways
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    finally:
        page.set_viewport_size({"width": 1280, "height": 720})


def test_a_retry_runs_the_disputed_link_again_and_the_list_counts_one_more_run(
        page, fake, data_root):
    fetched.clear()
    page.get_by_role("list", name="Offene Links").locator("> li").first.get_by_role(
        "button", name="Erneut versuchen").click()
    expect(page.get_by_role("heading", name="1 von 1 erledigt")).to_be_visible(timeout=WAIT)
    row = page.get_by_role("list", name="Stand je Anzeige").locator("> li")
    expect(row).to_have_count(1)
    expect(row.get_by_text("Nicht beurteilbar", exact=True)).to_be_visible()  # still disputed
    assert fetched.count(DISPUTED) == 2  # the plain 404, then the rendered 429, as in the run
    assert fetched.count(SHARED) == 0 and fetched.count(OWN) == 0  # only the listed link
    (kept,) = read_unsettled_links(data_root).links
    assert (kept.state, kept.tries, kept.source) == ("unclear", 2, "mailbox")  # the first source
    assert read_mailbox(data_root).handled.uids["Posteingang"].uids == [1, 2, 3, 4, 5, 6]

    page.get_by_role("button", name="Zurück zu den offenen Links").click()
    list_row = page.get_by_role("list", name="Offene Links").locator("> li")
    expect(list_row).to_have_count(1)
    expect(list_row).to_contain_text("Postfach · in 2 Läufen abgerufen")
    assert fake.violations == []


def test_removing_the_link_empties_the_list_and_leaves_the_mails_alone(page, data_root):
    handled = read_mailbox(data_root).handled.uids["Posteingang"].uids
    stored = stored_urls(data_root)
    page.get_by_role("list", name="Offene Links").get_by_role("button", name="Entfernen").click()
    expect(page.get_by_role("heading", name="Keine offenen Links")).to_be_visible()
    expect(page.get_by_text(f"„{TITLES[DISPUTED]}“ entfernt.", exact=True)).to_be_attached()
    expect(page.get_by_role("list", name="Offene Links")).to_have_count(0)
    expect(page.get_by_role("link", name="Anzeige hinzufügen", exact=True)
           ).to_be_visible()  # the badge is gone: the name is the label alone
    assert read_unsettled_links(data_root).links == []
    assert read_mailbox(data_root).handled.uids["Posteingang"].uids == handled
    assert stored_urls(data_root) == stored
