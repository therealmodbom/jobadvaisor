"""`/mailbox` endpoints (`openspec/changes/58-mailbox-alert-mails/design.md` D6): the account
settings, the folder list and the background check, over the fake IMAP client and the real
finder (rule mails, so no model is called unless a test gives one)."""

import threading
import time
from datetime import date

import pytest
from conftest import FakeStructuredModel, write_json
from cryptography.fernet import Fernet
from fake_imap import FakeFolder, FakeImap, FakeMail, build_mail
from fastapi.testclient import TestClient
from test_alert_mail import fixture
from test_alert_mail_model import Broken
from test_guard import THRESHOLDS
from test_mailbox_checks import DAY, KEY, PASSWORD, SERVER_TEXT, StubRuns, imap
from test_triage_graph import POLICY_PACK, Harness, add_posting

from jobadvaisor import mailbox_secret
from jobadvaisor.api.app import create_app
from jobadvaisor.data.models import MailRef
from jobadvaisor.data.writer import mark_mails, read_mailbox, update_mailbox
from jobadvaisor.intake import mailbox, mailbox_checks
from jobadvaisor.intake.alert_runs import AlertRunBusyError
from jobadvaisor.intake.mailbox import imap_errors
from jobadvaisor.intake.postings import Intake
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.triage.runs import Runs

ACCOUNT = {"host": "imap.example.org", "port": 993, "user": "name@example.org"}
LINKEDIN = [f"https://www.linkedin.com/jobs/view/{n}" for n in (4100000107, 4100000104)]
BA_TEXT = fixture("ba-plain.txt")
# 2,040,000 characters of words: over the 2,000,000 limit.
FILLER = "lorem ipsum " * 170_000


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


def test_the_stored_password_is_the_one_a_check_logs_in_with(tmp_path, root):
    app = api(tmp_path, root, linkedin_mail(1))
    app.configure()
    assert app.check()["status"] == "done"


def test_an_empty_or_absent_password_keeps_the_stored_one(tmp_path, root):
    app = api(tmp_path, root)
    app.configure()
    assert app.put(ACCOUNT | {"password": ""}).json()["password"] == "stored"
    assert app.put(ACCOUNT | {"max_mails": 50}).json()["password"] == "stored"
    assert app.check()["status"] == "done"


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


@pytest.mark.parametrize("change", [{"host": "other.example.org"}, {"port": 143},
                                    {"user": "other@example.org"}])
def test_changing_the_server_port_or_user_without_a_password_removes_the_stored_one(
        tmp_path, root, change):
    app = api(tmp_path, root)
    app.configure()
    answer = app.put(ACCOUNT | change)
    assert answer.status_code == 200 and answer.json()["password"] == "missing"
    assert app.check()["reason"] == "no password"  # and no login is attempted
    assert not any(call[0] == "login" for call in app.fake.calls)


def test_changing_the_server_with_a_new_password_stores_that_one(tmp_path, root):
    app = api(tmp_path, root)
    app.configure()
    answer = app.put(ACCOUNT | {"host": "other.example.org", "password": "new password"})
    assert answer.json()["password"] == "stored"


def stored_password_files(root):
    return list((root.parent / "state").rglob("mailbox-password"))


def test_a_failing_account_write_leaves_no_old_password_beside_the_new_host(
        tmp_path, root, monkeypatch):
    app = api(tmp_path, root)
    app.configure()

    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("jobadvaisor.api.app.update_mailbox_account", broken)
    assert app.put(ACCOUNT | {"host": "other.example.org"}).status_code == 500
    assert stored_password_files(root) == []


def test_a_failing_password_write_leaves_the_new_account_without_any_password(
        tmp_path, root, monkeypatch):
    app = api(tmp_path, root)
    app.configure()

    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(mailbox_secret, "store", broken)
    answer = app.put(ACCOUNT | {"host": "other.example.org", "password": "new password"})
    assert answer.status_code == 500
    assert read_mailbox(root).host == "other.example.org"
    assert stored_password_files(root) == []


def test_a_failing_password_write_keeps_the_old_password_of_an_unchanged_account(
        tmp_path, root, monkeypatch):
    app = api(tmp_path, root)
    app.configure()
    monkeypatch.setattr(mailbox_secret, "store", lambda *args: (_ for _ in ()).throw(OSError()))
    assert app.put(ACCOUNT | {"password": "new password"}).status_code == 500
    assert len(stored_password_files(root)) == 1
    assert app.get("/mailbox").json()["password"] == "stored"


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


