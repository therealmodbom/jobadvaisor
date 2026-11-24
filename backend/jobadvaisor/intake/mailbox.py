"""Reading job alert mails from an IMAP mailbox (`design.md` D2, D4, D5).

This module holds the access layer: the `connect` factory, the one mapping from every IMAP
error to a fixed reason code, the folder rules, the candidate search and `mail_parts`. The
password only ever passes through `connect` into `login`; no reason, log line or exception text
carries it, and none carries text from the server, which may echo the user name.
"""

import email
import email.policy
import imaplib
import logging
import socket
import ssl
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import date, datetime
from email.message import EmailMessage
from typing import Literal

from imapclient import IMAPClient
from imapclient.exceptions import LoginError

from jobadvaisor.data.models import Folders, Mailbox, MailRecord, MailRef, message_id_hash

Reason = Literal["unreachable", "certificate", "login", "folder", "protocol", "no key",
                 "no password", "password unreadable"]
REASONS: tuple[str, ...] = Reason.__args__
TIMEOUT_SECONDS = 30
HEADER_ITEM = "BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)]"
# One FETCH names this many UIDs; a longer command line is refused by some servers.
HEADER_BATCH = 200
UNSELECTABLE_FLAGS = {"\\noselect", "\\nonexistent"}
# \All, \Flagged and \Important are virtual folders that show mails of other folders again.
SYSTEM_FLAGS = {"\\trash", "\\junk", "\\sent", "\\drafts", "\\all", "\\flagged", "\\important"}


class MailboxError(Exception):
    """A mailbox operation failed. `reason` is one of `REASONS`; `str(error)` is the reason
    too, never text from the server."""

    def __init__(self, reason: Reason):
        super().__init__(reason)
        self.reason = reason


def reason_of(error: BaseException, imap_error: Reason = "protocol") -> Reason | None:
    """The reason code for an IMAP, TLS or socket `error`, or `None` for any other exception
    (a bug, not a mailbox problem). A failed certificate check is `certificate`; a timeout, a
    DNS failure or a refused connection is `unreachable`; a refused login is `login`; a dropped
    connection and every other TLS, socket or IMAP error is `protocol`. A plain IMAP error
    answer (a NO or BAD to one command) gives `imap_error`, which a select passes as `folder`."""
    if isinstance(error, ssl.SSLCertVerificationError):
        return "certificate"
    if isinstance(error, ssl.SSLError):
        return "protocol"
    if isinstance(error, TimeoutError | socket.gaierror | ConnectionRefusedError):
        return "unreachable"
    if isinstance(error, LoginError):
        return "login"
    if isinstance(error, imaplib.IMAP4.abort | OSError):
        return "protocol"
    if isinstance(error, imaplib.IMAP4.error):
        return imap_error
    return None


@contextmanager
def imap_errors(imap_error: Reason = "protocol") -> Iterator[None]:
    """Run IMAP calls so that no IMAP, TLS or socket exception leaves them: it becomes a
    `MailboxError` with its reason (`reason_of`), without the server's text. Any other exception
    passes unchanged."""
    try:
        yield
    except Exception as error:
        reason = reason_of(error, imap_error)
        if reason is None:
            raise
        raise MailboxError(reason) from None


def connect(account: Mailbox, password: str) -> IMAPClient:
    """A logged-in client for `account`'s host, port and user. TLS only, with the certificate and
    the host name verified, and a 30 second timeout; there is no plain or STARTTLS path. Sets
    the `imapclient` logger to WARNING first, because its DEBUG output logs protocol lines,
    the login included. The client returns timezone-aware times. Raises `MailboxError`; a failed
    login closes the connection."""
    logging.getLogger("imapclient").setLevel(logging.WARNING)
    with imap_errors():
        client = IMAPClient(account.host, account.port, ssl=True,
                            ssl_context=ssl.create_default_context(), timeout=TIMEOUT_SECONDS)
        client.normalise_times = False
        try:
            client.login(account.user, password)
        except BaseException:
            with suppress(Exception):
                client.shutdown()
            raise
    return client


@dataclass(frozen=True)
class Folder:
    """A selectable folder of the account: its readable `name` and whether the server flags it
    as a `system` folder (trash, junk, sent, drafts, all mails, flagged, important)."""

    name: str
    system: bool


def list_folders(client: IMAPClient) -> list[Folder]:
    """The account's folders that can hold mails, in the server's order, with names decoded.
    A folder flagged `\\Noselect` or `\\NonExistent` is left out. Flags compare without case.
    Raises `MailboxError`."""
    with imap_errors():
        listed = client.list_folders()
    folders = []
    for flags, _delimiter, name in listed:
        flags = {flag.decode().lower() for flag in flags}
        if not flags & UNSELECTABLE_FLAGS:
            folders.append(Folder(name, bool(flags & SYSTEM_FLAGS)))
    return folders


