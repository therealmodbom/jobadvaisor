import errno
import imaplib
import logging
import socket
import ssl

import pytest
from fake_imap import FakeImap
from imapclient.exceptions import IMAPClientAbortError, IMAPClientError, LoginError

from jobadvaisor.data.models import Mailbox
from jobadvaisor.intake import mailbox

ACCOUNT = Mailbox(schema_version="1", host="imap.example.org", port=993, user="name@example.org")
SERVER_TEXT = "NO [AUTHENTICATIONFAILED] name@example.org from 203.0.113.9 refused"


class Client(FakeImap):
    """The class `connect` builds in place of `IMAPClient`: records its constructor call and
    can fail there or at the login."""

    built: list[tuple]
    logins: list[str]
    fail_init: BaseException | None = None
    fail_login: BaseException | None = None
    accepted: str | None = None

    def __init__(self, *args, **kwargs):
        type(self).built.append((args, kwargs))
        if self.fail_init is not None:
            raise self.fail_init
        super().__init__(password=type(self).accepted)

    def login(self, user, password):
        type(self).logins.append(user)
        super().login(user, password)
        if self.fail_login is not None:
            raise self.fail_login

    def plain_login(self, user, password):
        super().plain_login(user, password)
        if self.fail_login is not None:
            raise self.fail_login


@pytest.fixture
def client_class(monkeypatch):
    subclass = type("TestClient", (Client,), {"built": [], "logins": []})
    monkeypatch.setattr(mailbox, "IMAPClient", subclass)
    return subclass


def reason_of_connect(client_class, **failure) -> mailbox.MailboxError:
    for name, error in failure.items():
        setattr(client_class, name, error)
    with pytest.raises(mailbox.MailboxError) as caught:
        mailbox.connect(ACCOUNT, "app-password-1")
    return caught.value


CERTIFICATE = ssl.SSLCertVerificationError(1, "certificate verify failed: hostname mismatch")


@pytest.mark.parametrize(("failure", "reason"), [
    ({"fail_init": CERTIFICATE}, "certificate"),
    ({"fail_init": TimeoutError(SERVER_TEXT)}, "unreachable"),
    ({"fail_init": socket.gaierror(8, SERVER_TEXT)}, "unreachable"),
    ({"fail_init": ConnectionRefusedError(SERVER_TEXT)}, "unreachable"),
    ({"fail_login": LoginError(SERVER_TEXT)}, "login"),
    ({"fail_init": ssl.SSLError(1, "[SSL: WRONG_VERSION_NUMBER] " + SERVER_TEXT)}, "protocol"),
    ({"fail_init": ConnectionResetError(SERVER_TEXT)}, "unreachable"),
    ({"fail_init": IMAPClientError(SERVER_TEXT)}, "protocol"),
    ({"fail_login": IMAPClientAbortError(SERVER_TEXT)}, "protocol"),
    ({"fail_login": imaplib.IMAP4.error(SERVER_TEXT)}, "protocol"),
])
def test_a_connection_error_gives_one_reason(client_class, failure, reason):
    assert reason_of_connect(client_class, **failure).reason == reason


def test_a_certificate_error_attempts_no_login(client_class):
    reason_of_connect(client_class, fail_init=CERTIFICATE)
    assert client_class.built and client_class.logins == []


@pytest.mark.parametrize("failure", [
    {"fail_init": TimeoutError(SERVER_TEXT)},
    {"fail_login": LoginError(SERVER_TEXT)},
    {"fail_init": ssl.SSLError(1, SERVER_TEXT)},
    {"fail_login": IMAPClientError(SERVER_TEXT)},
])
def test_no_reason_holds_the_server_text(client_class, failure):
    error = reason_of_connect(client_class, **failure)
    assert error.reason in mailbox.REASONS
    assert "name@example.org" not in str(error) + repr(error) + error.reason
    assert "203.0.113.9" not in str(error) + repr(error)


def test_connect_builds_a_verified_tls_client_with_a_30_second_timeout(client_class):
    mailbox.connect(ACCOUNT, "app-password-1")
    (args, kwargs), = client_class.built
    assert args == ("imap.example.org", 993)
    assert kwargs["ssl"] is True and kwargs["timeout"] == 30
    context = kwargs["ssl_context"]
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True


