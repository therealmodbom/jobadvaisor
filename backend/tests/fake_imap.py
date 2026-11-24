"""A fake IMAP client for the mailbox tests, in place of `imapclient.IMAPClient`.

It answers only the calls the app makes (`design.md` D2), in IMAPClient's shapes, and holds the
read-only rule: a select without `readonly=True` or a fetch item that is not a `PEEK` raises
`AssertionError` and is also listed in `violations`, so a test can assert it stayed empty even
when the code under test swallows the exception. `calls` records every call (the password is
never recorded). Import it as `from fake_imap import ...` (the tests directory is on the path).
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from email.message import EmailMessage
from email.parser import BytesParser

from imapclient.exceptions import IMAPClientError, LoginError

HEADER_KEY = b"BODY[HEADER.FIELDS (MESSAGE-ID)]"
PLAIN_ITEMS = {"INTERNALDATE", "UID", "RFC822.SIZE"}


def build_mail(message_id: str | None, *, subject: str = "Neue Jobs",
               sender: str = "jobs@example.org", html: str | None = None,
               text: str | None = None, html_encoding: str = "base64") -> bytes:
    """A MIME mail as bytes with fictional headers: `message_id` (`None` leaves the header
    out), an HTML part (transfer encoding `html_encoding`, e.g. `quoted-printable`), a plain
    part, or both as multipart/alternative. At least one part is required."""
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = sender, "name@example.org", subject
    if message_id:
        message["Message-ID"] = message_id
    if text is not None:
        message.set_content(text)
        if html is not None:
            message.add_alternative(html, subtype="html", cte=html_encoding)
    elif html is not None:
        message.set_content(html, subtype="html", cte=html_encoding)
    else:
        raise ValueError("a mail needs an html or a text part")
    return message.as_bytes()


@dataclass
class FakeMail:
    """One mail of a fake folder: its `uid`, the whole `raw` message and the INTERNALDATE
    (`received`, timezone-aware like the real factory's client)."""

    uid: int
    raw: bytes
    received: datetime


@dataclass
class FakeFolder:
    """One fake folder: its special-use and other `flags` (bytes like `b"\\Trash"`), its
    UIDVALIDITY and its `mails`."""

    flags: tuple[bytes, ...] = ()
    validity: int = 1
    mails: list[FakeMail] = field(default_factory=list)


class FakeImap:
    """`folders` by name (insertion order is the listing order). `password` is the one login
    accepts (`None`: any). `errors` maps a method name to an exception raised on every call of
    it. `calls` holds one tuple per call, `violations` the read-only rules that were broken."""

    def __init__(self, folders: dict[str, FakeFolder] | None = None, *,
                 password: str | None = None, errors: dict[str, BaseException] | None = None):
        self.folders = folders if folders is not None else {}
        self.password = password
        self.errors = errors or {}
        self.calls: list[tuple] = []
        self.violations: list[str] = []
        self.selected: str | None = None

    def _call(self, *call) -> None:
        self.calls.append(call)
        if (error := self.errors.get(call[0])) is not None:
            raise error

    def _violate(self, message: str, kind: str) -> None:
        self.violations.append(message)
        raise AssertionError(f"{kind}: {message}")

    def login(self, user: str, password: str) -> None:
        """Record the login (user only); `LoginError` for a password other than `password`.
        Like imaplib's LOGIN it encodes both as ASCII, so a non-ASCII one raises
        `UnicodeEncodeError`."""
        self._call("login", user)
        (user + password).encode("ascii")
        self._check_password(password)

    def plain_login(self, user: str, password: str) -> None:
        """Record a SASL PLAIN login (`("plain_login", user)`), which carries UTF-8; the same
        `LoginError` as `login`."""
        self._call("plain_login", user)
        self._check_password(password)

    def _check_password(self, password: str) -> None:
        if self.password is not None and password != self.password:
            raise LoginError("login refused")

    def logout(self) -> None:
        """Record the logout."""
        self._call("logout")

    def shutdown(self) -> None:
        """Record closing the connection without a logout."""
        self._call("shutdown")

    def list_folders(self) -> list[tuple[tuple[bytes, ...], bytes, str]]:
        """`(flags, delimiter, name)` per folder, names decoded, in IMAPClient's shape."""
        self._call("list_folders")
        return [(folder.flags, b"/", name) for name, folder in self.folders.items()]

    def select_folder(self, name: str, readonly: bool = False) -> dict[bytes, object]:
        """Select `name`; answers `UIDVALIDITY` and `EXISTS`. A select without `readonly=True`
        is a violation; a missing folder raises `IMAPClientError`."""
        self._call("select_folder", name, readonly)
        if readonly is not True:
            self._violate(f"select_folder({name!r}) without readonly=True", "readonly")
        if name not in self.folders:
            raise IMAPClientError(f"select failed: no folder {name}")
        self.selected = name
        folder = self.folders[name]
        return {b"UIDVALIDITY": folder.validity, b"EXISTS": len(folder.mails)}

    def _folder(self) -> FakeFolder:
        assert self.selected is not None, "select a folder first"
        return self.folders[self.selected]

    def search(self, criteria: list) -> list[int]:
        """Only `["SINCE", date]`: the UIDs of the selected folder received on or after it."""
        self._call("search", tuple(criteria))
        folder = self._folder()
        assert criteria[0] == "SINCE" and len(criteria) == 2 and isinstance(criteria[1], date)
        return sorted(mail.uid for mail in folder.mails
                      if mail.received.date() >= criteria[1])

    def fetch(self, uids: list[int], items: list[str]) -> dict[int, dict[bytes, object]]:
        """`BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)]`, `BODY.PEEK[]` and `INTERNALDATE` for the
        selected folder's `uids` (unknown ones are left out). Any other body item, a fetch
        without PEEK, is a violation."""
        self._call("fetch", tuple(uids), tuple(items))
        folder = self._folder()
        for item in items:
            if not item.startswith("BODY.PEEK[") and item not in PLAIN_ITEMS:
                self._violate(f"fetch item {item!r} without PEEK", "peek")
        found = {}
        for mail in folder.mails:
            if mail.uid not in uids:
                continue
            answer: dict[bytes, object] = {b"SEQ": mail.uid}
            for item in items:
                if item == "INTERNALDATE":
                    answer[b"INTERNALDATE"] = mail.received
                elif item == "BODY.PEEK[]":
                    answer[b"BODY[]"] = mail.raw
                elif item == "BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)]":
                    message_id = BytesParser().parsebytes(mail.raw, headersonly=True)["Message-ID"]
                    answer[HEADER_KEY] = (f"Message-ID: {message_id}\r\n\r\n".encode()
                                          if message_id else b"\r\n")
            found[mail.uid] = answer
        return found