def test_an_account_change_during_a_check_is_a_409_naming_the_check(tmp_path, root):
    entered, release = threading.Event(), threading.Event()
    fake = imap(linkedin_mail(1))

    def blocking(account, password):
        entered.set()
        assert release.wait(15)
        fake.login(account.user, password)
        return fake

    app = Api(tmp_path, root, fake, connect=blocking)
    app.configure()
    check_id = app.start()
    assert entered.wait(15)
    answer = app.put(ACCOUNT | {"host": "other.example.org"})
    assert answer.status_code == 409 and answer.json()["error"] == "check in progress"
    assert answer.json()["check_id"] == check_id
    assert read_mailbox(root).host == "imap.example.org"
    assert app.put(ACCOUNT | {"max_mails": 10}).status_code == 200  # no account change
    release.set()
    app.wait(check_id)


def test_an_account_change_drops_the_pending_pick_list(tmp_path, root):
    app = api(tmp_path, root, linkedin_mail(1))
    app.configure()
    check_id = app.check()["check_id"]
    assert app.get("/mailbox").json()["check_id"] == check_id
    app.put(ACCOUNT | {"host": "other.example.org", "password": PASSWORD})
    assert app.get("/mailbox").json()["check_id"] is None
    assert app.get(f"/mailbox/checks/{check_id}").json()["status"] == "finished"


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
    (ConnectionResetError(SERVER_TEXT), "unreachable"),
    (OSError(32, SERVER_TEXT), "protocol")])
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


def real_connect_over(fake, monkeypatch):
    """The real `connect` (login choice and error mapping) over `fake` in place of IMAPClient."""
    monkeypatch.setattr(mailbox, "IMAPClient", lambda *args, **kwargs: fake)
    return mailbox.connect


def test_the_folder_list_of_an_account_with_a_non_ascii_password_works(
        tmp_path, root, monkeypatch):
    fake = FakeImap({"Posteingang": FakeFolder()}, password="geheim§2026")
    app = Api(tmp_path, root, fake, connect=real_connect_over(fake, monkeypatch))
    app.put(ACCOUNT | {"password": "geheim§2026"})
    answer = app.post("/mailbox/folders")
    assert answer.status_code == 200, answer.text
    assert fake.calls[0] == ("plain_login", "name@example.org")
    assert not any("§" in text for text in app.seen[1:])


@pytest.mark.parametrize("error", [
    UnicodeDecodeError("utf-7", b"Bad&AP", 3, 6, "illegal base64"), ValueError("0xff")])
def test_a_malformed_folder_name_is_a_502_never_a_500(tmp_path, root, monkeypatch, error):
    fake = FakeImap({}, password=PASSWORD, errors={"list_folders": error})
    app = Api(tmp_path, root, fake, connect=real_connect_over(fake, monkeypatch))
    app.configure()
    answer = app.post("/mailbox/folders")
    assert answer.status_code == 502 and answer.json()["error"] == "protocol"
    assert "0xff" not in answer.text and "Bad&AP" not in answer.text


# --- the check routes ---------------------------------------------------------------------


def test_a_check_is_started_with_202_and_reports_its_state(tmp_path, root):
    app = api(tmp_path, root, ba_mail(1), empty_mail(2))
    app.configure()
    check_id = app.start()
    state = app.wait(check_id)
    assert set(state) == {"check_id", "status", "reason", "error", "interrupted",
                          "cancel_requested", "cancelled", "total", "read", "remaining", "mails",
                          "failed", "held", "not_screened", "missing_folders"}
    assert (state["status"], state["total"], state["read"], state["remaining"]) == ("done", 2, 2, 0)
    offered, = state["mails"]
    assert set(offered) == {"key", "folder", "sender", "subject", "date", "oversized", "reading",
                            "read_failed", "preview"}
    assert offered["preview"]["read_by"] == ["bundesagentur"]
    assert [entry["url"] for entry in offered["preview"]["entries"]][0].endswith("1000000001-S")
    assert app.get("/mailbox").json()["check_id"] == check_id  # the pending pick list


def test_a_check_without_a_configured_mailbox_is_a_409(tmp_path, root):
    answer = api(tmp_path, root).post("/mailbox/checks", {"since": "2026-10-24"})
    assert answer.status_code == 409 and answer.json()["error"] == "not configured"