@dataclass(frozen=True)
class Candidate(MailRef):
    """A mail a check may read: where it sits and which mail it is (`MailRef`), and its
    INTERNALDATE as `received`, which orders the check. Holds no sender, subject or text."""

    received: datetime


@dataclass(frozen=True)
class Candidates:
    """The outcome of the candidate search. `mails` are the `max_mails` oldest candidates,
    oldest first; `total` is their number and `remaining` counts the unhandled candidates left
    for the next check."""

    mails: list[Candidate]
    total: int
    remaining: int


def find_candidates(client: IMAPClient, folders: list[str], since: date,
                    skip: Sequence[MailRecord], max_mails: int) -> Candidates:
    """The mails of `folders` (see `searched_folders`) received on or after `since`, minus
    every mail held by a record of `skip` (the handled record, and the waiting one while
    screening is off), by UID under the folder's validity or by Message-ID hash. A mail in
    several folders counts once, the first folder in `folders` winning; a mail without a
    Message-ID relies on its UID. Folders are selected read-only and headers fetched with PEEK
    in batches. Marks nothing, so a failure leaves every record as it was. Raises
    `MailboxError`, with `folder` for a select that fails."""
    found: list[Candidate] = []
    seen: set[str] = set()
    for name in folders:
        with imap_errors("folder"):
            validity = client.select_folder(name, readonly=True)[b"UIDVALIDITY"]
        with imap_errors():
            unmarked = [uid for uid in client.search(["SINCE", since])
                        if not any(record.holds(MailRef(name, validity, uid, None))
                                   for record in skip)]
            for start in range(0, len(unmarked), HEADER_BATCH):
                answer = client.fetch(unmarked[start:start + HEADER_BATCH],
                                      [HEADER_ITEM, "INTERNALDATE"])
                for uid, data in sorted(answer.items()):
                    mail = Candidate(name, validity, uid, _id_hash(data), data[b"INTERNALDATE"])
                    if mail.id_hash is not None and (
                            mail.id_hash in seen or any(record.holds(mail) for record in skip)):
                        continue
                    if mail.id_hash is not None:
                        seen.add(mail.id_hash)
                    found.append(mail)
    order = {name: place for place, name in enumerate(folders)}
    found.sort(key=lambda mail: (mail.received, order[mail.folder], mail.uid))
    return Candidates(found[:max_mails], min(len(found), max_mails),
                      max(len(found) - max_mails, 0))


def _id_hash(data: dict[bytes, object]) -> str | None:
    """The `message_id_hash` of a fetched Message-ID header, or `None` when it has none."""
    raw = next((value for key, value in data.items() if key.startswith(b"BODY[HEADER")), b"")
    header = email.message_from_bytes(raw)["Message-ID"]
    return message_id_hash(str(header)) if header and str(header).strip() else None


def parse_mail(raw: bytes) -> EmailMessage:
    """A fetched mail as an `EmailMessage` (the default policy, which decodes headers)."""
    return email.message_from_bytes(raw, policy=email.policy.default)


def mail_parts(message: EmailMessage) -> tuple[str | None, str]:
    """The `(html, text)` the finder reads: the mail's HTML body part, decoded by its charset
    and transfer encoding, or `None` when it has none or it is blank (as on the paste path),
    and its plain-text part, `""` when it has none. Attachments are never read. A charset the
    system does not know is decoded as UTF-8 with replacement characters."""
    html_part, text_part = message.get_body(("html",)), message.get_body(("plain",))
    html = _content(html_part) if html_part is not None else None
    return (html if html and html.strip() else None,
            _content(text_part) if text_part is not None else "")


def _content(part: EmailMessage) -> str:
    try:
        return part.get_content()
    except LookupError:
        return (part.get_payload(decode=True) or b"").decode("utf-8", errors="replace")


def searched_folders(listed: list[Folder], choice: Folders) -> tuple[list[str], list[str]]:
    """The folder names a check searches, and the chosen names that are missing. `{"all"}`:
    every listed folder except system folders, none missing, so a folder created later is
    searched at the next check and a server without flags has every folder searched.
    `{"names"}`: exactly the chosen names that are listed (system folders too), in the chosen
    order; the others are missing and skipped."""
    if choice.names is None:
        return [folder.name for folder in listed if not folder.system], []
    present = {folder.name for folder in listed}
    return ([name for name in choice.names if name in present],
            [name for name in choice.names if name not in present])
