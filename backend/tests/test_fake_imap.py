"""Self-test of the fake IMAP client the mailbox tests inject in place of `IMAPClient`."""

from datetime import UTC, date, datetime

import pytest
from fake_imap import FakeFolder, FakeImap, FakeMail, build_mail
from imapclient.exceptions import IMAPClientError, LoginError

HEADER = "BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)]"


def mail(uid, received=datetime(2026, 11, 1, 9, 0, tzinfo=UTC), **parts) -> FakeMail:
    return FakeMail(uid, build_mail(f"<m{uid}@example.org>", **parts), received)


def fake() -> FakeImap:
    return FakeImap({
        "Posteingang": FakeFolder(validity=7, mails=[
            mail(1, text="one"),
            mail(2, datetime(2026, 11, 5, 9, 0, tzinfo=UTC), html="<p>two</p>")]),
        "Papierkorb": FakeFolder(flags=(b"\\Trash",)),
        "Konten": FakeFolder(flags=(b"\\Noselect",))})


def test_calls_are_recorded_in_order():
    imap = fake()
    imap.login("name@example.org", "secret")
    imap.select_folder("Posteingang", readonly=True)
    imap.search(["SINCE", date(2026, 11, 1)])
    imap.logout()
    assert [call[0] for call in imap.calls] == ["login", "select_folder", "search", "logout"]
    assert imap.violations == []


def test_the_password_is_not_recorded():
    imap = fake()
    imap.login("name@example.org", "secret")
    assert "secret" not in repr(imap.calls)


def test_wrong_password_is_a_login_error():
    with pytest.raises(LoginError):
        FakeImap({}, password="right").login("name@example.org", "wrong")


def test_list_folders_answers_flags_delimiter_and_name_like_imapclient():
    assert fake().list_folders() == [((), b"/", "Posteingang"), ((b"\\Trash",), b"/", "Papierkorb"),
                                     ((b"\\Noselect",), b"/", "Konten")]


def test_select_answers_the_validity():
    assert fake().select_folder("Posteingang", readonly=True)[b"UIDVALIDITY"] == 7


def test_select_without_readonly_fails_and_is_recorded():
    imap = fake()
    with pytest.raises(AssertionError, match="readonly"):
        imap.select_folder("Posteingang")
    assert imap.violations == ["select_folder('Posteingang') without readonly=True"]


def test_select_of_a_missing_folder_is_an_imap_error():
    with pytest.raises(IMAPClientError):
        fake().select_folder("Gone", readonly=True)


def test_search_since_keeps_the_mails_received_on_or_after_the_date():
    imap = fake()
    imap.select_folder("Posteingang", readonly=True)
    assert imap.search(["SINCE", date(2026, 11, 2)]) == [2]
    assert imap.search(["SINCE", date(2026, 11, 1)]) == [1, 2]


def test_fetch_answers_message_id_and_internal_date():
    imap = fake()
    imap.select_folder("Posteingang", readonly=True)
    answer = imap.fetch([1], [HEADER, "INTERNALDATE"])
    header = answer[1][b"BODY[HEADER.FIELDS (MESSAGE-ID)]"]
    assert header == b"Message-ID: <m1@example.org>\r\n\r\n"
    assert answer[1][b"INTERNALDATE"] == datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def test_fetch_answers_the_whole_mail_with_peek():
    imap = fake()
    imap.select_folder("Posteingang", readonly=True)
    assert b"one" in imap.fetch([1], ["BODY.PEEK[]"])[1][b"BODY[]"]


@pytest.mark.parametrize("item", ["BODY[]", "RFC822", "BODY[HEADER.FIELDS (MESSAGE-ID)]"])
def test_fetch_without_peek_fails_and_is_recorded(item):
    imap = fake()
    imap.select_folder("Posteingang", readonly=True)
    with pytest.raises(AssertionError, match="PEEK"):
        imap.fetch([1], [item])
    assert imap.violations == [f"fetch item {item!r} without PEEK"]


def test_fetch_omits_an_unknown_uid():
    imap = fake()
    imap.select_folder("Posteingang", readonly=True)
    assert imap.fetch([99], ["BODY.PEEK[]"]) == {}


def test_search_and_fetch_need_a_selected_folder():
    with pytest.raises(AssertionError, match="select"):
        fake().search(["SINCE", date(2026, 11, 1)])


def test_a_mail_without_a_message_id_answers_an_empty_header():
    imap = FakeImap({"A": FakeFolder(mails=[FakeMail(1, build_mail(None, text="x"),
                                                     datetime(2026, 11, 1, tzinfo=UTC))])})
    imap.select_folder("A", readonly=True)
    assert imap.fetch([1], [HEADER])[1][b"BODY[HEADER.FIELDS (MESSAGE-ID)]"] == b"\r\n"


def test_an_injected_error_is_raised_by_its_method():
    imap = FakeImap({}, errors={"list_folders": OSError("boom")})
    with pytest.raises(OSError):
        imap.list_folders()
    assert imap.calls == [("list_folders",)]
