"""The mailbox check (`openspec/changes/58-mailbox-alert-mails/design.md` D4): the background run
over the fake IMAP client with a stub finder, and what it reports and marks."""

import imaplib
import logging
import ssl
import threading
import time
from datetime import UTC, date, datetime, timedelta
from email import message_from_bytes, policy

import pytest
from cryptography.fernet import Fernet
from fake_imap import FakeFolder, FakeImap, FakeMail, build_mail
from test_alert_mail import NoGuard, Untouchable, fixture

from jobadvaisor import mailbox_secret
from jobadvaisor.data.models import Folders, MailRef
from jobadvaisor.data.writer import read_mailbox, update_mailbox, update_mailbox_account
from jobadvaisor.intake import mailbox
from jobadvaisor.intake.alert_mail import FinderError
from jobadvaisor.intake.alert_runs import AlertRunBusyError, RunEntry
from jobadvaisor.intake.mailbox import imap_errors
from jobadvaisor.intake.mailbox_checks import (
    CheckBusyError,
    CheckNotDoneError,
    CheckNotRunningError,
    EntryNotOfferedError,
    MailboxChecks,
)
from jobadvaisor.intake.postings import Intake
from jobadvaisor.tools.guard import ContentGuard

KEY = Fernet.generate_key().decode()
PASSWORD = "correct horse battery staple"
SINCE = date(2026, 10, 24)
DAY = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
ACCOUNT = ("imap.example.org", 993, "name@example.org")
EMPTY = {"entries": [], "read_by": [], "unread_hosts": [], "held": False, "model_skipped": None,
         "truncated": False}


def found(*urls: str) -> dict:
    """A preview answer with one entry per URL."""
    entries = [{"url": url, "title": f"Job {url[-1]}", "ambiguous": False, "duplicate": None,
                "login_walled": False} for url in urls]
    return EMPTY | {"entries": entries, "read_by": ["stub"]}


HELD = EMPTY | {"held": True}
NOT_SCREENED = EMPTY | {"model_skipped": "screening off"}


class StubFinder:
    """A finder in place of `alert_mail.preview`: the answer (or exception) for a mail is looked
    up by its plain text; every call is recorded as `(html, text)`. With `hold` set, a call
    signals `entered` and waits for `release` (the test's own events, never a sleep)."""

    def __init__(self, answers: dict[str, object] | None = None, hold: bool = False):
        self.answers, self.calls, self.hold = answers or {}, [], hold
        self.entered, self.release = threading.Event(), threading.Event()

    def __call__(self, intake, html, text, record):
        self.calls.append((html, text))
        if self.hold:
            self.entered.set()
            assert self.release.wait(10), "the test never released the finder"
        answer = self.answers.get(text.strip(), EMPTY)
        if isinstance(answer, Exception):
            raise answer
        return answer


class StubRuns:
    """An alert-run starter that records its entries and answers a fixed run ID."""

    def __init__(self):
        self.started, self.error = [], None

    def start(self, entries):
        if self.error:
            raise self.error
        self.started.append(list(entries))
        return "run-1"


def mail(uid: int, text: str | None = None, received: datetime | None = None, **parts) -> FakeMail:
    """A fake mail `uid` whose plain text is `mail <uid>` (or `text`), received an hour per UID
    after `DAY`; `parts` replace the text (`html=...`)."""
    body = {"text": text or f"mail {uid}"} | parts
    return FakeMail(uid, build_mail(f"<m{uid}@example.org>", subject=f"Subject {uid}", **body),
                    received or DAY + timedelta(hours=uid))


def imap(*mails: FakeMail, **options) -> FakeImap:
    return FakeImap({"Posteingang": FakeFolder(validity=7, mails=list(mails))},
                    password=PASSWORD, **options)


def connector(fake: FakeImap):
    """The `connect` factory over `fake`: the login runs through the real error mapping."""
    def connect(account, password):
        with imap_errors():
            fake.login(account.user, password)
        return fake
    return connect


def configure(root, since: date | None = SINCE, password: str | None = PASSWORD):
    update_mailbox_account(root, *ACCOUNT)
    if since is not None:
        update_mailbox(root, lambda current: current.model_copy(update={"since": since}))
    if password is not None:
        mailbox_secret.store(root / "pw", password, KEY)


@pytest.fixture
def root(tmp_path):
    configure(tmp_path)
    return tmp_path


