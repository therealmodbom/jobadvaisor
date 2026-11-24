"""`/mailbox` endpoints (`openspec/changes/58-mailbox-alert-mails/design.md` D6): the account
settings, the folder list and the background check, over the fake IMAP client and the real
finder (rule mails, so no model is called unless a test gives one)."""

import time
from datetime import date

import pytest
from conftest import FakeStructuredModel, write_json
from cryptography.fernet import Fernet
from fake_imap import FakeFolder, FakeImap, FakeMail, build_mail
from fastapi.testclient import TestClient
from test_alert_mail import fixture
from test_guard import THRESHOLDS
from test_mailbox_checks import DAY, KEY, PASSWORD, SERVER_TEXT, StubRuns, imap
from test_triage_graph import POLICY_PACK, Harness, add_posting

from jobadvaisor.api.app import create_app
from jobadvaisor.data.models import MailRef
from jobadvaisor.data.writer import mark_mails, read_mailbox, update_mailbox
from jobadvaisor.intake.mailbox import imap_errors
from jobadvaisor.intake.postings import Intake
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.triage.runs import Runs

ACCOUNT = {"host": "imap.example.org", "port": 993, "user": "name@example.org"}
LINKEDIN = [f"https://www.linkedin.com/jobs/view/{n}" for n in (4100000107, 4100000104)]
BA_TEXT = fixture("ba-plain.txt")


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DIRECTORY", str(tmp_path / "state"))
    monkeypatch.setenv("MAILBOX_KEY", KEY)
    root = tmp_path / "data"
    write_json(root / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(root / "policy-pack.json", POLICY_PACK)
    add_posting(root, "p1", "Engineer 1")
    return root


class Api:
    """The app over `root` with the fake mailbox `fake`, its alert runs stubbed; `get`, `put`
    and `post` answer the response and `check()` runs a check to its end."""

    def __init__(self, tmp_path, root, fake=None, *, classifier=None, connect=None):
        harness = Harness(tmp_path, root)
        guard = ContentGuard(classifier, THRESHOLDS if classifier else {})
        self.root, self.fake, self.runs = root, fake, StubRuns()
        intake = Intake(root, FakeStructuredModel(), guard)

        def connector(account, password):
            with imap_errors():
                fake.login(account.user, password)
            return fake

        self.client = TestClient(create_app(
            Runs(harness.graph, harness.context), intake, frontend=root / "no-frontend-build",
            alert_runs=self.runs, connect=connect or (connector if fake else None)),
            raise_server_exceptions=False)
        self.seen = []

    def request(self, method, path, **kwargs):
        response = self.client.request(method, path, **kwargs)
        self.seen.append(response.text)
        return response

    def get(self, path):
        return self.request("GET", path)

    def put(self, body):
        return self.request("PUT", "/mailbox", json=body)

    def post(self, path, body=None):
        return self.request("POST", path, json=body)

    def configure(self, **extra):
        answer = self.put(ACCOUNT | {"password": PASSWORD} | extra)
        assert answer.status_code == 200, answer.text
        return answer

    def start(self, since="2026-10-24"):
        answer = self.post("/mailbox/checks", {"since": since} if since else None)
        assert answer.status_code == 202, answer.text
        return answer.json()["check_id"]

    def wait(self, check_id):
        deadline = time.monotonic() + 15
        while (state := self.get(f"/mailbox/checks/{check_id}").json())["status"] == "running":
            assert time.monotonic() < deadline, "the check never ended"
            time.sleep(0.005)
        return state

    def check(self, since="2026-10-24"):
        return self.wait(self.start(since))


def api(tmp_path, root, *mails, **options) -> Api:
    return Api(tmp_path, root, imap(*mails) if mails else imap(), **options)


def ba_mail(uid, extra="") -> FakeMail:
    """A mail the Bundesagentur rule reads (three entries), optionally padded by `extra`."""
    return FakeMail(uid, build_mail(f"<ba{uid}@example.org>", text=BA_TEXT + extra), DAY)


def linkedin_mail(uid) -> FakeMail:
    return FakeMail(uid, build_mail(f"<li{uid}@example.org>",
                                    html=fixture("linkedin-single.html")), DAY)


def empty_mail(uid) -> FakeMail:
    return FakeMail(uid, build_mail(f"<empty{uid}@example.org>",
                                    html=fixture("no-postings.html")), DAY)


# --- GET and PUT /mailbox -----------------------------------------------------------------


def test_an_unconfigured_mailbox_answers_defaults(tmp_path, root):
    answer = api(tmp_path, root).get("/mailbox")
    assert answer.status_code == 200
    assert answer.json() == {
        "configured": False, "host": "", "port": 993, "user": "", "folders": {"all": True},
        "max_mails": 200, "since": None, "last_check_at": None, "password": "missing",
        "key_configured": True, "check_id": None}


def test_saving_the_account_answers_it_back_with_a_stored_password_but_never_the_password(
        tmp_path, root):
    app = api(tmp_path, root)
    answer = app.put(ACCOUNT | {"password": PASSWORD})
    assert answer.status_code == 200
    assert answer.json() == {
        "configured": True, "host": "imap.example.org", "port": 993, "user": "name@example.org",
        "folders": {"all": True}, "max_mails": 200, "since": None, "last_check_at": None,
        "password": "stored", "key_configured": True, "check_id": None}
    assert app.get("/mailbox").json()["password"] == "stored"
    assert all(PASSWORD not in text for text in app.seen)
    assert (root / "mailbox.json").read_text().count(PASSWORD) == 0


def test_max_mails_is_answered_stored_and_limited(tmp_path, root):
    app = api(tmp_path, root)
    assert app.put(ACCOUNT | {"max_mails": 50}).json()["max_mails"] == 50
    assert read_mailbox(root).max_mails == 50
    assert app.put(ACCOUNT).json()["max_mails"] == 50  # absent keeps it
    for bad in (0, 1001):
        answer = app.put(ACCOUNT | {"max_mails": bad})
        assert answer.status_code == 422 and answer.json()["error"] == "invalid request"
    assert read_mailbox(root).max_mails == 50


def test_the_folder_choice_is_stored_and_a_bad_choice_is_a_422(tmp_path, root):
    app = api(tmp_path, root)
    assert app.put(ACCOUNT | {"folders": {"names": ["Jobs"]}}).json()["folders"] == {
        "names": ["Jobs"]}
    for bad in ({}, {"all": True, "names": ["Jobs"]}, {"names": []}):
        assert app.put(ACCOUNT | {"folders": bad}).status_code == 422
    assert app.put(ACCOUNT).json()["folders"] == {"names": ["Jobs"]}


@pytest.mark.parametrize("body", [
    {"host": "", "port": 993, "user": "name@example.org"},
    {"host": "imap.example.org", "port": 0, "user": "name@example.org"},
    {"host": "imap.example.org", "port": 70000, "user": "name@example.org"},
    {"host": "imap.example.org", "port": 993, "user": ""},
    {"host": "imap.example.org", "port": 993},
    {"host": "imap.example.org", "port": 993, "user": "a@b.org", "since": "2026-01-01"}])
def test_an_invalid_account_is_a_422_and_nothing_is_written(tmp_path, root, body):
    assert api(tmp_path, root).put(body).status_code == 422
    assert not (root / "mailbox.json").exists()


def test_changing_the_server_with_a_new_password_stores_that_one(tmp_path, root):
    app = api(tmp_path, root)
    app.configure()
    answer = app.put(ACCOUNT | {"host": "other.example.org", "password": "new password"})
    assert answer.json()["password"] == "stored"


def test_a_host_or_user_change_resets_the_records_and_a_port_change_keeps_them(tmp_path, root):
    app = api(tmp_path, root)
    app.configure()

    def seed():
        update_mailbox(root, lambda current: current.model_copy(
            update={"since": date(2026, 10, 24), "last_check_at": DAY}))
        mark_mails(root, handled=[MailRef("Posteingang", 7, 1, None)],
                   waiting=[MailRef("Posteingang", 7, 2, None)])

    seed()
    app.put(ACCOUNT | {"port": 143, "password": PASSWORD})
    kept = read_mailbox(root)
    assert kept.since == date(2026, 10, 24) and kept.handled.uids and kept.waiting.uids
    for change in ({"host": "other.example.org"}, {"user": "other@example.org"}):
        seed()
        app.put(ACCOUNT | change | {"password": PASSWORD})
        stored = read_mailbox(root)
        assert stored.since is None and stored.last_check_at is None
        assert stored.handled.uids == {} and stored.waiting.uids == {}
        app.put(ACCOUNT | {"password": PASSWORD})  # back to the first account


def test_a_password_without_a_key_is_a_409_no_key_and_nothing_is_stored(
        tmp_path, root, monkeypatch):
    for key in (None, "not-a-fernet-key"):
        monkeypatch.delenv("MAILBOX_KEY", raising=False)
        if key:
            monkeypatch.setenv("MAILBOX_KEY", key)
        app = api(tmp_path, root)
        assert app.get("/mailbox").json()["key_configured"] is False
        answer = app.put(ACCOUNT | {"password": PASSWORD})
        assert answer.status_code == 409 and answer.json()["error"] == "no key"
        assert not (root / "mailbox.json").exists()
        assert app.put(ACCOUNT).status_code == 200  # the account itself saves without a password
        (root / "mailbox.json").unlink()


def test_a_stored_password_the_key_cannot_decrypt_is_unreadable(tmp_path, root, monkeypatch):
    app = api(tmp_path, root)
    app.configure()
    monkeypatch.setenv("MAILBOX_KEY", Fernet.generate_key().decode())
    assert api(tmp_path, root).get("/mailbox").json()["password"] == "unreadable"


def test_the_stored_password_without_a_key_is_unreadable(tmp_path, root, monkeypatch):
    api(tmp_path, root).configure()
    monkeypatch.delenv("MAILBOX_KEY")
    assert api(tmp_path, root).get("/mailbox").json()["password"] == "unreadable"


def test_a_malformed_mailbox_file_is_a_500_that_names_no_password(tmp_path, root):
    (root / "mailbox.json").write_text("{not json")
    answer = api(tmp_path, root).get("/mailbox")
    assert answer.status_code == 500


# --- POST /mailbox/folders ----------------------------------------------------------------


def test_the_folders_of_the_account_are_listed_with_their_system_flag(tmp_path, root):
    fake = FakeImap({"Posteingang": FakeFolder(), "Jobs": FakeFolder(),
                     "Papierkorb": FakeFolder(flags=(b"\\Trash",)),
                     "Konten": FakeFolder(flags=(b"\\Noselect",))}, password=PASSWORD)
    app = Api(tmp_path, root, fake)
    app.configure()
    answer = app.post("/mailbox/folders")
    assert answer.status_code == 200
    assert answer.json() == {"folders": [
        {"name": "Posteingang", "system": False}, {"name": "Jobs", "system": False},
        {"name": "Papierkorb", "system": True}]}
    assert fake.calls[-1] == ("logout",) and fake.violations == []


def test_the_folder_list_without_a_configured_account_is_a_409(tmp_path, root):
    answer = api(tmp_path, root).post("/mailbox/folders")
    assert answer.status_code == 409 and answer.json()["error"] == "not configured"


@pytest.mark.parametrize("setup, reason", [("no key", "no key"), ("no password", "no password"),
                                           ("other key", "password unreadable")])
def test_the_folder_list_names_a_missing_key_or_password_as_a_409(
        tmp_path, root, monkeypatch, setup, reason):
    app = api(tmp_path, root)
    if setup == "no password":
        app.put(ACCOUNT)
    else:
        app.configure()
    if setup == "no key":
        monkeypatch.delenv("MAILBOX_KEY")
    if setup == "other key":
        monkeypatch.setenv("MAILBOX_KEY", Fernet.generate_key().decode())
    second = Api(tmp_path, root, imap())
    answer = second.post("/mailbox/folders")
    assert answer.status_code == 409 and answer.json()["error"] == reason
    assert second.fake.calls == []  # no login attempted


@pytest.mark.parametrize("error, reason", [
    (TimeoutError(SERVER_TEXT), "unreachable"),
    (ConnectionResetError(SERVER_TEXT), "protocol")])
def test_the_folder_list_answers_a_connection_failure_as_a_502_with_its_reason_only(
        tmp_path, root, error, reason):
    def failing(account, password):
        with imap_errors():
            raise error

    app = Api(tmp_path, root, imap(), connect=failing)
    app.configure()
    answer = app.post("/mailbox/folders")
    assert answer.status_code == 502 and answer.json()["error"] == reason
    assert SERVER_TEXT not in answer.text and PASSWORD not in answer.text


def test_a_refused_login_for_the_folder_list_is_a_502_login(tmp_path, root):
    app = Api(tmp_path, root, FakeImap({}, password="another password"))
    app.configure()
    assert app.post("/mailbox/folders").json()["error"] == "login"


# --- the check routes ---------------------------------------------------------------------


# --- oversized mails ----------------------------------------------------------------------


def oversized_app(tmp_path, root, **options):
    app = api(tmp_path, root, ba_mail(1, extra="\n" + "x" * 2_000_001), **options)
    app.configure()
    return app, app.check()


