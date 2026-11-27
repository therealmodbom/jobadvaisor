"""`unsettled-links.json`: the model and its writer (`openspec/changes/182-unsettled-links-list/
design.md` D1, D2). Regression tests, no model call."""

import json
import threading

import pytest
from pydantic import ValidationError

from jobadvaisor.data import writer
from jobadvaisor.data.loader import DataRepositoryError
from jobadvaisor.data.models import UnsettledLinks
from jobadvaisor.data.schemas import render
from jobadvaisor.data.writer import read_unsettled_links, update_unsettled_links

ROW = {"url": "https://jobs.example.org/stelle/1", "title": "Platform Engineer",
       "source": "mailbox", "state": "unread", "tries": 1,
       "added_at": "2026-11-27T09:00:00Z", "last_tried_at": "2026-11-27T09:05:00Z",
       "attempts": [{"step": "plain", "outcome": "HTTP 429"}], "reason": None}
FILE = {"schema_version": "1", "links": [ROW]}


def test_a_valid_file_round_trips():
    links = UnsettledLinks.model_validate_json(json.dumps(FILE), strict=True)
    assert links.links[0].attempts[0].outcome == "HTTP 429"
    again = UnsettledLinks.model_validate_json(links.model_dump_json(), strict=True)
    assert again == links


def test_an_unknown_state_is_refused():
    with pytest.raises(ValidationError, match="state"):
        UnsettledLinks.model_validate({**FILE, "links": [ROW | {"state": "lost"}]})


def test_a_naive_datetime_is_refused():
    with pytest.raises(ValidationError, match="added_at"):
        UnsettledLinks.model_validate_json(json.dumps(
            {**FILE, "links": [ROW | {"added_at": "2026-11-27T09:00:00"}]}), strict=True)


def test_an_attempt_holds_no_address():
    with pytest.raises(ValidationError):
        UnsettledLinks.model_validate({**FILE, "links": [ROW | {"attempts": [
            {"step": "plain", "url": "https://hop.example.org/?token=x", "outcome": "HTTP 429"}]}]})


def test_the_published_schema_names_the_states_and_sources():
    schema = json.loads(render()["unsettled-links.schema.json"])
    row = schema["$defs"]["UnsettledLink"]["properties"]
    assert row["state"]["enum"] == ["waiting", "unread", "unclear", "not_reached"]
    assert row["source"]["enum"] == ["mailbox", "paste"]


# --- writer -----------------------------------------------------------------------------------


def test_a_missing_file_reads_as_an_empty_list(tmp_path):
    """data-repository → Scenario: No unsettled links file."""
    assert read_unsettled_links(tmp_path).links == []


def test_an_invalid_file_raises(tmp_path):
    (tmp_path / "unsettled-links.json").write_text("{not json")
    with pytest.raises(DataRepositoryError, match="unsettled-links.json"):
        read_unsettled_links(tmp_path)


def test_an_update_writes_the_change_and_answers_it(tmp_path):
    added = update_unsettled_links(tmp_path, lambda current: UnsettledLinks.model_validate(FILE))
    assert read_unsettled_links(tmp_path) == added and added.links[0].tries == 1
    assert [path.name for path in tmp_path.iterdir()] == ["unsettled-links.json"]


def test_an_invalid_result_raises_and_leaves_the_file_as_it_was(tmp_path):
    update_unsettled_links(tmp_path, lambda current: UnsettledLinks.model_validate(FILE))
    before = (tmp_path / "unsettled-links.json").read_text()

    def negative_tries(current):
        return current.model_copy(update={"links": [current.links[0].model_copy(
            update={"tries": -1})]})
    with pytest.raises(ValueError, match="tries"):
        update_unsettled_links(tmp_path, negative_tries)
    assert (tmp_path / "unsettled-links.json").read_text() == before


def test_an_update_waits_for_the_write_gate(tmp_path):
    done = threading.Event()
    thread = threading.Thread(target=lambda: (update_unsettled_links(
        tmp_path, lambda current: current), done.set()))
    with writer.write_gate:
        thread.start()
        assert not done.wait(0.2), "the update did not wait for the write gate"
    assert done.wait(10)
    thread.join(10)