def test_the_first_check_needs_a_start_date_and_a_stored_one_is_not_asked_for_again(
        tmp_path, root):
    app = api(tmp_path, root, empty_mail(1))
    app.configure()
    refused = app.post("/mailbox/checks")
    assert refused.status_code == 422 and refused.json()["error"] == "invalid request"
    assert "start date" in refused.json()["detail"]
    assert app.post("/mailbox/checks", {"since": "not a date"}).status_code == 422
    app.wait(app.start())
    assert app.get("/mailbox").json()["since"] == "2026-10-24"
    app.wait(app.start(since=None))  # no body at all


def test_a_second_check_while_one_runs_is_a_409_naming_it(tmp_path, root):
    entered, release = threading.Event(), threading.Event()
    fake = imap(empty_mail(1))

    def blocking(account, password):
        entered.set()
        assert release.wait(15)
        fake.login(account.user, password)
        return fake

    app = Api(tmp_path, root, fake, connect=blocking)
    app.configure()
    check_id = app.start()
    assert entered.wait(15)
    assert app.get("/mailbox").json()["check_id"] == check_id  # the running check
    answer = app.post("/mailbox/checks", {"since": "2026-10-24"})
    assert answer.status_code == 409 and answer.json()["error"] == "check in progress"
    assert answer.json()["check_id"] == check_id
    release.set()
    app.wait(check_id)


def test_a_failed_check_names_its_reason_and_never_an_exception_text(tmp_path, root):
    app = Api(tmp_path, root, FakeImap({}, password="another password"))
    app.configure()
    state = app.check()
    assert (state["status"], state["reason"], state["error"]) == ("failed", "login", None)
    assert PASSWORD not in "".join(app.seen)


def test_an_unknown_check_is_a_404(tmp_path, root):
    app = api(tmp_path, root)
    for answer in (app.get("/mailbox/checks/nope"), app.post("/mailbox/checks/nope/cancel"),
                   app.post("/mailbox/checks/nope/finish", {"entries": []}),
                   app.post("/mailbox/checks/nope/mails/0/read")):
        assert answer.status_code == 404 and answer.json()["error"] == "not found"


def test_a_cancel_is_202_while_running_and_a_409_after_the_end(tmp_path, root):
    entered, release = threading.Event(), threading.Event()
    fake = imap(empty_mail(1))

    def blocking(account, password):
        entered.set()
        assert release.wait(15)
        fake.login(account.user, password)
        return fake

    app = Api(tmp_path, root, fake, connect=blocking)
    app.configure()
    check_id = app.start()
    assert entered.wait(15)
    answer = app.post(f"/mailbox/checks/{check_id}/cancel")
    assert answer.status_code == 202 and answer.json() == {"check_id": check_id}
    assert app.get(f"/mailbox/checks/{check_id}").json()["cancel_requested"] is True
    release.set()
    state = app.wait(check_id)
    assert (state["cancelled"], state["read"], state["total"]) == (True, 0, 1)
    ended = app.post(f"/mailbox/checks/{check_id}/cancel")
    assert ended.status_code == 409 and ended.json()["error"] == "check not running"


def test_finishing_with_entries_starts_one_alert_run_and_marks_the_mails(tmp_path, root):
    app = api(tmp_path, root, ba_mail(1), empty_mail(2))
    app.configure()
    state = app.check()
    urls = [entry["url"] for entry in state["mails"][0]["preview"]["entries"]]
    chosen = [{"url": url, "title": "t"} for url in urls[:2]]
    answer = app.post(f"/mailbox/checks/{state['check_id']}/finish", {"entries": chosen})
    assert answer.status_code == 202 and answer.json() == {"run_id": "run-1"}
    assert [entry.url for entry in app.runs.started[0]] == urls[:2]
    assert read_mailbox(root).handled.uids["Posteingang"].uids == [1, 2]
    assert app.get("/mailbox").json()["check_id"] is None
    assert app.get(f"/mailbox/checks/{state['check_id']}").json()["status"] == "finished"


def test_finishing_with_no_entry_answers_a_null_run(tmp_path, root):
    app = api(tmp_path, root, ba_mail(1))
    app.configure()
    check_id = app.check()["check_id"]
    answer = app.post(f"/mailbox/checks/{check_id}/finish", {"entries": []})
    assert answer.status_code == 202 and answer.json() == {"run_id": None}
    assert app.runs.started == [] and read_mailbox(root).handled.uids


