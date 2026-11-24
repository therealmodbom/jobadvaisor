"""Reading job alert mails from an IMAP mailbox (`design.md` D2, D4, D5).

This module holds the access layer: the `connect` factory, the one mapping from every IMAP
error to a fixed reason code, the folder rules, the candidate search and `mail_parts`. The
password only ever passes through `connect` into `login`; no reason, log line or exception text
carries it, and none carries text from the server, which may echo the user name.
"""

import imaplib
import logging
import socket
import ssl
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Literal

from imapclient import IMAPClient
from imapclient.exceptions import LoginError

from jobadvaisor.data.models import Mailbox

Reason = Literal["unreachable", "certificate", "login", "folder", "protocol", "no key",
                 "no password", "password unreadable"]
REASONS: tuple[str, ...] = Reason.__args__
TIMEOUT_SECONDS = 30


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
