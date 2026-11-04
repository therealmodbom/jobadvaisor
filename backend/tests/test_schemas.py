import json

from jobadvaisor.data.models import POSTING_ID_PATTERN
from jobadvaisor.data.schemas import SCHEMA_DIRECTORY, drift, render, write


def test_committed_schemas_match_the_models():
    """CI's drift check. On failure, run `uv run python -m jobadvaisor.data.schemas` in `backend/`
    and commit the result."""
    assert drift(SCHEMA_DIRECTORY) == []


def test_hand_edit_is_reported_as_drift(tmp_path):
    write(tmp_path)
    edited = tmp_path / "posting.schema.json"
    edited.write_text(edited.read_text().replace('"title"', '"headline"'))
    (tmp_path / "stale.schema.json").write_text("{}")
    assert drift(tmp_path) == ["posting.schema.json", "stale.schema.json"]


def test_missing_schema_is_reported_as_drift(tmp_path):
    write(tmp_path)
    (tmp_path / "label.schema.json").unlink()
    assert drift(tmp_path) == ["label.schema.json"]


def test_posting_schema_states_the_id_pattern_the_loader_enforces():
    assert POSTING_ID_PATTERN in json.loads(render()["posting.schema.json"])["description"]


def test_each_schema_declares_draft_2020_12_and_its_version():
    for name, content in render().items():
        schema = json.loads(content)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema", name
        version = schema["properties"]["schema_version"]
        assert (version.get("enum") or [version["const"]]) == (
            ["1", "2"] if name == "posting.schema.json" else ["1"]), name
        assert "schema_version" in schema["required"], name
