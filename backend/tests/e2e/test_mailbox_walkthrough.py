"""Browser walkthrough of the mailbox source: set the account up on the settings page, check the
mailbox, see the pick list grouped by mail, collapse one mail, clear another, add the rest, and
check again to see that nothing is offered twice. Real app (`create_app` served by uvicorn) over a
temporary data repository, the built frontend in Chromium, the fake IMAP client of
`tests/fake_imap.py` injected through `create_app(connect=...)`, the mails of the `.eml` fixtures
(three rule senders, so no model reads them), and fake page fetches (no request leaves the
machine). The tests share one server and run in order, each building on the one before; run them
as a set: `pytest -m e2e` after `npm --prefix frontend run build`."""

import json
import threading
import time
import zlib
from datetime import UTC, datetime, timedelta

import pytest
import uvicorn
from conftest import ScriptedModel, ToolScriptModel, write_json
from cryptography.fernet import Fernet
from fake_imap import FakeFolder, FakeImap, FakeMail, build_mail
from playwright.sync_api import Page, expect, sync_playwright
from test_triage_graph import POLICY_PACK, Harness

from jobadvaisor.api.app import create_app
from jobadvaisor.data.loader import load
from jobadvaisor.data.writer import read_mailbox
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


def fake_page(url: str) -> FetchedPage:
    """The page behind a fake fetch: a short text of its own per URL (no two fake postings count
    as similar)."""
    tail = url.rstrip("/").rsplit("/", 1)[-1]
    return FetchedPage(url, f"Wir suchen Verstärkung im Team, Kennung {tail}.")


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
    key, the IMAP connection replaced by `fake`, the ladder's fetches by `fake_page` and no
    content-guard classifier. Fails with a build hint when `frontend/dist` is missing; stops the
    server afterwards."""
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
        patch.setattr("jobadvaisor.intake.ladder.fetch_plain", fake_page)
        patch.setattr("jobadvaisor.intake.ladder.fetch_rendered", fake_page)
        harness = Harness(tmp_path_factory.mktemp("e2e-mailbox-triage"), data_root)
        app = create_app(
            Runs(harness.graph, harness.context),
            Intake(data_root, ScriptedModel(fill_by_text), ContentGuard(None, {}),
                   loop_model=ToolScriptModel(plan=[])),
            agent=inert_agent, frontend=FRONTEND, connect=connect)
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
