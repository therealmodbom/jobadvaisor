"""`unsettled-links.json`: the model and its writer (`openspec/changes/182-unsettled-links-list/
design.md` D1, D2). Regression tests, no model call."""

import json

import pytest
from pydantic import ValidationError

from jobadvaisor.data.models import UnsettledLinks
from jobadvaisor.data.schemas import render

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

