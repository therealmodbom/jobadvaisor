from datetime import UTC, date, datetime, timedelta

import pytest
from fake_imap import FakeFolder, FakeImap, FakeMail, build_mail

from jobadvaisor.data.models import MailRecord, MailRef, message_id_hash
from jobadvaisor.intake.mailbox import MailboxError, find_candidates, mail_parts, parse_mail

SINCE = date(2026, 10, 24)
DAY = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
NOBODY = MailRecord()


def mail(uid, message_id="auto", received=DAY, **parts) -> FakeMail:
    """A fake mail; `message_id="auto"` derives `<m<uid>@example.org>`, `None` leaves it out."""
    message_id = f"<m{uid}@example.org>" if message_id == "auto" else message_id
    return FakeMail(uid, build_mail(message_id, **{"text": "x"} | parts), received)


def folder(*mails, validity=7) -> FakeFolder:
    return FakeFolder(validity=validity, mails=list(mails))


def hours(count) -> datetime:
    return DAY + timedelta(hours=count)


def uids(found):
    return [(mail.folder, mail.uid) for mail in found.mails]


def test_candidates_carry_folder_validity_uid_hash_and_received_date():
    imap = FakeImap({"Posteingang": folder(mail(101, received=hours(2)))})
    found = find_candidates(imap, ["Posteingang"], SINCE, [NOBODY], 200)
    candidate, = found.mails
    assert (candidate.folder, candidate.validity, candidate.uid) == ("Posteingang", 7, 101)
    assert candidate.id_hash == message_id_hash("<m101@example.org>")
    assert candidate.received == hours(2)
    assert isinstance(candidate, MailRef)
    assert (found.total, found.remaining) == (1, 0)


def test_the_search_is_since_the_start_date_and_older_mail_is_not_read():
    old = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
    imap = FakeImap({"Posteingang": folder(mail(1, received=old), mail(2))})
    found = find_candidates(imap, ["Posteingang"], SINCE, [NOBODY], 200)
    assert uids(found) == [("Posteingang", 2)]
    assert ("search", ("SINCE", SINCE)) in imap.calls


def test_every_folder_is_selected_read_only_and_nothing_is_flagged():
    imap = FakeImap({"A": folder(mail(1)), "B": folder(mail(2))})
    find_candidates(imap, ["A", "B"], SINCE, [NOBODY], 200)
    assert [call for call in imap.calls if call[0] == "select_folder"] == [
        ("select_folder", "A", True), ("select_folder", "B", True)]
    assert imap.violations == []
    assert {call[0] for call in imap.calls} == {"select_folder", "search", "fetch"}


def test_marked_uids_are_dropped_before_their_headers_are_fetched():
    handled = MailRecord().marked([MailRef("Posteingang", 7, 1, None)])
    waiting = MailRecord().marked([MailRef("Posteingang", 7, 2, None)])
    imap = FakeImap({"Posteingang": folder(mail(1), mail(2), mail(3))})
    found = find_candidates(imap, ["Posteingang"], SINCE, [handled, waiting], 200)
    assert uids(found) == [("Posteingang", 3)]
    assert [call[1] for call in imap.calls if call[0] == "fetch"] == [(3,)]


def test_waiting_mails_are_candidates_when_only_handled_is_passed():
    waiting = MailRecord().marked([MailRef("Posteingang", 7, 2, None)])
    imap = FakeImap({"Posteingang": folder(mail(2))})
    assert uids(find_candidates(imap, ["Posteingang"], SINCE, [NOBODY], 200)) == [
        ("Posteingang", 2)]
    assert uids(find_candidates(imap, ["Posteingang"], SINCE, [NOBODY, waiting], 200)) == []


def test_a_mail_moved_to_another_folder_is_recognised_by_its_id_hash():
    handled = MailRecord().marked([MailRef("Posteingang", 7, 101, message_id_hash("<a@x.org>"))])
    imap = FakeImap({"Jobs": folder(mail(5, "<A@x.org>"), mail(6), validity=3)})
    found = find_candidates(imap, ["Jobs"], SINCE, [handled], 200)
    assert uids(found) == [("Jobs", 6)]


def test_a_renumbered_folder_keeps_handled_mails_with_an_id_hash_skipped():
    handled = MailRecord().marked([MailRef("Posteingang", 7, 1, message_id_hash("<a@x.org>")),
                                   MailRef("Posteingang", 7, 2, None)])
    imap = FakeImap({"Posteingang": folder(mail(1, "<a@x.org>"), mail(2, None), validity=8)})
    found = find_candidates(imap, ["Posteingang"], SINCE, [handled], 200)
    assert uids(found) == [("Posteingang", 2)]


def test_a_mail_in_two_folders_is_read_once_and_the_first_folder_wins():
    imap = FakeImap({"Posteingang": folder(mail(1, "<a@x.org>")),
                     "Alle Nachrichten": folder(mail(40, "<a@x.org>"), mail(41, "<b@x.org>"))})
    found = find_candidates(imap, ["Posteingang", "Alle Nachrichten"], SINCE, [NOBODY], 200)
    assert uids(found) == [("Posteingang", 1), ("Alle Nachrichten", 41)]
    assert (found.total, found.remaining) == (2, 0)


def test_mails_without_a_message_id_are_neither_dropped_nor_merged():
    imap = FakeImap({"A": folder(mail(1, None)), "B": folder(mail(1, None))})
    found = find_candidates(imap, ["A", "B"], SINCE, [NOBODY], 200)
    assert uids(found) == [("A", 1), ("B", 1)]
    assert [candidate.id_hash for candidate in found.mails] == [None, None]


