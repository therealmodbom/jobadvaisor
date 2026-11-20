import json
from datetime import UTC, datetime

import pytest

from jobadvaisor.data.loader import load
from jobadvaisor.data.models import Availability, Guard, Label
from jobadvaisor.data.writer import (
    read_posting,
    update_posting,
    write_availability,
    write_guard,
    write_label,
)

LABEL = Label(schema_version="1", kind="rating", verdict="negative", chips=["too-junior"],
              note="Too many on-call weeks.", rated_at=datetime(2026, 2, 1, 14, 30, tzinfo=UTC))


def test_written_label_reloads_unchanged(data_repository):
    path = write_label(data_repository, "p2", LABEL)
    assert path == data_repository / "labels/p2.json"
    assert load(data_repository).labels["p2"] == LABEL


def test_label_without_verdict_reloads_unchanged(data_repository):
    label = Label(schema_version="1", kind="imported_not_preference", rated_at=LABEL.rated_at)
    write_label(data_repository, "p2", label)
    assert '"verdict"' not in (data_repository / "labels/p2.json").read_text()
    assert load(data_repository).labels["p2"] == label


def test_label_without_strength_writes_no_strength_key(data_repository):
    write_label(data_repository, "p2", LABEL)
    assert '"strength"' not in (data_repository / "labels/p2.json").read_text()


def test_label_with_strength_reloads_unchanged(data_repository):
    label = LABEL.model_copy(update={"strength": "weak"})
    write_label(data_repository, "p2", label)
    assert '"strength": "weak"' in (data_repository / "labels/p2.json").read_text()
    assert load(data_repository).labels["p2"] == label


def test_rewriting_a_label_replaces_it(data_repository):
    write_label(data_repository, "p1", LABEL)
    assert load(data_repository).labels["p1"] == LABEL
    assert [path.name for path in (data_repository / "labels").iterdir()] == ["p1.json"]


def test_label_changed_into_an_invalid_one_is_refused(data_repository):
    label = LABEL.model_copy()
    label.verdict = None
    with pytest.raises(ValueError, match="verdict"):
        write_label(data_repository, "p2", label)
    assert not (data_repository / "labels/p2.json").exists()


def test_label_for_unknown_posting_is_refused(data_repository):
    with pytest.raises(ValueError, match="no posting postings/p9.json"):
        write_label(data_repository, "p9", LABEL)


def test_unsafe_posting_id_is_refused(data_repository):
    with pytest.raises(ValueError, match="posting ID"):
        write_label(data_repository, "../profile", LABEL)


GUARD = Guard(flagged=True, categories=["jailbreaking"], checked_by="stub",
              checked_at=datetime(2026, 2, 1, 14, 30, tzinfo=UTC))


def test_write_guard_sets_only_the_guard_of_the_posting_on_disk(data_repository):
    before = load(data_repository).postings["p1"]
    (data_repository / "postings/p1.json").write_text(
        before.model_copy(update={"title": "Edited meanwhile"}).model_dump_json())
    written = write_guard(data_repository, "p1", GUARD)
    reloaded = load(data_repository).postings["p1"]
    assert reloaded == written and reloaded.guard == GUARD
    assert reloaded.title == "Edited meanwhile"
    assert '"released_at"' not in (data_repository / "postings/p1.json").read_text()


def checked(state: str = "closed") -> Availability:
    return Availability(state=state, set_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC), set_by="check")


def by_user(state: str = "available") -> dict:
    return {"state": state, "set_at": "2026-03-01T10:00:00Z", "set_by": "user"}


def test_write_availability_sets_only_the_availability_of_the_posting_on_disk(data_repository):
    path = data_repository / "postings/p1.json"
    before = json.loads(path.read_text())
    assert write_availability(data_repository, "p1", checked(), None) is True
    after = json.loads(path.read_text())
    assert after == before | {"availability": {"state": "closed",
                                               "set_at": "2026-03-01T09:00:00Z",
                                               "set_by": "check"}}
    assert after["schema_version"] == before["schema_version"] == "1"
    assert load(data_repository).postings["p1"].availability == checked()


def test_write_availability_replaces_an_availability_equal_to_the_snapshot(data_repository):
    write_availability(data_repository, "p1", checked("unknown"), None)
    assert write_availability(data_repository, "p1", checked("available"),
                              checked("unknown")) is True
    assert read_posting(data_repository, "p1").availability.state == "available"


def test_write_availability_replaces_a_hand_setting_that_is_the_snapshot(data_repository):
    update_posting(data_repository, "p1", {"availability": by_user("closed")})
    snapshot = read_posting(data_repository, "p1").availability
    assert write_availability(data_repository, "p1", checked("available"), snapshot) is True
    assert read_posting(data_repository, "p1").availability == checked("available")


def test_a_hand_setting_made_after_the_checks_read_survives_its_write(data_repository):
    to_check = read_posting(data_repository, "p1")  # what the check started from
    assert to_check.availability is None
    update_posting(data_repository, "p1", {"availability": by_user()})  # the user, meanwhile
    assert write_availability(data_repository, "p1", checked("closed"),
                              to_check.availability) is False
    assert read_posting(data_repository, "p1").availability.set_by == "user"
    assert read_posting(data_repository, "p1").availability.state == "available"


def test_a_value_set_again_after_the_snapshot_differs_from_it(data_repository):
    update_posting(data_repository, "p1", {"availability": by_user()})
    snapshot = read_posting(data_repository, "p1").availability
    update_posting(data_repository, "p1",
                   {"availability": by_user() | {"set_at": "2026-03-02T10:00:00Z"}})
    assert write_availability(data_repository, "p1", checked("closed"), snapshot) is False
    assert read_posting(data_repository, "p1").availability.set_at.day == 2


def test_write_availability_never_writes_unknown_over_closed(data_repository):
    write_availability(data_repository, "p1", checked("closed"), None)
    before = (data_repository / "postings/p1.json").read_text()
    assert write_availability(data_repository, "p1", checked("unknown"), checked("closed")) is False
    assert (data_repository / "postings/p1.json").read_text() == before


def test_write_availability_for_a_missing_posting_writes_nothing(data_repository):
    assert write_availability(data_repository, "p9", checked(), None) is False
    assert not (data_repository / "postings/p9.json").exists()


def test_write_availability_refuses_an_unsafe_posting_id(data_repository):
    with pytest.raises(ValueError, match="posting ID"):
        write_availability(data_repository, "../profile", checked(), None)


def test_write_guard_refuses_an_unsafe_or_unknown_posting(data_repository):
    with pytest.raises(ValueError, match="posting ID"):
        write_guard(data_repository, "../profile", GUARD)
    with pytest.raises(ValueError, match="no posting postings/p9.json"):
        write_guard(data_repository, "p9", GUARD)