def test_a_second_finish_is_a_409_check_not_done(tmp_path, root):
    app = api(tmp_path, root, ba_mail(1))
    app.configure()
    check_id = app.check()["check_id"]
    app.post(f"/mailbox/checks/{check_id}/finish", {"entries": []})
    answer = app.post(f"/mailbox/checks/{check_id}/finish", {"entries": []})
    assert answer.status_code == 409 and answer.json()["error"] == "check not done"


def test_an_entry_the_check_did_not_offer_is_a_422_and_nothing_is_marked(tmp_path, root):
    app = api(tmp_path, root, ba_mail(1))
    app.configure()
    check_id = app.check()["check_id"]
    answer = app.post(f"/mailbox/checks/{check_id}/finish", {
        "entries": [{"url": "https://jobs.example.org/not-offered", "title": "x"}]})
    assert answer.status_code == 422 and answer.json()["error"] == "entry not offered"
    assert app.runs.started == [] and read_mailbox(root).handled.uids == {}


def test_an_entry_that_is_no_public_link_is_a_422(tmp_path, root):
    app = api(tmp_path, root, ba_mail(1))
    app.configure()
    check_id = app.check()["check_id"]
    answer = app.post(f"/mailbox/checks/{check_id}/finish", {
        "entries": [{"url": "ftp://localhost/x", "title": "x"}]})
    assert answer.status_code == 422 and answer.json()["error"] == "invalid request"


def test_a_busy_alert_run_is_a_409_naming_it_and_nothing_is_marked(tmp_path, root):
    app = api(tmp_path, root, ba_mail(1))
    app.configure()
    state = app.check()
    app.runs.error = AlertRunBusyError("run-0")
    url = state["mails"][0]["preview"]["entries"][0]["url"]
    answer = app.post(f"/mailbox/checks/{state['check_id']}/finish",
                      {"entries": [{"url": url, "title": "t"}]})
    assert answer.status_code == 409 and answer.json()["error"] == "alert run in progress"
    assert answer.json()["run_id"] == "run-0" and read_mailbox(root).handled.uids == {}


def test_more_than_a_hundred_entries_are_one_run(tmp_path, root):
    def digest(uid, first):
        html = "".join(f'<a href="https://www.linkedin.com/jobs/view/{first + n}">Job {first + n}'
                       "</a>" for n in range(80))
        return FakeMail(uid, build_mail(f"<li{uid}@example.org>", html=html), DAY)

    app = api(tmp_path, root, digest(1, 4200000000), digest(2, 4300000000))
    app.configure()
    state = app.check()
    entries = [entry for mail_ in state["mails"] for entry in mail_["preview"]["entries"]]
    assert len(entries) == 160
    answer = app.post(f"/mailbox/checks/{state['check_id']}/finish", {
        "entries": [{"url": e["url"], "title": e["title"]} for e in entries]})
    assert answer.status_code == 202 and len(app.runs.started[0]) == 160


# --- oversized mails ----------------------------------------------------------------------


def oversized_app(tmp_path, root, **options):
    app = api(tmp_path, root, ba_mail(1, extra="\n" + FILLER), **options)
    app.configure()
    return app, app.check()


def test_an_oversized_mail_is_offered_unread_and_read_on_request(tmp_path, root):
    app, state = oversized_app(tmp_path, root)
    mail_ = state["mails"][0]
    assert mail_["oversized"] is True and mail_["preview"] is None
    assert "lorem ipsum lorem" not in repr(state)  # no kept mail text in any answer
    answer = app.post(f"/mailbox/checks/{state['check_id']}/mails/{mail_['key']}/read")
    assert answer.status_code == 200
    body = answer.json()
    assert body["key"] == mail_["key"] and body["reading"] is False
    assert len(body["preview"]["entries"]) == 3 and "lorem ipsum lorem" not in answer.text
    assert "lorem ipsum lorem" not in app.get(f"/mailbox/checks/{state['check_id']}").text
    again = app.post(f"/mailbox/checks/{state['check_id']}/mails/{mail_['key']}/read")
    assert again.status_code == 409 and again.json()["error"] == "not oversized"


