"""The background mailbox check (`design.md` D4): one check at a time reads the unhandled mails of
the searched folders through the finder, reports what it found and marks what it handled. State
lives in memory only. Lock order: this object's lock first, then `write_gate`; the finder and
every IMAP call run outside the lock.

Lives next to `mailbox.py` (the IMAP access) because the check class outgrew that file.
"""

import copy
import logging
import threading
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from imapclient import IMAPClient

from jobadvaisor import mailbox_secret
from jobadvaisor.data.models import Mailbox, MailRef
from jobadvaisor.data.writer import mark_mails, read_mailbox, update_mailbox
from jobadvaisor.intake import alert_mail
from jobadvaisor.intake.alert_mail import FinderError
from jobadvaisor.intake.alert_runs import AlertRuns, RunEntry
from jobadvaisor.intake.mailbox import (
    Candidate,
    Folder,
    MailboxError,
    find_candidates,
    imap_errors,
    list_folders,
    mail_parts,
    parse_mail,
    searched_folders,
)
from jobadvaisor.intake.mailbox import (
    connect as real_connect,
)
from jobadvaisor.intake.postings import Intake

Finder = Callable[[Intake, str | None, str, Path], dict]
Connect = Callable[[Mailbox, str], IMAPClient]
MAX_HEADER = 200  # characters of a displayed sender or subject
log = logging.getLogger(__name__)


class CheckBusyError(Exception):
    """Another mailbox check computes; `check_id` names it."""

    def __init__(self, check_id: str):
        self.check_id = check_id
        super().__init__(f"mailbox check {check_id} is still computing")


class NotConfiguredError(LookupError):
    """No mailbox is configured."""


class SinceRequiredError(ValueError):
    """The first check needs a start date and got none."""


class CheckNotDoneError(Exception):
    """The check is not `done`: it still runs, failed, or its pick list is finished or closed."""


class CheckNotRunningError(Exception):
    """The check is `done`, `failed` or `finished`, so it takes no cancel."""


class NotOversizedError(Exception):
    """The mail is not an unread oversized mail: it was read or never was oversized."""


class ReadInProgressError(Exception):
    """An oversized mail of the pending pick list is being read, so it cannot be finished or
    replaced yet."""


class EntryNotOfferedError(ValueError):
    """An entry's link is not one the check offered; `url` names it."""

    def __init__(self, url: str):
        self.url = url
        super().__init__(f"the check did not offer {url}")


@dataclass
class _Check:
    """One check: the `state` that `read` answers, the `refs` of the mails in its pick list by
    key, and the `kept` parts of its unread oversized mails by key. The last two never leave
    this module."""

    state: dict
    refs: dict[str, MailRef] = field(default_factory=dict)
    kept: dict[str, tuple[str | None, str]] = field(default_factory=dict)


def _header(message, name: str) -> str:
    try:
        return " ".join(str(message[name] or "").split())[:MAX_HEADER]
    except Exception:  # a malformed header shows as blank, it never fails the check
        return ""


def _display(message, candidate: Candidate) -> dict:
    """The headers a report shows for a mail: its folder, sender, subject and date. Never stored."""
    try:
        sent = message["Date"].datetime.isoformat()
    except Exception:  # missing or malformed: the server's own date stands in
        sent = candidate.received.isoformat()
    return {"folder": candidate.folder, "sender": _header(message, "From"),
            "subject": _header(message, "Subject"), "date": sent}


def _waits(answer: dict) -> bool:
    """Whether an answer means no model read the mail because screening is off."""
    return answer["model_skipped"] == "screening off"