def make(root, fake, finder=None, *, screening=True, key=KEY, runs=None, **options):
    guard = NoGuard() if screening else ContentGuard(None, {})
    intake = Intake(root, Untouchable(), guard)
    return MailboxChecks(intake, runs or StubRuns(), record=root / "record.jsonl",
                         password_file=root / "pw", key=key, connect=connector(fake),
                         finder=finder or StubFinder(), **options)


def settle(checks: MailboxChecks, check_id: str) -> dict:
    """The check's state once its worker has ended."""
    deadline = time.monotonic() + 10
    while (state := checks.read(check_id))["status"] == "running":
        assert time.monotonic() < deadline, "the check never ended"
        time.sleep(0.002)
    return state


def run(checks: MailboxChecks, since: date | None = None) -> dict:
    return settle(checks, checks.start(since))


def ref(uid: int, folder: str = "Posteingang") -> MailRef:
    return MailRef(folder, 7, uid, None)


def marked(record) -> set[int]:
    folder = record.uids.get("Posteingang")
    return set(folder.uids) if folder else set()


def handled(root) -> set[int]:
    return marked(read_mailbox(root).handled)


def waiting(root) -> set[int]:
    return marked(read_mailbox(root).waiting)


# --- start and read -----------------------------------------------------------------------


def test_a_check_reads_every_mail_oldest_first_through_the_finder(root):
    finder = StubFinder()
    state = run(make(root, imap(mail(3), mail(1), mail(2)), finder))
    assert state["status"] == "done" and (state["total"], state["read"]) == (3, 3)
    assert [text for _, text in finder.calls] == ["mail 1\n", "mail 2\n", "mail 3\n"]


def test_total_and_read_are_reported_while_the_check_runs(root):
    finder = StubFinder(hold=True)
    checks = make(root, imap(mail(1), mail(2)), finder)
    check_id = checks.start()
    assert finder.entered.wait(10)
    state = checks.read(check_id)
    assert (state["status"], state["total"], state["read"]) == ("running", 2, 0)
    finder.release.set()
    assert settle(checks, check_id)["read"] == 2


def test_a_second_check_is_refused_while_one_runs_and_names_it(root):
    finder = StubFinder(hold=True)
    checks = make(root, imap(mail(1)), finder)
    check_id = checks.start()
    assert finder.entered.wait(10)
    with pytest.raises(CheckBusyError) as busy:
        checks.start()
    assert busy.value.check_id == check_id
    finder.release.set()
    settle(checks, check_id)


def test_an_unknown_check_reads_as_none(root):
    assert make(root, imap()).read("nope") is None


def test_the_html_part_goes_to_the_finder_and_a_blank_one_falls_back_to_the_text(root):
    finder = StubFinder()
    run(make(root, imap(mail(1, html="<p>hello</p>", text="plain 1"),
                        mail(2, html="  \n ", text="plain 2")), finder))
    assert [(html and html.strip(), text.strip()) for html, text in finder.calls] == [
        ("<p>hello</p>", "plain 1"), (None, "plain 2")]


def test_a_mail_with_entries_is_offered_with_its_headers_and_marked_nothing(root):
    finder = StubFinder({"mail 1": found("https://jobs.example.org/a")})
    state = run(make(root, imap(mail(1), mail(2)), finder))
    offered, = state["mails"]
    assert (offered["folder"], offered["sender"], offered["subject"]) == (
        "Posteingang", "jobs@example.org", "Subject 1")
    assert offered["oversized"] is False and offered["read_failed"] is None
    assert offered["preview"]["entries"][0]["url"] == "https://jobs.example.org/a"
    assert handled(root) == {2}  # the empty mail at once; the offered one waits for the finish


def test_a_mail_without_postings_is_marked_handled_at_once_and_not_reported(root):
    state = run(make(root, imap(mail(1))))
    assert handled(root) == {1} and state["mails"] == [] and state["held"] == []


def test_a_held_mail_is_named_with_its_headers_and_marked_handled(root):
    state = run(make(root, imap(mail(1)), StubFinder({"mail 1": HELD})))
    held, = state["held"]
    assert (held["folder"], held["sender"], held["subject"]) == (
        "Posteingang", "jobs@example.org", "Subject 1")
    assert handled(root) == {1} and state["mails"] == []


