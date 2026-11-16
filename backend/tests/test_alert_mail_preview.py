"""The preview of a pasted mail (`design.md` → Duplicate key, Record for #109): stored and
login-walled marks, and one record line per mail."""

import json
from datetime import UTC, datetime

import pytest
from conftest import write_json
from test_alert_mail import NoGuard, Untouchable, fixture
from test_alert_mail_model import Broken
from test_guard import THRESHOLDS
from test_triage_graph import POLICY_PACK

from jobadvaisor.data.models import Posting
from jobadvaisor.intake.alert_mail import FinderError, preview
from jobadvaisor.intake.postings import Intake
from jobadvaisor.tools.guard import ContentGuard


class CountingIntake(Intake):
    """An intake whose stored postings are given, counting each `postings()` read."""

    def postings(self):
        object.__setattr__(self, "reads", getattr(self, "reads", 0) + 1)
        return self.stored


def stored_posting(url: str, title: str) -> Posting:
    return Posting(schema_version="2", text="Text", source_type="url", urls=[url],
                   added_at=datetime.now(UTC), title=title, company="Firma", location_raw="Ort")


@pytest.fixture
def intake(tmp_path):
    write_json(tmp_path / "policy-pack.json", POLICY_PACK)
    made = CountingIntake(tmp_path, Untouchable(), NoGuard())
    object.__setattr__(made, "stored", {"20261101-nordlicht": stored_posting(
        "https://www.linkedin.com/jobs/view/4100000101", "Leitung Softwareplattform")})
    return made


def test_a_stored_posting_is_named(intake, tmp_path):
    answer = preview(intake, fixture("linkedin-digest.html"), "", tmp_path / "alert-mails.jsonl")
    marks = [entry["duplicate"] for entry in answer["entries"]]
    assert marks[0] == {"posting_id": "20261101-nordlicht", "title": "Leitung Softwareplattform"}
    assert marks[1:] == [None] * 5


def test_postings_are_read_once_per_preview(intake, tmp_path):
    preview(intake, fixture("career-site-a.html"), "", tmp_path / "alert-mails.jsonl")
    assert intake.reads == 1


def test_a_login_walled_host_is_marked(intake, tmp_path):
    html = ('<a href="https://www.xing.com/job/Leitung/12345/?refid=TOKEN-1">Leitung - Ort, DE</a>'
            '<a href="https://careers.example.com/job/A/2000000001/?refid=TOKEN-2">A - Ort, DE</a>')
    answer = preview(intake, html, "", tmp_path / "alert-mails.jsonl")
    assert [entry["login_walled"] for entry in answer["entries"]] == [True, False]


def test_the_record_holds_no_path_query_or_title(intake, tmp_path):
    record = tmp_path / "state" / "alert-mails.jsonl"
    preview(intake, fixture("career-site-a.html"), "", record)
    preview(intake, fixture("ba-list.html"), "", record)
    lines = [json.loads(line) for line in record.read_text().splitlines()]
    assert [line["read_by"] for line in lines] == [["career_site"], ["bundesagentur"]]
    assert lines[0]["hosts"] == {"careers.example.com": 12, "careers-admin.example.net": 2}
    assert lines[0]["entries"] == 10 and lines[0]["held"] is False
    assert set(lines[0]) == {"at", "read_by", "hosts", "entries", "held", "model_skipped"}
    text = record.read_text()
    assert "/job/" not in text and "TOKEN" not in text and "Berater" not in text


def test_a_failed_preview_still_writes_a_record_line(tmp_path):
    write_json(tmp_path / "policy-pack.json", POLICY_PACK)
    failing = CountingIntake(tmp_path, Untouchable(), ContentGuard(Broken(), THRESHOLDS))
    object.__setattr__(failing, "stored", {})
    record = tmp_path / "alert-mails.jsonl"
    with pytest.raises(FinderError, match="screening failed"):
        preview(failing, fixture("unknown-jobid.html"), "", record)
    line = json.loads(record.read_text())
    assert line["failed"] == "screening failed" and set(line) == {"at", "failed"}


def test_a_failed_record_write_is_ignored(intake, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")
    answer = preview(intake, fixture("ba-list.html"), "", blocker / "alert-mails.jsonl")
    assert len(answer["entries"]) == 3
