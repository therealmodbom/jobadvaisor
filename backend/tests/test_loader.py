"""One test per `data-repository` spec scenario the loader covers, plus its file-level rules."""

import pytest
from conftest import POSTING, write_json

from jobadvaisor.data.loader import DataRepositoryError, load
from jobadvaisor.settings import Settings


def test_configured_location_loads_every_entity(data_repository, monkeypatch):
    monkeypatch.setenv("DATA_REPOSITORY", str(data_repository))
    repository = load(Settings(_env_file=None).data_repository)
    assert repository.profile.summary == "Backend developer"
    assert [chip.id for chip in repository.policy_pack.reason_chips] == ["too-junior"]
    assert sorted(repository.postings) == ["p1", "p2"]
    assert repository.labels["p1"].verdict == "positive"


def test_missing_location_names_the_setting():
    with pytest.raises(DataRepositoryError, match="DATA_REPOSITORY is not set"):
        load(None)


def test_nonexistent_location_names_the_setting(tmp_path):
    with pytest.raises(DataRepositoryError, match="DATA_REPOSITORY points to .*missing"):
        load(tmp_path / "missing")


def test_invalid_file_names_file_and_field(data_repository):
    broken = {key: value for key, value in POSTING.items() if key != "company"}
    write_json(data_repository / "postings/p2.json", broken)
    with pytest.raises(DataRepositoryError) as error:
        load(data_repository)
    assert "postings/p2.json: company: Field required" in str(error.value)


def test_invalid_file_is_not_used_partially(data_repository):
    write_json(data_repository / "postings/p2.json", {**POSTING, "source_type": "email"})
    with pytest.raises(DataRepositoryError) as error:
        load(data_repository)
    assert error.value.problems == [
        "postings/p2.json: source_type: Input should be 'url', 'text' or 'pdf'"
    ]


def test_unsupported_schema_version_names_file_version_and_supported(data_repository):
    write_json(data_repository / "labels/p1.json", {"schema_version": "7"})
    with pytest.raises(DataRepositoryError, match=(
        r"labels/p1\.json: schema version 7 is not supported \(supported: 1\)"
    )):
        load(data_repository)


def test_posting_loader_accepts_versions_1_and_2(data_repository):
    write_json(data_repository / "postings/p2.json", {**POSTING, "schema_version": "2",
                                                      "status": "done"})
    repository = load(data_repository)
    assert repository.postings["p1"].status == "open"
    assert repository.postings["p2"].status == "done"


def test_posting_version_3_names_both_supported_versions(data_repository):
    write_json(data_repository / "postings/p2.json", {**POSTING, "schema_version": "3"})
    with pytest.raises(DataRepositoryError,
                       match=r"schema version 3 is not supported \(supported: 1, 2\)"):
        load(data_repository)


@pytest.mark.parametrize(("change", "field"), [
    ({"added_at": 1700000000}, "added_at"),
    ({"guard": {"flagged": "yes", "checked_by": "x", "checked_at": "2026-01-05T09:00:00Z"}},
     "guard.flagged"),
])
def test_values_the_schema_rejects_are_not_coerced(data_repository, change, field):
    write_json(data_repository / "postings/p2.json", {**POSTING, **change})
    with pytest.raises(DataRepositoryError, match=f"postings/p2.json: {field}: "):
        load(data_repository)


def test_label_beside_a_misnamed_posting_file_is_an_orphan(data_repository):
    (data_repository / "postings/p1.json").unlink()
    write_json(data_repository / "postings/p1.JSON", POSTING)
    with pytest.raises(DataRepositoryError, match="labels/p1.json: no posting"):
        load(data_repository)


def test_numeric_schema_version_is_a_type_error(data_repository):
    write_json(data_repository / "profile.json", {"schema_version": 1, "summary": "x"})
    with pytest.raises(DataRepositoryError, match="profile.json: schema_version: Input should be"):
        load(data_repository)


def test_file_without_schema_version_is_rejected(data_repository):
    write_json(data_repository / "profile.json", {"summary": "x"})
    with pytest.raises(DataRepositoryError, match="profile.json: schema_version: Field required"):
        load(data_repository)


def test_every_invalid_file_is_reported(data_repository):
    (data_repository / "profile.json").write_text("{not json")
    write_json(data_repository / "postings/p1.json", {"schema_version": "1"})
    with pytest.raises(DataRepositoryError) as error:
        load(data_repository)
    files = {problem.split(":")[0] for problem in error.value.problems}
    assert files == {"profile.json", "postings/p1.json"}


def test_missing_profile_is_reported(data_repository):
    (data_repository / "profile.json").unlink()
    with pytest.raises(DataRepositoryError, match="profile.json: file is missing"):
        load(data_repository)