def test_a_finder_error_fails_the_mail_unmarked_and_the_check_goes_on(root):
    finder = StubFinder({"mail 1": FinderError("finder failed")})
    state = run(make(root, imap(mail(1), mail(2)), finder))
    failed, = state["failed"]
    assert (failed["subject"], failed["reason"]) == ("Subject 1", "finder failed")
    assert (state["status"], state["read"]) == ("done", 2) and handled(root) == {2}


def test_a_mail_no_model_read_is_not_screened_and_waits(root):
    state = run(make(root, imap(mail(1)), StubFinder({"mail 1": NOT_SCREENED}), screening=False))
    not_screened, = state["not_screened"]
    assert not_screened["subject"] == "Subject 1"
    assert waiting(root) == {1} and handled(root) == set()


def test_waiting_mails_are_skipped_while_screening_is_off_and_read_when_it_is_on(root):
    fake = imap(mail(1))
    run(make(root, fake, StubFinder({"mail 1": NOT_SCREENED}), screening=False))
    skipped = StubFinder()
    assert run(make(root, fake, skipped, screening=False))["total"] == 0 and skipped.calls == []
    reading = StubFinder()
    state = run(make(root, fake, reading, screening=True))
    assert state["total"] == 1 and len(reading.calls) == 1
    assert handled(root) == {1} and waiting(root) == set()  # read now: handled, no longer waiting


def test_handled_mails_are_not_read_again(root):
    fake = imap(mail(1), mail(2))
    run(make(root, fake))
    again = StubFinder()
    assert run(make(root, fake, again))["total"] == 0 and again.calls == []


def test_a_mail_that_is_offered_but_not_finished_is_offered_again(root):
    fake = imap(mail(1))
    finder = StubFinder({"mail 1": found("https://jobs.example.org/a")})
    run(make(root, fake, finder))
    assert [m["subject"] for m in run(make(root, fake, finder))["mails"]] == ["Subject 1"]


def test_mails_older_than_the_start_date_are_not_read(root):
    old = mail(1, received=datetime(2026, 10, 20, 9, 0, tzinfo=UTC))
    finder = StubFinder()
    assert run(make(root, imap(old, mail(2)), finder))["total"] == 1


def test_the_first_check_stores_the_start_date_after_the_login(tmp_path):
    configure(tmp_path, since=None)
    fake = imap(mail(1))
    state = run(make(tmp_path, fake), since=SINCE)
    assert state["status"] == "done" and read_mailbox(tmp_path).since == SINCE


def test_a_stored_start_date_wins_over_the_one_given(root):
    run(make(root, imap(mail(1))), since=date(2026, 1, 1))
    assert read_mailbox(root).since == SINCE


def test_the_first_check_without_a_start_date_is_refused(tmp_path):
    configure(tmp_path, since=None)
    with pytest.raises(ValueError, match="start date"):
        make(tmp_path, imap(mail(1))).start()


def test_a_check_without_a_mailbox_is_refused(tmp_path):
    with pytest.raises(LookupError, match="configured"):
        make(tmp_path, imap(mail(1))).start()


def test_the_time_of_the_last_check_is_set_when_it_is_done(root):
    assert read_mailbox(root).last_check_at is None
    run(make(root, imap(mail(1))))
    assert read_mailbox(root).last_check_at is not None


def test_remaining_and_missing_folders_are_reported(root):
    update_mailbox(root, lambda current: current.model_copy(update={
        "max_mails": 2, "folders": Folders(names=["Posteingang", "Jobs"])}))
    state = run(make(root, imap(mail(1), mail(2), mail(3))))
    assert (state["total"], state["remaining"], state["missing_folders"]) == (2, 1, ["Jobs"])


def test_the_mailbox_is_only_read(root):
    fake = imap(mail(1), mail(2))
    run(make(root, fake))
    assert fake.violations == [] and fake.calls[-1] == ("logout",)


# --- oversized mails ----------------------------------------------------------------------


def test_an_oversized_mail_is_offered_unread_and_not_marked(root):
    big = mail(1, html="<p>" + "x" * 2_000_001 + "</p>")
    finder = StubFinder()
    state = run(make(root, imap(big), finder))
    offered, = state["mails"]
    assert offered["oversized"] is True and offered["preview"] is None
    assert finder.calls == [] and handled(root) == set() and waiting(root) == set()


def test_both_parts_count_together_toward_the_limit(root):
    half = "x" * 1_000_001
    state = run(make(root, imap(mail(1, html=f"<p>{half}</p>", text=half)), StubFinder()))
    assert state["mails"][0]["oversized"] is True