def test_connect_logs_in_and_returns_the_client(client_class):
    client = mailbox.connect(ACCOUNT, "app-password-1")
    assert isinstance(client, client_class)
    assert client.calls == [("login", "name@example.org")]
    assert client.normalise_times is False


def test_a_refused_login_closes_the_connection(client_class):
    client_class.fail_login = LoginError(SERVER_TEXT)
    closed = []
    client_class.shutdown = lambda self: closed.append(self)
    with pytest.raises(mailbox.MailboxError):
        mailbox.connect(ACCOUNT, "app-password-1")
    assert len(closed) == 1


@pytest.mark.parametrize("name", ["imapclient", "imapclient.imapclient", "imapclient.imaplib"])
def test_connect_leaves_the_imapclient_logger_at_warning(client_class, name):
    logging.getLogger("imapclient").setLevel(logging.DEBUG)
    mailbox.connect(ACCOUNT, "app-password-1")
    assert logging.getLogger(name).getEffectiveLevel() == logging.WARNING


def test_the_mapping_leaves_other_errors_alone():
    with pytest.raises(KeyError), mailbox.imap_errors():
        raise KeyError("a bug, not an IMAP error")


def test_a_failing_select_gives_folder_but_a_lost_connection_stays_protocol():
    with pytest.raises(mailbox.MailboxError) as caught, mailbox.imap_errors("folder"):
        raise IMAPClientError(SERVER_TEXT)
    assert caught.value.reason == "folder"
    with pytest.raises(mailbox.MailboxError) as caught, mailbox.imap_errors("folder"):
        raise IMAPClientAbortError(SERVER_TEXT)
    assert caught.value.reason == "protocol"
    with pytest.raises(mailbox.MailboxError) as caught, mailbox.imap_errors("folder"):
        raise TimeoutError(SERVER_TEXT)
    assert caught.value.reason == "unreachable"


# --- a password outside ASCII (review C1) -------------------------------------------------

UMLAUT_PASSWORD = "geheim§2026ä"
NOT_ASCII = UnicodeEncodeError("ascii", UMLAUT_PASSWORD, 6, 7, "ordinal not in range(128)")


def test_a_password_outside_ascii_logs_in_through_sasl_plain(client_class):
    client = mailbox.connect(ACCOUNT, UMLAUT_PASSWORD)
    assert client.calls == [("plain_login", "name@example.org")]


def test_an_ascii_password_keeps_the_login_command(client_class):
    assert mailbox.connect(ACCOUNT, "app-password-1").calls == [("login", "name@example.org")]


def test_a_refused_password_outside_ascii_is_a_login_reason(client_class):
    client_class.accepted = "another-password"
    with pytest.raises(mailbox.MailboxError) as caught:
        mailbox.connect(ACCOUNT, UMLAUT_PASSWORD)
    assert caught.value.reason == "login"


@pytest.mark.parametrize(("failure", "reason"), [
    ({"fail_init": NOT_ASCII}, "protocol"),
    ({"fail_init": KeyError(UMLAUT_PASSWORD)}, "protocol"),
    ({"fail_login": NOT_ASCII}, "login"),
    ({"fail_login": ValueError(UMLAUT_PASSWORD)}, "login"),
])
def test_an_unexpected_error_of_connect_gives_a_fixed_reason_never_its_text(
        client_class, caplog, failure, reason):
    error = reason_of_connect(client_class, **failure)
    assert error.reason == reason
    assert "§" not in str(error) + repr(error) + caplog.text
    assert error.__suppress_context__


@pytest.mark.parametrize(("error", "reason"), [
    (OSError(errno.EHOSTUNREACH, "no route to host"), "unreachable"),
    (OSError(errno.ENETUNREACH, "network is unreachable"), "unreachable"),
    (OSError(errno.EHOSTDOWN, "host is down"), "unreachable"),
    (ConnectionResetError(errno.ECONNRESET, "reset by peer"), "unreachable"),
    (OSError(errno.EPIPE, "broken pipe"), "protocol"),
])
def test_a_network_error_that_means_not_reachable_is_unreachable(client_class, error, reason):
    assert reason_of_connect(client_class, fail_init=error).reason == reason