def test_candidates_are_sorted_oldest_first_across_folders():
    imap = FakeImap({"A": folder(mail(1, received=hours(5)), mail(2, received=hours(1))),
                     "B": folder(mail(3, received=hours(3)))})
    found = find_candidates(imap, ["A", "B"], SINCE, [NOBODY], 200)
    assert uids(found) == [("A", 2), ("B", 3), ("A", 1)]


def test_a_large_first_check_reads_the_oldest_and_counts_the_rest():
    imap = FakeImap({"A": folder(*[mail(uid, received=hours(uid)) for uid in range(1, 131)]),
                     "B": folder(*[mail(uid, received=hours(uid)) for uid in range(131, 261)])})
    found = find_candidates(imap, ["A", "B"], SINCE, [NOBODY], 200)
    assert (found.total, found.remaining) == (200, 60)
    assert max(candidate.received for candidate in found.mails) == hours(200)
    assert sorted(candidate.uid for candidate in found.mails) == list(range(1, 201))


def test_a_changed_limit_changes_the_split():
    imap = FakeImap({"A": folder(*[mail(uid, received=hours(uid)) for uid in range(1, 261)])})
    found = find_candidates(imap, ["A"], SINCE, [NOBODY], 50)
    assert (found.total, found.remaining) == (50, 210)
    assert [candidate.uid for candidate in found.mails] == list(range(1, 51))


def test_headers_are_fetched_in_batches():
    imap = FakeImap({"A": folder(*[mail(uid, received=hours(uid)) for uid in range(1, 461)])})
    find_candidates(imap, ["A"], SINCE, [NOBODY], 1000)
    sizes = [len(call[1]) for call in imap.calls if call[0] == "fetch"]
    assert max(sizes) <= 200 and sum(sizes) == 460


def test_repeats_do_not_count_against_the_limit_or_remaining():
    imap = FakeImap({"A": folder(mail(1, "<a@x.org>", received=hours(1))),
                     "B": folder(mail(9, "<a@x.org>", received=hours(2)),
                                 mail(10, "<b@x.org>", received=hours(3)))})
    found = find_candidates(imap, ["A", "B"], SINCE, [NOBODY], 1)
    assert uids(found) == [("A", 1)] and (found.total, found.remaining) == (1, 1)


def test_nothing_is_marked_by_the_search():
    handled = MailRecord()
    imap = FakeImap({"A": folder(mail(1), mail(2))})
    find_candidates(imap, ["A"], SINCE, [handled], 200)
    assert handled == MailRecord()


def test_a_select_that_fails_for_a_listed_folder_is_the_folder_reason():
    imap = FakeImap({"A": folder(mail(1))})
    with pytest.raises(MailboxError) as caught:
        find_candidates(imap, ["A", "Gone"], SINCE, [NOBODY], 200)
    assert caught.value.reason == "folder"


def test_a_lost_connection_while_searching_is_a_mailbox_error():
    imap = FakeImap({"A": folder(mail(1))}, errors={"fetch": ConnectionResetError("lost")})
    with pytest.raises(MailboxError) as caught:
        find_candidates(imap, ["A"], SINCE, [NOBODY], 200)
    assert caught.value.reason == "protocol"


def parts(**kwargs):
    return mail_parts(parse_mail(build_mail("<m@example.org>", **kwargs)))


def test_a_multipart_mail_gives_its_html_and_its_text():
    assert parts(html="<p>Job</p>", text="Job") == ("<p>Job</p>\n", "Job\n")


def test_a_plain_only_mail_has_no_html():
    assert parts(text="https://jobs.example.org/1") == (None, "https://jobs.example.org/1\n")


def test_an_html_only_mail_has_empty_text():
    assert parts(html="<p>Job</p>") == ("<p>Job</p>\n", "")


def test_a_quoted_printable_html_part_is_decoded_with_its_charset():
    html, text = parts(html="<p>Stellenangebote für Entwickler</p>", text="x",
                       html_encoding="quoted-printable")
    assert html == "<p>Stellenangebote für Entwickler</p>\n"


@pytest.mark.parametrize("blank", ["", "   ", "\n\t \n"])
def test_a_blank_html_part_becomes_none_and_the_text_stays(blank):
    assert parts(html=blank, text="https://jobs.example.org/1") == (
        None, "https://jobs.example.org/1\n")


def test_an_attachment_is_not_read():
    raw = build_mail("<m@example.org>", html="<p>Job</p>")
    message = parse_mail(raw)
    message.add_attachment(b"%PDF-1.4 " + b"x" * 1000, maintype="application", subtype="pdf",
                           filename="cv.pdf")
    assert mail_parts(parse_mail(message.as_bytes())) == ("<p>Job</p>\n", "")


def test_a_mail_without_a_text_part_gives_nothing():
    message = parse_mail(build_mail("<m@example.org>", text="x"))
    message.clear_content()
    message.set_content(b"data", maintype="application", subtype="octet-stream")
    assert mail_parts(parse_mail(message.as_bytes())) == (None, "")


def test_an_unknown_charset_is_decoded_as_utf8_instead_of_failing():
    raw = (b"Message-ID: <x@example.org>\r\nMIME-Version: 1.0\r\n"
           b"Content-Type: text/html; charset=x-unknown\r\n"
           b"Content-Transfer-Encoding: 8bit\r\n\r\n<p>F\xc3\xbcr Sie</p>\r\n")
    assert mail_parts(parse_mail(raw)) == ("<p>Für Sie</p>\r\n", "")