def test_a_large_attachment_does_not_count(root):
    message = message_from_bytes(mail(1, html="<p>" + "y" * 80_000 + "</p>").raw,
                                 policy=policy.default)
    message.add_attachment(b"z" * 3_000_000, maintype="application", subtype="pdf",
                           filename="cv.pdf")
    big_attachment = FakeMail(1, message.as_bytes(), DAY)
    finder = StubFinder()
    state = run(make(root, imap(big_attachment), finder))
    assert len(finder.calls) == 1 and state["mails"] == [] and handled(root) == {1}


# --- finish -------------------------------------------------------------------------------

A, B, C = (f"https://jobs.example.org/{name}" for name in "abc")


def offering(root, *, screening=True, runs=None):
    """A done check over mails 1 (offers A and B), 2 (offers C), 3 (no posting), 4 (fails) and
    5 (held): returns `(checks, check_id, runs, fake)`."""
    finder = StubFinder({"mail 1": found(A, B), "mail 2": found(C), "mail 4": FinderError("x"),
                         "mail 5": HELD})
    fake = imap(*(mail(uid) for uid in range(1, 6)))
    runs = runs or StubRuns()
    checks = make(root, fake, finder, screening=screening, runs=runs)
    return checks, checks.start(), runs, fake


def test_finishing_with_no_entries_marks_the_offered_mails_and_starts_no_run(root):
    checks, check_id, runs, _ = offering(root)
    settle(checks, check_id)
    assert handled(root) == {3, 5} and checks.current() == check_id
    assert checks.finish(check_id, []) is None
    assert runs.started == [] and handled(root) == {1, 2, 3, 5}
    assert checks.read(check_id)["status"] == "finished" and checks.current() is None


def test_finishing_starts_one_run_with_the_chosen_entries_and_marks_the_mails(root):
    checks, check_id, runs, _ = offering(root)
    settle(checks, check_id)
    chosen = [RunEntry(A, "Job a"), RunEntry(C, "Job c", force=True)]
    assert checks.finish(check_id, chosen) == "run-1"
    assert runs.started == [chosen] and handled(root) == {1, 2, 3, 5}


def test_more_than_a_hundred_entries_go_into_one_run(root):
    urls = [f"https://jobs.example.org/job{n}" for n in range(140)]
    checks = make(root, imap(mail(1)), StubFinder({"mail 1": found(*urls)}))
    check_id = checks.start()
    settle(checks, check_id)
    runs = checks._alert_runs
    assert checks.finish(check_id, [RunEntry(url, "t") for url in urls]) == "run-1"
    assert len(runs.started) == 1 and len(runs.started[0]) == 140


def test_a_failed_mail_and_a_screening_off_mail_are_never_marked_handled(root):
    finder = StubFinder({"mail 1": found(A), "mail 2": NOT_SCREENED,
                         "mail 3": FinderError("finder failed")})
    checks = make(root, imap(mail(1), mail(2), mail(3)), finder, screening=False)
    check_id = checks.start()
    settle(checks, check_id)
    checks.finish(check_id, [])
    assert handled(root) == {1} and waiting(root) == {2}


def test_a_link_the_check_did_not_offer_is_refused_and_nothing_changes(root):
    checks, check_id, runs, _ = offering(root)
    settle(checks, check_id)
    with pytest.raises(EntryNotOfferedError):
        checks.finish(check_id, [RunEntry(A, "a"), RunEntry("https://other.example.org/x", "x")])
    assert runs.started == [] and handled(root) == {3, 5}
    assert checks.read(check_id)["status"] == "done"


def test_a_busy_alert_run_leaves_everything_unmarked_and_the_pick_list_open(root):
    runs = StubRuns()
    runs.error = AlertRunBusyError("run-0")
    checks, check_id, _, _ = offering(root, runs=runs)
    settle(checks, check_id)
    with pytest.raises(AlertRunBusyError):
        checks.finish(check_id, [RunEntry(A, "a")])
    assert handled(root) == {3, 5} and checks.read(check_id)["status"] == "done"
    runs.error = None
    assert checks.finish(check_id, [RunEntry(A, "a")]) == "run-1"


