import hashlib
import json
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from jobadvaisor.data.loader import DataRepositoryError, load
from jobadvaisor.data.models import Folders, Mailbox, MailRef, message_id_hash
from jobadvaisor.data.schemas import render
from jobadvaisor.data.writer import mark_mails, read_mailbox, update_mailbox, update_mailbox_account

ACCOUNT = {"host": "imap.example.org", "port": 993, "user": "name@example.org"}
CHECKED = datetime(2026, 11, 22, 18, 4, tzinfo=UTC)


def ref(uid, folder="Posteingang", validity=7, message_id="<a@example.org>") -> MailRef:
    return MailRef(folder, validity, uid, message_id_hash(message_id) if message_id else None)


def configured(root, **changes) -> Mailbox:
    update_mailbox_account(root, **ACCOUNT)
    return update_mailbox(root, lambda mailbox: mailbox.model_copy(update=changes))


def test_model_defaults_to_all_folders_port_993_and_200_mails():
    mailbox = Mailbox.model_validate({"schema_version": "1", "host": "imap.example.org",
                                      "user": "name@example.org"})
    assert (mailbox.port, mailbox.max_mails, mailbox.folders.all) == (993, 200, True)
    assert (mailbox.since, mailbox.last_check_at) == (None, None)
    assert mailbox.handled.ids == [] and mailbox.waiting.uids == {}


def test_model_reads_the_documented_file_shape():
    mailbox = Mailbox.model_validate_json(json.dumps({
        "schema_version": "1", **ACCOUNT, "folders": {"names": ["Posteingang", "Jobs"]},
        "max_mails": 50, "since": "2026-10-24", "last_check_at": "2026-11-22T18:04:00Z",
        "handled": {"uids": {"Posteingang": {"validity": 1700000000, "uids": [101, 102]}},
                    "ids": ["3f2a9c0d1b7e4a56"]},
        "waiting": {"uids": {}, "ids": []}}), strict=True)
    assert mailbox.folders.names == ["Posteingang", "Jobs"]
    assert mailbox.since == date(2026, 10, 24)
    assert mailbox.handled.uids["Posteingang"].uids == [101, 102]


@pytest.mark.parametrize("value", [0, 1001])
def test_max_mails_outside_1_to_1000_is_refused(value):
    with pytest.raises(ValidationError, match="max_mails"):
        Mailbox.model_validate({"schema_version": "1", **ACCOUNT, "max_mails": value})


@pytest.mark.parametrize("value", [1, 1000])
def test_max_mails_bounds_are_allowed(value):
    assert Mailbox.model_validate(
        {"schema_version": "1", **ACCOUNT, "max_mails": value}).max_mails == value


def test_a_mark_that_is_no_id_hash_is_refused():
    with pytest.raises(ValidationError):
        Mailbox.model_validate({"schema_version": "1", **ACCOUNT,
                                "handled": {"ids": ["<a@example.org>"]}})


def test_published_schema_includes_the_mailbox_with_max_mails_bounds():
    schema = json.loads(render()["mailbox.schema.json"])
    assert schema["properties"]["max_mails"]["minimum"] == 1
    assert schema["properties"]["max_mails"]["maximum"] == 1000
    assert schema["properties"]["max_mails"]["default"] == 200


def test_a_repository_without_a_mailbox_file_loads(data_repository):
    assert load(data_repository).postings
    assert read_mailbox(data_repository) is None


def test_unreadable_mailbox_file_is_refused(data_repository):
    (data_repository / "mailbox.json").write_text("{not json")
    with pytest.raises(DataRepositoryError, match="mailbox.json"):
        read_mailbox(data_repository)


def test_message_id_hash_is_16_hex_of_sha256_over_the_trimmed_lower_case_id():
    expected = hashlib.sha256(b"<abc@example.org>").hexdigest()[:16]
    assert message_id_hash("  <ABC@Example.org>\r\n") == expected
    assert len(expected) == 16


def test_saving_the_account_creates_the_file_with_defaults(data_repository):
    mailbox = update_mailbox_account(data_repository, **ACCOUNT)
    assert read_mailbox(data_repository) == mailbox
    assert (mailbox.max_mails, mailbox.folders.all) == (200, True)


def test_saving_settings_keeps_the_marks_written_meanwhile(data_repository):
    configured(data_repository, since=date(2026, 10, 24), last_check_at=CHECKED)
    mark_mails(data_repository, handled=[ref(101)], waiting=[ref(102, message_id="<b@x.org>")])
    update_mailbox_account(data_repository, **ACCOUNT, max_mails=50,
                           folders=Folders(names=["Jobs"]))
    mailbox = read_mailbox(data_repository)
    assert mailbox.max_mails == 50 and mailbox.folders.names == ["Jobs"]
    assert mailbox.handled.uids["Posteingang"].uids == [101]
    assert mailbox.waiting.uids["Posteingang"].uids == [102]
    assert (mailbox.since, mailbox.last_check_at) == (date(2026, 10, 24), CHECKED)


def test_an_account_change_without_new_values_keeps_folders_and_max_mails(data_repository):
    update_mailbox_account(data_repository, **ACCOUNT, max_mails=50,
                           folders=Folders(names=["Jobs"]))
    update_mailbox_account(data_repository, **ACCOUNT | {"user": "other@example.org"})
    mailbox = read_mailbox(data_repository)
    assert mailbox.max_mails == 50 and mailbox.folders.names == ["Jobs"]