def test_a_mail_that_is_not_oversized_or_unknown_cannot_be_read(tmp_path, root):
    app = api(tmp_path, root, ba_mail(1))
    app.configure()
    state = app.check()
    base = f"/mailbox/checks/{state['check_id']}/mails"
    answer = app.post(f"{base}/{state['mails'][0]['key']}/read")
    assert answer.status_code == 409 and answer.json()["error"] == "not oversized"
    assert app.post(f"{base}/99/read").status_code == 404


def test_a_read_for_a_check_that_is_not_done_is_a_409(tmp_path, root):
    app = Api(tmp_path, root, FakeImap({}, password="another password"))
    app.configure()
    check_id = app.check()["check_id"]
    answer = app.post(f"/mailbox/checks/{check_id}/mails/0/read")
    assert answer.status_code == 409 and answer.json()["error"] == "check not done"


def test_a_failing_read_is_a_502_without_exception_text_and_can_be_retried(tmp_path, root):
    html = fixture("unknown-jobid.html") + "<p>" + FILLER + "</p>"
    big = FakeMail(1, build_mail("<big@example.org>", html=html), DAY)
    app = Api(tmp_path, root, imap(big), classifier=Broken())
    app.configure()
    state = app.check()
    base = f"/mailbox/checks/{state['check_id']}/mails/0/read"
    answer = app.post(base)
    assert answer.status_code == 502 and answer.json()["error"] == "screening failed"
    assert "classifier down" not in answer.text
    mail_ = app.get(f"/mailbox/checks/{state['check_id']}").json()["mails"][0]
    assert mail_["read_failed"] == "screening failed" and mail_["reading"] is False
    assert app.post(base).status_code == 502  # retryable


def test_while_a_mail_is_read_finish_start_and_an_account_change_are_409s(tmp_path, root):
    entered, release = threading.Event(), threading.Event()

    class Blocking(Broken):
        def classify(self, text):
            entered.set()
            assert release.wait(15)
            raise RuntimeError("classifier down")

    html = fixture("unknown-jobid.html") + "<p>" + FILLER + "</p>"
    big = FakeMail(1, build_mail("<big@example.org>", html=html), DAY)
    app = Api(tmp_path, root, imap(big), classifier=Blocking())
    app.configure()
    check_id = app.check()["check_id"]
    outcome = []
    reader = threading.Thread(target=lambda: outcome.append(
        app.post(f"/mailbox/checks/{check_id}/mails/0/read")))
    reader.start()
    assert entered.wait(15)
    for answer in (app.post(f"/mailbox/checks/{check_id}/finish", {"entries": []}),
                   app.post(f"/mailbox/checks/{check_id}/mails/0/read"),
                   app.post("/mailbox/checks", {"since": "2026-10-24"}),
                   app.put(ACCOUNT | {"host": "other.example.org"})):
        assert answer.status_code == 409 and answer.json()["error"] == "read in progress"
    assert read_mailbox(root).host == "imap.example.org"
    release.set()
    reader.join(15)
    assert outcome[0].status_code == 502
    assert app.post(f"/mailbox/checks/{check_id}/finish", {"entries": []}).status_code == 202


def test_no_answer_holds_the_password_or_server_text(tmp_path, root):
    app = api(tmp_path, root, ba_mail(1), empty_mail(2))
    app.configure()
    app.check()
    app.post("/mailbox/folders")
    assert all(PASSWORD not in text and SERVER_TEXT not in text for text in app.seen)
    assert mailbox_secret.read(next((root.parent / "state").rglob("mailbox-password")), KEY) == (
        PASSWORD)


def test_every_password_write_holds_the_checks_lock_also_for_an_unchanged_account(
        tmp_path, root, monkeypatch):
    made = []

    class Recorded(mailbox_checks.MailboxChecks):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            made.append(self)

    monkeypatch.setattr(mailbox_checks, "MailboxChecks", Recorded)
    app = api(tmp_path, root)
    app.configure()
    held = []
    for name in ("store", "forget"):
        original = getattr(mailbox_secret, name)
        monkeypatch.setattr(mailbox_secret, name, lambda *args, _original=original: (
            held.append(made[0]._lock.locked()), _original(*args))[1])
    app.put(ACCOUNT | {"password": "new password"})
    app.put(ACCOUNT | {"port": 994})
    app.put(ACCOUNT | {"host": "other.example.org", "password": "other password"})
    assert len(held) == 4 and all(held)