def test_unsafe_posting_id_is_rejected(data_repository):
    write_json(data_repository / "postings/Bad Name.json", POSTING)
    with pytest.raises(DataRepositoryError, match="postings/Bad Name.json: file name"):
        load(data_repository)


def test_label_without_posting_is_rejected(data_repository):
    (data_repository / "postings/p1.json").unlink()
    with pytest.raises(DataRepositoryError, match="labels/p1.json: no posting postings/p1.json"):
        load(data_repository)


FEATURE_POLICY_PACK = {"schema_version": "1", "feature_set": [
    {"id": "seniority", "description": "Seniority", "type": "categorical",
     "options": ["junior", "senior"]},
    {"id": "remote", "description": "Remote possible", "type": "boolean"}]}


def write_extraction_labels(root, labels, **extra):
    write_json(root / "policy-pack.json", FEATURE_POLICY_PACK)
    write_json(root / "extraction-labels.json",
               {"schema_version": "1", "labels": labels, **extra})


def test_extraction_labels_are_optional(data_repository):
    assert load(data_repository).extraction_labels is None


def test_valid_extraction_labels_load_with_the_minimum_accuracy(data_repository):
    write_extraction_labels(data_repository, {"p1": {"seniority": "senior", "remote": True}},
                            min_accuracy=0.8)
    labels = load(data_repository).extraction_labels
    assert labels.min_accuracy == 0.8
    assert labels.labels == {"p1": {"seniority": "senior", "remote": True}}


def test_extraction_label_may_name_a_default_feature_the_policy_pack_does_not_list(
        data_repository):
    write_extraction_labels(data_repository, {"p1": {"role_type": "backend engineering"}})
    assert load(data_repository).extraction_labels.labels["p1"] == {
        "role_type": "backend engineering"}


def test_extraction_label_for_a_missing_posting_names_file_and_posting(data_repository):
    write_extraction_labels(data_repository, {"gone": {"seniority": "senior"}})
    with pytest.raises(DataRepositoryError, match="extraction-labels.json: .*posting gone"):
        load(data_repository)


def test_extraction_label_for_an_unknown_feature_names_file_posting_and_feature(data_repository):
    write_extraction_labels(data_repository, {"p1": {"salary": "high"}})
    with pytest.raises(DataRepositoryError,
                       match="extraction-labels.json: .*posting p1.*feature salary"):
        load(data_repository)


def test_extraction_minimum_accuracy_out_of_range_names_file_and_value(data_repository):
    write_extraction_labels(data_repository, {}, min_accuracy=1.5)
    with pytest.raises(DataRepositoryError, match=r"extraction-labels.json: min_accuracy.*1\.5"):
        load(data_repository)


def test_integer_label_loads_for_a_number_feature(data_repository):
    write_json(data_repository / "policy-pack.json", {"schema_version": "1", "feature_set": [
        {"id": "years", "description": "Years", "type": "number"}]})
    write_json(data_repository / "extraction-labels.json",
               {"schema_version": "1", "labels": {"p1": {"years": 3}}})
    assert load(data_repository).extraction_labels.labels["p1"]["years"] == 3


def test_demo_persona_loads_without_extraction_labels(demo_copy):
    assert load(demo_copy).extraction_labels is None


def test_empty_posting_and_label_directories_are_optional(tmp_path, data_repository):
    for name in ("profile.json", "policy-pack.json"):
        (tmp_path / "empty" / name).parent.mkdir(exist_ok=True)
        (tmp_path / "empty" / name).write_text((data_repository / name).read_text())
    repository = load(tmp_path / "empty")
    assert repository.postings == {} and repository.labels == {}


def test_file_by_external_writer_loads(data_repository):
    """A file written from the published schema alone, with every optional field set."""
    (data_repository / "postings/ext-1.json").write_text("""{
      "schema_version": "1",
      "title": "Platform Engineer",
      "company": "unknown",
      "location_raw": "Berlin",
      "text": "Imported text.",
      "source_type": "url",
      "urls": ["https://jobs.example.com/42"],
      "added_at": "2025-11-02T08:30:00+01:00",
      "presented_at": "2025-11-03T10:00:00+01:00",
      "guard": {"flagged": true, "categories": ["jailbreaking"], "checked_by": "exporter",
                "checked_at": "2025-11-02T08:30:00Z", "released_at": "2025-11-04T12:00:00Z"},
      "legacy_decision": "discarded"
    }""")
    (data_repository / "labels/ext-1.json").write_text(
        '{"schema_version": "1", "kind": "imported_not_preference", "chips": [], '
        '"note": null, "rated_at": "2025-11-02T08:30:00Z"}'
    )
    repository = load(data_repository)
    assert repository.postings["ext-1"].legacy_decision == "discarded"
    assert repository.labels["ext-1"].verdict is None