@pytest.mark.parametrize("change", [{"host": "imap.example.com"}, {"user": "other@example.org"}])
def test_a_host_or_user_change_clears_since_check_time_and_marks(data_repository, change):
    configured(data_repository, since=date(2026, 10, 24), last_check_at=CHECKED)
    mark_mails(data_repository, handled=[ref(101)], waiting=[ref(102, message_id="<b@x.org>")])
    update_mailbox_account(data_repository, **ACCOUNT | change)
    mailbox = read_mailbox(data_repository)
    assert (mailbox.since, mailbox.last_check_at) == (None, None)
    assert (mailbox.handled.uids, mailbox.handled.ids) == ({}, [])
    assert (mailbox.waiting.uids, mailbox.waiting.ids) == ({}, [])


def test_a_port_change_keeps_since_and_marks(data_repository):
    configured(data_repository, since=date(2026, 10, 24))
    mark_mails(data_repository, handled=[ref(101)])
    update_mailbox_account(data_repository, **ACCOUNT | {"port": 1993})
    mailbox = read_mailbox(data_repository)
    assert mailbox.port == 1993 and mailbox.since == date(2026, 10, 24)
    assert mailbox.handled.uids["Posteingang"].uids == [101]


@pytest.mark.parametrize("value", [0, 1001])
def test_saving_max_mails_outside_1_to_1000_is_refused(data_repository, value):
    with pytest.raises(ValueError, match="max_mails"):
        update_mailbox_account(data_repository, **ACCOUNT, max_mails=value)
    assert read_mailbox(data_repository) is None


def test_marks_hold_uids_by_folder_and_id_hashes(data_repository):
    configured(data_repository)
    mark_mails(data_repository, handled=[ref(101), ref(102, message_id=None),
                                         ref(5, folder="Jobs", validity=9, message_id="<c@x.org>")])
    mailbox = read_mailbox(data_repository)
    assert mailbox.handled.uids["Posteingang"].validity == 7
    assert mailbox.handled.uids["Posteingang"].uids == [101, 102]
    assert mailbox.handled.uids["Jobs"].uids == [5]
    assert mailbox.handled.ids == sorted([message_id_hash("<a@example.org>"),
                                          message_id_hash("<c@x.org>")])


def test_marking_twice_records_once(data_repository):
    configured(data_repository)
    mark_mails(data_repository, handled=[ref(101)])
    mark_mails(data_repository, handled=[ref(101)])
    mailbox = read_mailbox(data_repository)
    assert mailbox.handled.uids["Posteingang"].uids == [101]
    assert len(mailbox.handled.ids) == 1


def test_a_changed_uidvalidity_replaces_the_folders_uids(data_repository):
    configured(data_repository)
    mark_mails(data_repository, handled=[ref(101), ref(102, message_id=None)])
    mark_mails(data_repository, handled=[ref(3, validity=8, message_id=None)])
    folder = read_mailbox(data_repository).handled.uids["Posteingang"]
    assert (folder.validity, folder.uids) == (8, [3])


def test_a_mark_is_found_by_uid_under_the_same_validity_or_by_id_hash(data_repository):
    configured(data_repository)
    mark_mails(data_repository, handled=[ref(101, message_id=None), ref(7, message_id="<m@x.org>")])
    handled = read_mailbox(data_repository).handled
    assert handled.holds(ref(101, message_id=None))
    assert not handled.holds(ref(101, validity=8, message_id=None))
    assert not handled.holds(ref(102, message_id=None))
    assert handled.holds(ref(999, folder="Jobs", validity=1, message_id="<M@x.org>"))


def test_handling_a_waiting_mail_removes_it_from_waiting(data_repository):
    configured(data_repository)
    mark_mails(data_repository, waiting=[ref(101)])
    mark_mails(data_repository, handled=[ref(101)])
    mailbox = read_mailbox(data_repository)
    assert mailbox.waiting.uids == {}
    assert mailbox.waiting.ids == []
    assert mailbox.handled.uids["Posteingang"].uids == [101]


def test_marking_without_a_configured_mailbox_is_refused(data_repository):
    with pytest.raises(ValueError, match="no mailbox"):
        mark_mails(data_repository, handled=[ref(101)])


def test_marking_for_the_account_that_is_stored_marks(data_repository):
    configured(data_repository)
    mailbox = mark_mails(data_repository, handled=[ref(101)],
                         account=("imap.example.org", "name@example.org"))
    assert mailbox.handled.uids["Posteingang"].uids == [101]


@pytest.mark.parametrize("account", [("imap.other.example", "name@example.org"),
                                     ("imap.example.org", "other@example.org")])
def test_marking_for_another_account_marks_nothing_and_answers_the_stored_mailbox(
        data_repository, account):
    configured(data_repository)
    mailbox = mark_mails(data_repository, handled=[ref(101)], waiting=[ref(102)], account=account)
    assert mailbox == read_mailbox(data_repository) and mailbox.handled.uids == {}
    assert mailbox.waiting.uids == {}


def test_marking_for_an_account_without_a_mailbox_marks_nothing_and_does_not_raise(
        data_repository):
    assert mark_mails(data_repository, handled=[ref(101)], account=("h", "u")) is None
    assert read_mailbox(data_repository) is None


def test_the_file_holds_no_sender_subject_text_or_password(data_repository):
    configured(data_repository)
    mark_mails(data_repository, handled=[ref(101, message_id="<job-alert@sender.example>")])
    text = (data_repository / "mailbox.json").read_text()
    assert "sender.example" not in text and "job-alert" not in text
    assert set(json.loads(text)) <= {"schema_version", "host", "port", "user", "folders",
                                     "max_mails", "since", "last_check_at", "handled", "waiting"}


def test_no_temporary_file_stays_behind(data_repository):
    configured(data_repository)
    mark_mails(data_repository, handled=[ref(101)])
    assert sorted(path.name for path in data_repository.glob("*mailbox*")) == ["mailbox.json"]
