from datetime import UTC, datetime

import pytest

from jobadvaisor.data.loader import load
from jobadvaisor.data.models import Guard, Label
from jobadvaisor.data.writer import write_guard, write_label

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


def test_write_guard_refuses_an_unsafe_or_unknown_posting(data_repository):
    with pytest.raises(ValueError, match="posting ID"):
        write_guard(data_repository, "../profile", GUARD)
    with pytest.raises(ValueError, match="no posting postings/p9.json"):
        write_guard(data_repository, "p9", GUARD)