def test_a_second_finish_is_refused(root):
    checks, check_id, runs, _ = offering(root)
    settle(checks, check_id)
    checks.finish(check_id, [RunEntry(A, "a")])
    with pytest.raises(CheckNotDoneError):
        checks.finish(check_id, [RunEntry(A, "a")])
    assert len(runs.started) == 1


def test_a_double_click_starts_exactly_one_run(root):
    checks, check_id, runs, _ = offering(root)
    settle(checks, check_id)
    results = []

    def click():
        try:
            results.append(checks.finish(check_id, [RunEntry(A, "a")]))
        except CheckNotDoneError as refused:
            results.append(refused)

    threads = [threading.Thread(target=click) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert len(runs.started) == 1 and results.count("run-1") == 1


def test_a_check_that_is_running_failed_or_unknown_cannot_be_finished(root):
    finder = StubFinder(hold=True)
    checks = make(root, imap(mail(1)), finder)
    check_id = checks.start()
    assert finder.entered.wait(10)
    with pytest.raises(CheckNotDoneError):
        checks.finish(check_id, [])
    finder.release.set()
    settle(checks, check_id)
    keyless = make(root, imap(mail(1)), key=None)
    with pytest.raises(CheckNotDoneError):
        keyless.finish(run(keyless)["check_id"], [])
    with pytest.raises(KeyError):
        checks.finish("nope", [])


def test_an_unread_oversized_mail_is_marked_handled_by_the_finish(root):
    big = mail(1, html="<p>" + "x" * 2_000_001 + "</p>")
    checks = make(root, imap(big, mail(2)), StubFinder({"mail 2": found(A)}))
    check_id = checks.start()
    state = settle(checks, check_id)
    assert [m["oversized"] for m in state["mails"]] == [True, False] and handled(root) == set()
    checks.finish(check_id, [])
    assert handled(root) == {1, 2}


def test_the_next_check_does_not_offer_the_mails_of_a_finished_pick_list(root):
    checks, check_id, _, fake = offering(root)
    settle(checks, check_id)
    checks.finish(check_id, [])
    assert run(make(root, fake, StubFinder({"mail 4": found(A)})))["total"] == 1  # only mail 4


# --- cancel -------------------------------------------------------------------------------


def test_a_cancel_stops_after_the_current_mail_and_keeps_the_marks_of_the_mails_read(root):
    finder = StubFinder({"mail 1": found(A)}, hold=True)
    fake = imap(*(mail(uid) for uid in range(1, 5)))
    checks = make(root, fake, finder)
    check_id = checks.start()
    assert finder.entered.wait(10)
    assert checks.cancel(check_id) == check_id
    assert checks.read(check_id)["cancel_requested"] is True  # while mail 1 finishes
    finder.release.set()
    state = settle(checks, check_id)
    assert (state["status"], state["cancelled"], state["read"], state["total"]) == (
        "done", True, 1, 4)
    assert len(finder.calls) == 1 and [m["subject"] for m in state["mails"]] == ["Subject 1"]
    assert handled(root) == set() and read_mailbox(root).last_check_at is not None


def test_a_cancel_before_the_first_mail_reads_none(root):
    release, entered = threading.Event(), threading.Event()
    fake = imap(mail(1), mail(2))
    inner = connector(fake)

    def slow(account, password):
        entered.set()
        assert release.wait(10)
        return inner(account, password)

    finder = StubFinder()
    checks = make(root, fake, finder)
    checks._connect = slow
    check_id = checks.start()
    assert entered.wait(10)
    checks.cancel(check_id)
    release.set()
    state = settle(checks, check_id)
    assert (state["cancelled"], state["read"], state["total"]) == (True, 0, 2)
    assert finder.calls == [] and handled(root) == set()


def test_the_mails_a_cancelled_check_did_not_read_are_read_by_the_next_check(root):
    finder = StubFinder(hold=True)
    fake = imap(mail(1), mail(2), mail(3))
    checks = make(root, fake, finder)
    check_id = checks.start()
    assert finder.entered.wait(10)
    checks.cancel(check_id)
    finder.release.set()
    settle(checks, check_id)
    assert handled(root) == {1}
    assert run(make(root, fake, StubFinder()))["total"] == 2


def test_a_cancelled_checks_pick_list_finishes_like_any_other(root):
    finder = StubFinder({"mail 1": found(A)}, hold=True)
    checks = make(root, imap(mail(1), mail(2)), finder)
    check_id = checks.start()
    assert finder.entered.wait(10)
    checks.cancel(check_id)
    finder.release.set()
    settle(checks, check_id)
    assert checks.current() == check_id
    assert checks.finish(check_id, [RunEntry(A, "a")]) == "run-1" and handled(root) == {1}


def test_a_cancel_after_the_last_mail_leaves_a_plain_done_check(root):
    finder = StubFinder(hold=True)
    checks = make(root, imap(mail(1)), finder)
    check_id = checks.start()
    assert finder.entered.wait(10)
    checks.cancel(check_id)
    finder.release.set()
    state = settle(checks, check_id)
    assert state["cancelled"] is False and state["read"] == 1


def test_a_cancel_is_refused_for_a_check_that_is_not_running_and_unknown_for_a_stranger(root):
    checks = make(root, imap(mail(1)), StubFinder({"mail 1": found(A)}))
    done = run(checks)["check_id"]
    with pytest.raises(CheckNotRunningError):
        checks.cancel(done)
    checks.finish(done, [])
    with pytest.raises(CheckNotRunningError):
        checks.cancel(done)  # finished
    keyless = make(root, imap(mail(1)), key=None)
    with pytest.raises(CheckNotRunningError):
        keyless.cancel(run(keyless)["check_id"])  # failed
    assert checks.cancel("nope") is None


# --- the password never leaves ------------------------------------------------------------


class Chatty(FakeImap):
    """The class the real `connect` builds in place of `IMAPClient`, with imaplib's debug output
    on: its login logs the whole LOGIN line, password included, at DEBUG like the real one."""

    def __init__(self, *args, **kwargs):
        super().__init__({"Posteingang": FakeFolder(validity=7, mails=[mail(1), mail(2)])},
                         password=PASSWORD)

    def login(self, user, password):
        logging.getLogger("imapclient.imaplib").debug("> LOGIN %s %s", user, password)
        super().login(user, password)


def everything_written(root) -> bytes:
    return b"".join(path.read_bytes() for path in root.rglob("*") if path.is_file())


@pytest.mark.parametrize("stored", [PASSWORD, "wrong-password-marker"])
def test_a_whole_check_at_debug_level_never_logs_or_answers_the_password(
        root, caplog, monkeypatch, stored):
    monkeypatch.setattr(mailbox, "IMAPClient", Chatty)
    mailbox_secret.store(root / "pw", stored, KEY)
    checks = MailboxChecks(Intake(root, Untouchable(), NoGuard()), StubRuns(),
                           record=root / "record.jsonl", password_file=root / "pw", key=KEY,
                           finder=StubFinder({"mail 1": found(A)}))
    caplog.set_level(logging.DEBUG)
    state = run(checks)
    assert state["status"] == ("done" if stored == PASSWORD else "failed")
    logged = caplog.text + "".join(repr(record.args) for record in caplog.records)
    for place in (logged, repr(state), repr(checks.read(state["check_id"])),
                  everything_written(root).decode(errors="replace")):
        assert stored not in place
    if stored == PASSWORD:
        checks.finish(state["check_id"], [])
        assert PASSWORD not in everything_written(root).decode(errors="replace")


# --- failure paths ------------------------------------------------------------------------

SERVER_TEXT = "Hello name@example.org, your secret is unknown to us"


def failing_connect(error: BaseException):
    """A `connect` whose attempt raises `error` through the real error mapping."""
    def connect(account, password):
        with imap_errors():
            raise error
    return connect


class Dropping(FakeImap):
    """A fake whose connection drops on every mail body fetch after the first `allowed`."""

    def __init__(self, *args, allowed: int, **kwargs):
        super().__init__(*args, **kwargs)
        self.allowed = allowed

    def fetch(self, uids, items):
        if items == ["BODY.PEEK[]"]:
            if self.allowed <= 0:
                raise ConnectionResetError(SERVER_TEXT)
            self.allowed -= 1
        return super().fetch(uids, items)


def logged_in(fake: FakeImap) -> bool:
    return any(call[0] == "login" for call in fake.calls)


@pytest.mark.parametrize("key", [None, "", "not-a-fernet-key"])
def test_without_a_valid_key_the_check_fails_with_no_key_and_attempts_no_login(root, key):
    fake = imap(mail(1))
    state = run(make(root, fake, key=key))
    assert (state["status"], state["reason"]) == ("failed", "no key") and fake.calls == []


def test_without_a_password_the_check_fails_with_no_password_and_attempts_no_login(tmp_path):
    configure(tmp_path, password=None)
    fake = imap(mail(1))
    state = run(make(tmp_path, fake))
    assert (state["status"], state["reason"]) == ("failed", "no password") and fake.calls == []


def test_a_password_the_key_cannot_decrypt_is_unreadable_and_attempts_no_login(root):
    fake = imap(mail(1))
    state = run(make(root, fake, key=Fernet.generate_key().decode()))
    assert (state["status"], state["reason"]) == ("failed", "password unreadable")
    assert fake.calls == []


@pytest.mark.parametrize("error, reason", [
    (TimeoutError(SERVER_TEXT), "unreachable"),
    (ssl.SSLCertVerificationError(1, SERVER_TEXT), "certificate"),
    (ssl.SSLError(1, SERVER_TEXT), "protocol"),
    (ConnectionResetError(SERVER_TEXT), "protocol")])
def test_a_connection_failure_names_its_reason_without_the_servers_text(root, error, reason):
    checks = make(root, imap(mail(1)))
    checks._connect = failing_connect(error)
    state = run(checks)
    assert (state["status"], state["reason"]) == ("failed", reason)
    assert SERVER_TEXT not in repr(state) and handled(root) == set()


def test_a_refused_login_fails_the_check_and_stores_no_start_date(tmp_path):
    configure(tmp_path, since=None, password="wrong password")
    state = run(make(tmp_path, imap(mail(1))), since=SINCE)
    assert (state["status"], state["reason"]) == ("failed", "login")
    assert read_mailbox(tmp_path).since is None and handled(tmp_path) == set()


def test_a_folder_that_cannot_be_selected_fails_the_check_and_marks_nothing(root):
    fake = imap(mail(1), errors={"select_folder": imaplib.IMAP4.error(SERVER_TEXT)})
    state = run(make(root, fake))
    assert (state["status"], state["reason"]) == ("failed", "folder")
    assert handled(root) == set() and read_mailbox(root).last_check_at is None


def test_a_failure_while_listing_the_folders_fails_the_check(root):
    fake = imap(mail(1), errors={"list_folders": ConnectionResetError(SERVER_TEXT)})
    state = run(make(root, fake))
    assert (state["status"], state["reason"]) == ("failed", "protocol")
    assert SERVER_TEXT not in repr(state)


def test_a_failed_check_does_not_set_the_time_of_the_last_check(root):
    run(make(root, imap(mail(1)), key=None))
    assert read_mailbox(root).last_check_at is None


def test_a_connection_lost_while_reading_keeps_what_was_read(root):
    fake = Dropping({"Posteingang": FakeFolder(validity=7, mails=[mail(1), mail(2), mail(3)])},
                    password=PASSWORD, allowed=2)
    finder = StubFinder({"mail 1": found("https://jobs.example.org/a")})
    state = run(make(root, fake, finder))
    assert (state["status"], state["interrupted"], state["read"], state["total"]) == (
        "done", "protocol", 2, 3)
    assert [m["subject"] for m in state["mails"]] == ["Subject 1"] and handled(root) == {2}
    assert SERVER_TEXT not in repr(state)
    again = StubFinder()
    assert run(make(root, imap(mail(1), mail(2), mail(3)), again))["total"] == 2  # 1 offered, 3 new


def test_a_connection_lost_before_the_first_mail_is_a_failed_check(root):
    fake = Dropping({"Posteingang": FakeFolder(validity=7, mails=[mail(1)])},
                    password=PASSWORD, allowed=0)
    state = run(make(root, fake))
    assert (state["status"], state["reason"], state["interrupted"]) == ("failed", "protocol", None)
    assert handled(root) == set()


# --- the real finder ----------------------------------------------------------------------


def test_a_known_sender_is_read_by_its_rule_and_no_model_is_called(demo_copy):
    configure(demo_copy)
    raw = build_mail("<linkedin@example.org>", html=fixture("linkedin-digest.html"))
    fake = imap(FakeMail(1, raw, DAY))
    intake = Intake(demo_copy, Untouchable(), NoGuard())
    checks = MailboxChecks(intake, StubRuns(), record=demo_copy / "record.jsonl",
                           password_file=demo_copy / "pw", key=KEY, connect=connector(fake))
    offered, = run(checks)["mails"]
    assert offered["preview"]["read_by"] == ["linkedin"]
    assert len(offered["preview"]["entries"]) == 6
