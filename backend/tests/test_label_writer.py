import json
from datetime import UTC, datetime

import pytest
from conftest import git, write_json

from jobadvaisor.data.backup import commit_message
from jobadvaisor.data.loader import load
from jobadvaisor.data.models import Availability, Guard, Label, Score
from jobadvaisor.data.writer import (
    delete_posting,
    read_posting,
    read_score,
    update_posting,
    write_availability,
    write_guard,
    write_label,
    write_score,
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


SCORE = Score(schema_version="1", score=7, reasoning="Fits.",
              scored_at=datetime(2026, 2, 1, 15, 0, tzinfo=UTC))


def with_records(root, posting_id: str) -> None:
    """Give `posting_id` a label, a score and a hand-settled value, beside `p1`'s own."""
    write_label(root, posting_id, LABEL)
    write_score(root, posting_id, SCORE)
    write_json(root / "extraction-labels.json", {
        "schema_version": "1", "min_accuracy": 0.8,
        "labels": {"p1": {"role_type": "backend"}, posting_id: {"role_type": "data"}}})


def test_a_deleted_posting_loses_every_record_and_the_others_keep_theirs(data_repository):
    write_score(data_repository, "p1", SCORE)
    with_records(data_repository, "p2")
    delete_posting(data_repository, "p2")
    assert not any((data_repository / name / "p2.json").exists()
                   for name in ("postings", "labels", "scores"))
    repository = load(data_repository)
    assert set(repository.postings) == {"p1"} and set(repository.labels) == {"p1"}
    assert read_score(data_repository, "p1") == SCORE
    assert repository.extraction_labels.labels == {"p1": {"role_type": "backend"}}
    assert repository.extraction_labels.min_accuracy == 0.8


def test_a_posting_without_label_score_or_hand_settled_values_deletes_cleanly(data_repository):
    delete_posting(data_repository, "p2")
    assert set(load(data_repository).postings) == {"p1"}
    assert not (data_repository / "extraction-labels.json").exists()
    assert (data_repository / "labels/p1.json").exists()


def test_an_extraction_labels_file_without_the_posting_is_left_alone(data_repository):
    write_json(data_repository / "extraction-labels.json",
               {"schema_version": "1", "labels": {"p1": {"role_type": "backend"}}})
    before = (data_repository / "extraction-labels.json").read_text()
    delete_posting(data_repository, "p2")
    assert (data_repository / "extraction-labels.json").read_text() == before


def test_deleting_an_unknown_posting_raises_key_error_and_changes_nothing(data_repository):
    with pytest.raises(KeyError):
        delete_posting(data_repository, "p9")
    assert set(load(data_repository).postings) == {"p1", "p2"}


def test_deleting_twice_raises_key_error_the_second_time(data_repository):
    delete_posting(data_repository, "p2")
    with pytest.raises(KeyError):
        delete_posting(data_repository, "p2")


@pytest.mark.parametrize("posting_id", ["../profile", "Bad_ID", ""])
def test_deleting_an_unsafe_id_raises_value_error(data_repository, posting_id):
    with pytest.raises(ValueError, match="posting ID"):
        delete_posting(data_repository, posting_id)
    assert (data_repository / "profile.json").exists()


def test_the_backup_commits_a_delete_as_one_rating_one_score_and_one_posting(backed_up):
    root = backed_up.root
    write_score(root, "demo-001", SCORE)
    git(root, "add", "-A")
    git(root, "commit", "-m", "score")
    delete_posting(root, "demo-001")
    git(root, "add", "-A")
    staged = [path for path in git(root, "diff", "--cached", "--name-only", "-z").split("\0")
              if path]
    assert sorted(staged) == ["labels/demo-001.json", "postings/demo-001.json",
                              "scores/demo-001.json"]
    assert commit_message(staged) == "Backup: 1 rating, 1 score, 1 posting"
    assert "demo-001" not in load(root).postings