class MailboxChecks:
    """Starts and reads mailbox checks over the data repository of `intake`, one at a time.
    `alert_runs` adds the entries of a finished pick list. `record` is the finder's
    `alert-mails.jsonl`, `password_file` the encrypted password, `key` its Fernet key. `connect`
    (the real factory by default) and `finder` (`alert_mail.preview`) are replaced in tests."""

    def __init__(self, intake: Intake, alert_runs: AlertRuns, *, record: Path,
                 password_file: Path, key: str | None, connect: Connect = real_connect,
                 finder: Finder = alert_mail.preview):
        self._intake, self._alert_runs, self._record = intake, alert_runs, record
        self._password_file, self._key = password_file, key
        self._connect, self._finder = connect, finder
        self._root = intake.root
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._lock = threading.Lock()
        self._checks: dict[str, _Check] = {}
        self._computing: str | None = None
        self._pending: str | None = None

    def start(self, since: date | None = None) -> str:
        """Check the mailbox in the background and return the check's ID at once; `read`
        reports `total` once the candidates are known. `since` is the start date of the first
        check: a stored one always wins, and it is stored only after a successful login. A
        check that fails (no key, no password, the server) answers an ID too and ends `failed`
        with its `reason`. Replaces the pending pick list. Raises `CheckBusyError`,
        `NotConfiguredError` and `SinceRequiredError`."""
        check_id = uuid.uuid4().hex
        with self._lock:
            if self._computing:
                raise CheckBusyError(self._computing)
            self._refuse_while_reading()
            account = read_mailbox(self._root)
            if account is None:
                raise NotConfiguredError("no mailbox is configured")
            if account.since is None and since is None:
                raise SinceRequiredError("a start date is required for the first check")
            self._drop_pending()
            self._computing = check_id
            self._checks[check_id] = _Check({
                "check_id": check_id, "status": "running", "reason": None, "error": None,
                "interrupted": None, "cancel_requested": False, "cancelled": False,
                "total": 0, "read": 0, "remaining": 0, "mails": [], "failed": [], "held": [],
                "not_screened": [], "missing_folders": []})
        try:
            self._executor.submit(self._run, check_id, account, since)
        except Exception:
            with self._lock:
                self._computing = None
                del self._checks[check_id]
            raise
        return check_id

    def folders(self) -> list[Folder]:
        """The account's folders, read over a login with the stored password that is closed
        again (`intake.mailbox.list_folders`). Raises `NotConfiguredError` and `MailboxError`
        (`no key`, `no password`, `password unreadable`, or the connection's reason)."""
        account = read_mailbox(self._root)
        if account is None:
            raise NotConfiguredError("no mailbox is configured")
        client = self._connect(account, self._password())
        try:
            return list_folders(client)
        finally:
            with suppress(Exception):
                client.logout()

    def current(self) -> str | None:
        """The ID of the running check, else of the pending one (a `done` check whose pick
        list is not finished), else `None`."""
        with self._lock:
            return self._computing or self._pending

    def read(self, check_id: str) -> dict | None:
        """A copy of the check's state, or `None` for an unknown ID: `check_id`, `status`
        (`running`, `done`, `failed`, `finished`), `reason` (a failed check's, one of
        `intake.mailbox.REASONS`), `error` (the exception's type name when the worker crashed),
        `interrupted` (the reason a `done` check lost its connection), `cancel_requested`,
        `cancelled`, `total` (mails to read), `read`, `remaining` (unhandled mails left for the
        next check), `missing_folders`, and the reports `mails` (the pick list), `failed`,
        `held` and `not_screened`. A mail of `mails` is `{key, folder, sender, subject, date,
        oversized, reading, read_failed, preview}` with `preview` the finder's answer or `None`
        for an unread oversized mail; the other reports hold `{folder, sender, subject, date}`
        and, for `failed`, `reason`. Never the kept parts of an oversized mail."""
        with self._lock:
            check = self._checks.get(check_id)
            return copy.deepcopy(check.state) if check else None

    def read_oversized(self, check_id: str, key: str) -> dict:
        """Read the unread oversized mail `key` of a `done` check on request, like a pasted
        mail, and answer that mail (as in `read`) with its `preview`; its entries join the
        offer. The finder runs in the caller's thread, outside the lock, while the mail shows
        `reading: true`, so no finish, second read, new check or account change can slip in
        before the answer lands. A `FinderError` propagates and leaves `read_failed` on the
        mail, which stays readable and, when the pick list is finished, unmarked. The kept parts
        are dropped once the mail is read. Raises `KeyError` (unknown check or key),
        `CheckNotDoneError`, `ReadInProgressError` (this mail is being read) and
        `NotOversizedError`."""
        with self._lock:
            check = self._checks.get(check_id)
            if check is None:
                raise KeyError(check_id)
            if check.state["status"] != "done":
                raise CheckNotDoneError(f"check {check_id} is {check.state['status']}, not done")
            mail = next((mail for mail in check.state["mails"] if mail["key"] == key), None)
            if mail is None:
                raise KeyError(key)
            if mail["reading"]:
                raise ReadInProgressError(f"mail {key} is being read")
            if not mail["oversized"] or mail["preview"] is not None:
                raise NotOversizedError(f"mail {key} is not an unread oversized mail")
            html, text = check.kept[key]
            mail["reading"] = True
        try:
            answer = self._finder(self._intake, html, text, self._record)
        except BaseException as error:  # whatever it was, the mail is free to read again
            with self._lock:
                mail["reading"] = False
                if isinstance(error, FinderError):
                    mail["read_failed"] = str(error)
            raise
        with self._lock:
            mail |= {"preview": answer, "reading": False, "read_failed": None}
            check.kept.pop(key, None)
            return copy.deepcopy(mail)

    @contextmanager
    def account_change(self) -> Iterator[None]:
        """Hold the lock around a change of the account (host or user) so no check starts
        meanwhile; the pending pick list and its kept parts are dropped when the block ends
        without an exception. Raises `CheckBusyError` while a check runs and
        `ReadInProgressError` while an oversized mail is being read. Code in the block must not
        call another method of this object."""
        with self._lock:
            if self._computing:
                raise CheckBusyError(self._computing)
            self._refuse_while_reading()
            yield
            self._drop_pending()

    def _refuse_while_reading(self) -> None:
        """Raise `ReadInProgressError` while a mail of the pending pick list is being read. The
        lock is held."""
        pending = self._checks.get(self._pending) if self._pending else None
        if pending and any(mail["reading"] for mail in pending.state["mails"]):
            raise ReadInProgressError("an oversized mail of the pending pick list is being read")

    def cancel(self, check_id: str) -> str | None:
        """Ask the running check to stop; returns its ID at once. The worker looks for the
        request before each mail, so the mail it works on is finished and filed, then the check
        ends `done` with `cancelled` and the mails read so far, and the rest stay unmarked. A
        request that arrives while the candidates are searched takes effect before the first
        mail. Answers `None` for an unknown ID and raises `CheckNotRunningError` for a check
        that has ended."""
        with self._lock:
            check = self._checks.get(check_id)
            if check is None:
                return None
            if check.state["status"] != "running":
                raise CheckNotRunningError(f"check {check_id} is {check.state['status']}")
            check.state["cancel_requested"] = True
            return check_id

    def finish(self, check_id: str, entries: list[RunEntry]) -> str | None:
        """Finish the pick list of a `done` check: `entries` (none up to all offered, their
        links already cleaned) go into one alert run, and the mails of the pick list, unread
        oversized ones included, count as handled; a mail whose read on request failed stays
        unmarked and one no model read waits. Answers the run's ID, or `None` without
        entries. Everything runs under the lock, so a second finish (a double click) is
        refused. Raises `KeyError` (unknown check), `CheckNotDoneError`, `ReadInProgressError`,
        `EntryNotOfferedError`, and `AlertRunBusyError` with nothing marked."""
        with self._lock:
            check = self._open(check_id)
            offered = {entry["url"] for mail in check.state["mails"] if mail["preview"]
                       for entry in mail["preview"]["entries"]}
            for entry in entries:
                if entry.url not in offered:
                    raise EntryNotOfferedError(entry.url)
            run_id = self._alert_runs.start(entries) if entries else None
            handled, waiting = [], []
            for mail in check.state["mails"]:
                if not mail["read_failed"]:
                    preview = mail["preview"]
                    (waiting if preview and _waits(preview) else handled).append(
                        check.refs[mail["key"]])
            try:
                mark_mails(self._root, handled=handled, waiting=waiting)
            except BaseException:
                if run_id:  # the run has started: a second finish would start another
                    # ponytail: the mails stay unmarked and come again in the next check, whose
                    # run reports their entries as duplicates by link; retry marking if it matters
                    self._close(check_id)
                raise
            self._close(check_id)
            return run_id

    def _open(self, check_id: str) -> _Check:
        """The `done` check whose pick list is open and has no mail being read. The lock is
        held. Raises `KeyError`, `CheckNotDoneError` or `ReadInProgressError`."""
        check = self._checks.get(check_id)
        if check is None:
            raise KeyError(check_id)
        if check.state["status"] != "done":
            raise CheckNotDoneError(f"check {check_id} is {check.state['status']}, not done")
        if any(mail["reading"] for mail in check.state["mails"]):
            raise ReadInProgressError(f"an oversized mail of check {check_id} is being read")
        return check

    def _close(self, check_id: str) -> None:
        """End a check's pick list: drop its kept parts and mark it `finished`. The lock is
        held."""
        check = self._checks[check_id]
        check.kept.clear()
        check.state["status"] = "finished"
        if self._pending == check_id:
            self._pending = None

    def _drop_pending(self) -> None:
        """Close the pending pick list and its kept parts. The lock is held."""
        if self._pending:
            self._close(self._pending)

    def _run(self, check_id: str, account: Mailbox, since: date | None) -> None:
        check = self._checks[check_id]
        status, client = "done", None
        try:
            client = self._connect(account, self._password())
            if account.since is None:
                update_mailbox(self._root, lambda current: current.model_copy(
                    update={"since": since}) if current.since is None else current)
            self._read_all(client, check, account)
        except MailboxError as error:
            status = "failed"
            with self._lock:
                check.state["reason"] = error.reason
        except Exception as crash:  # the thread must not die silently
            status = "failed"
            with self._lock:
                check.state["error"] = type(crash).__name__
        finally:
            if client is not None:
                with suppress(Exception):
                    client.logout()
            error = None
            if status == "done":
                try:
                    update_mailbox(self._root, lambda current: current.model_copy(
                        update={"last_check_at": datetime.now(UTC)}))
                except Exception as crash:  # the slot must be freed whatever happens
                    status, error = "failed", type(crash).__name__
            with self._lock:
                if error:
                    check.state["error"] = error
                check.state["status"] = status
                self._computing = None
                if status == "done" and check.state["mails"]:
                    self._pending = check_id

    def _password(self) -> str:
        """The stored password in plain text, for the one login that needs it: it is never kept
        on this object, never logged and never part of an exception. Raises `MailboxError`
        (`no key`, `password unreadable`, `no password`) before any login is attempted."""
        if not mailbox_secret.key_configured(self._key):
            raise MailboxError("no key")
        try:
            password = mailbox_secret.read(self._password_file, self._key)
        except mailbox_secret.PasswordUnreadable:
            raise MailboxError("password unreadable") from None
        if password is None:
            raise MailboxError("no password")
        return password

    def _read_all(self, client: IMAPClient, check: _Check, account: Mailbox) -> None:
        state = check.state
        mailbox = read_mailbox(self._root)
        screening = self._intake.guard.classifier is not None
        skip = [mailbox.handled] + ([] if screening else [mailbox.waiting])
        searched, missing = searched_folders(list_folders(client), account.folders)
        candidates = find_candidates(client, searched, mailbox.since, skip, account.max_mails)
        with self._lock:
            state |= {"total": candidates.total, "remaining": candidates.remaining,
                      "missing_folders": missing}
        selected = None
        try:
            for index, candidate in enumerate(candidates.mails):
                with self._lock:
                    if state["cancel_requested"]:
                        state["cancelled"] = True
                        break
                if selected != candidate.folder:
                    with imap_errors():
                        client.select_folder(candidate.folder, readonly=True)
                    selected = candidate.folder
                with imap_errors():
                    raw = client.fetch([candidate.uid], ["BODY.PEEK[]"]).get(
                        candidate.uid, {}).get(b"BODY[]")
                if raw is not None:  # a mail deleted since the search is simply gone
                    try:
                        self._read_mail(check, str(index), candidate, raw)
                    except Exception as crash:  # one mail never fails the check
                        log.warning("mailbox check %s: mail %d failed unexpectedly (%s)",
                                    state["check_id"], index, type(crash).__name__)
                        with self._lock:
                            state["failed"].append({
                                "folder": candidate.folder, "sender": "", "subject": "",
                                "date": candidate.received.isoformat(),
                                "reason": "finder failed"})
                with self._lock:
                    state["read"] += 1
        except MailboxError as error:
            if not state["read"]:
                raise  # nothing read yet: the check fails with the reason
            with self._lock:
                state["interrupted"] = error.reason

    def _read_mail(self, check: _Check, key: str, candidate: Candidate, raw: bytes) -> None:
        """Pass one fetched mail to the finder and file the answer in the check and the marks:
        offered mails stay unmarked until the pick list is finished, failed ones stay unmarked,
        held and empty ones are handled at once, and screening-off ones wait."""
        message = parse_mail(raw)
        html, text = mail_parts(message)
        head = _display(message, candidate)
        mail = head | {"key": key, "oversized": False, "reading": False, "read_failed": None,
                       "preview": None}
        if len(html or "") + len(text) > alert_mail.MAX_MAIL:
            with self._lock:
                mail["oversized"] = True
                check.state["mails"].append(mail)
                check.refs[key], check.kept[key] = candidate, (html, text)
            return
        try:
            answer = self._finder(self._intake, html, text, self._record)
        except FinderError as error:
            with self._lock:
                check.state["failed"].append(head | {"reason": str(error)})
            return
        if answer["entries"]:
            with self._lock:
                check.state["mails"].append(mail | {"preview": answer})
                check.refs[key] = candidate
        elif _waits(answer):
            mark_mails(self._root, waiting=[candidate])
            with self._lock:
                check.state["not_screened"].append(head)
        else:
            mark_mails(self._root, handled=[candidate])
            if answer["held"]:
                with self._lock:
                    check.state["held"].append(head)
