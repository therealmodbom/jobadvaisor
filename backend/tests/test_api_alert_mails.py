"""`/alert-mails` endpoints (`openspec/changes/alert-mail-intake/design.md` → API)."""

import time

import pytest
from conftest import FakeStructuredModel, write_json
from fastapi.testclient import TestClient
from test_alert_mail import fixture
from test_alert_mail_model import Broken, FlagAll, number_of
from test_guard import THRESHOLDS, StubClassifier
from test_triage_graph import POLICY_PACK, Harness, add_posting

import jobadvaisor.intake.alert_runs as runs_module
from jobadvaisor.api.app import create_app
from jobadvaisor.intake.postings import Intake
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.triage.runs import Runs


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DIRECTORY", str(tmp_path / "state"))
    root = tmp_path / "data"
    write_json(root / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(root / "policy-pack.json", POLICY_PACK)
    add_posting(root, "p1", "Engineer 1")
    return root


def client(tmp_path, root, model=None, classifier=None) -> TestClient:
    harness = Harness(tmp_path, root)
    guard = ContentGuard(classifier, THRESHOLDS if classifier else {})
    intake = Intake(root, model or FakeStructuredModel(), guard)
    return TestClient(create_app(Runs(harness.graph, harness.context), intake,
                                 frontend=root / "no-frontend-build"),
                      raise_server_exceptions=False)


def store_linkedin_job(root):
    path = root / "postings" / "p1.json"
    path.write_text(path.read_text().replace(
        '"source_type"', '"urls": ["https://www.linkedin.com/jobs/view/4100000101"], '
        '"source_type"', 1))


def test_preview_of_a_rule_mail_marks_a_stored_posting(tmp_path, root):
    store_linkedin_job(root)
    answer = client(tmp_path, root).post("/alert-mails/preview", json={
        "html": fixture("linkedin-digest.html"), "text": ""})
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["entries"][0]["duplicate"] == {"posting_id": "p1", "title": "Engineer 1"}
    assert len(body["entries"]) == 6 and body["read_by"] == ["linkedin"]
    assert body["unread_hosts"] == [] and body["screening"] is False
    assert set(body) == {"entries", "read_by", "unread_hosts", "held", "model_skipped",
                         "screening", "truncated"}
    assert (tmp_path / "state").exists()


def test_preview_names_unread_hosts(tmp_path, root):
    html = fixture("linkedin-digest.html") + fixture("unknown-jobid.html")
    body = client(tmp_path, root).post("/alert-mails/preview", json={"html": html}).json()
    assert {"host": "jobs.example.net", "links": 4} in body["unread_hosts"]


def test_preview_held_by_a_flagging_classifier(tmp_path, root):
    body = client(tmp_path, root, classifier=FlagAll()).post("/alert-mails/preview", json={
        "html": fixture("injection.html")}).json()
    assert body["held"] is True and body["entries"] == [] and body["screening"] is True


def test_preview_without_a_classifier_skips_the_model(tmp_path, root):
    body = client(tmp_path, root).post("/alert-mails/preview", json={
        "html": fixture("unknown-jobid.html")}).json()
    assert body["model_skipped"] == "screening off" and body["entries"] == []


def test_preview_with_a_failing_classifier_is_502(tmp_path, root):
    answer = client(tmp_path, root, classifier=Broken()).post("/alert-mails/preview", json={
        "html": fixture("unknown-jobid.html")})
    assert answer.status_code == 502 and answer.json()["error"] == "screening failed"


def test_preview_with_a_failing_model_is_502(tmp_path, root):
    class Failing:
        def with_structured_output(self, schema):
            raise RuntimeError("provider down")

    answer = client(tmp_path, root, Failing(), StubClassifier()).post(
        "/alert-mails/preview", json={"html": fixture("unknown-jobid.html")})
    assert answer.status_code == 502 and answer.json()["error"] == "finder failed"


def test_preview_through_the_model(tmp_path, root):
    html = fixture("unknown-jobid.html")
    model = FakeStructuredModel({"postings": [
        {"link": number_of(html, "Produktmanager"), "title": "Produktmanager (f/m/d)"}]})
    body = client(tmp_path, root, model, StubClassifier()).post(
        "/alert-mails/preview", json={"html": html}).json()
    assert body["read_by"] == ["model"] and [e["url"] for e in body["entries"]] == [
        "https://jobs.example.net/de_DE/externaljobs/JobDetail?jobId=700001"]


@pytest.mark.parametrize("body", [
    {"html": None, "text": "  "}, {"html": "", "text": ""}, {"text": "x" * 2_000_001},
    {"html": "x" * 2_000_001, "text": ""}, {"html": 5, "text": ""}])
def test_preview_rejects_empty_and_oversized_input(tmp_path, root, body):
    answer = client(tmp_path, root).post("/alert-mails/preview", json=body)
    assert answer.status_code == 422 and answer.json()["error"] == "invalid request"


@pytest.mark.parametrize("html", ["", "   "])
def test_a_blank_html_part_falls_back_to_the_text(tmp_path, root, html):
    text = "Senior Dev\nhttps://www.linkedin.com/jobs/view/4100000123"
    answer = client(tmp_path, root).post("/alert-mails/preview", json={"html": html, "text": text})
    assert [e["url"] for e in answer.json()["entries"]] == [
        "https://www.linkedin.com/jobs/view/4100000123"]


def fake_add(outcomes):
    def add(intake, url, *, allow_text_duplicate=False):
        posting_id, reason = outcomes[url]
        if reason == "text" and allow_text_duplicate:
            return "neu", None, None, []
        return posting_id, None, reason, []
    return add


def settled(http: TestClient, run_id: str) -> dict:
    deadline = time.monotonic() + 10
    while (state := http.get(f"/alert-mails/runs/{run_id}").json())["status"] == "running":
        assert time.monotonic() < deadline, "run never settled"
        time.sleep(0.02)
    return state


A, B = "https://jobs.example.org/stelle/1", "https://jobs.example.org/stelle/2"


def test_a_run_is_started_and_polled_to_done(tmp_path, root, monkeypatch):
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({A: ("a", None), B: ("p1", "url")}))
    http = client(tmp_path, root)
    answer = http.post("/alert-mails/runs", json={"entries": [{"url": A, "title": "A"},
                                                              {"url": B, "title": "B"}]})
    assert answer.status_code == 202
    state = settled(http, answer.json()["run_id"])
    assert state["status"] == "done" and state["done"] == state["total"] == 2
    assert [(e["state"], e.get("duplicate_by")) for e in state["entries"]] == [
        ("stored", None), ("duplicate", "url")]


def test_force_stores_a_text_duplicate_and_defaults_to_false(tmp_path, root, monkeypatch):
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({A: ("p1", "text")}))
    http = client(tmp_path, root)
    plain = settled(http, http.post("/alert-mails/runs", json={
        "entries": [{"url": A, "title": "A"}]}).json()["run_id"])
    forced = settled(http, http.post("/alert-mails/runs", json={
        "entries": [{"url": A, "title": "A", "force": True}]}).json()["run_id"])
    assert plain["entries"][0]["duplicate_by"] == "text"
    assert (forced["entries"][0]["state"], forced["entries"][0]["posting_id"]) == ("stored", "neu")


def test_a_second_run_is_409_naming_the_first(tmp_path, root, monkeypatch):
    import threading
    release = threading.Event()

    def held(intake, url, *, allow_text_duplicate=False):
        release.wait(30)
        return "a", None, None, []
    monkeypatch.setattr(runs_module, "add_from_url", held)
    http = client(tmp_path, root)
    first = http.post("/alert-mails/runs", json={"entries": [{"url": A, "title": "A"}]})
    second = http.post("/alert-mails/runs", json={"entries": [{"url": B, "title": "B"}]})
    release.set()
    assert second.status_code == 409
    assert second.json()["error"] == "alert run in progress"
    assert second.json()["run_id"] == first.json()["run_id"]


def test_an_unknown_run_is_404(tmp_path, root):
    assert client(tmp_path, root).get("/alert-mails/runs/nope").status_code == 404


def test_a_raw_link_is_cleaned_on_start(tmp_path, root, monkeypatch):
    seen = []

    def add(intake, url, *, allow_text_duplicate=False):
        seen.append(url)
        return "a", None, None, []
    monkeypatch.setattr(runs_module, "add_from_url", add)
    http = client(tmp_path, root)
    raw = "https://www.linkedin.com/comm/jobs/view/4100000101/?otpToken=TOKEN-7&trk=TOKEN-4"
    state = settled(http, http.post("/alert-mails/runs", json={
        "entries": [{"url": raw, "title": "A"}]}).json()["run_id"])
    assert seen == ["https://www.linkedin.com/jobs/view/4100000101"]
    assert state["entries"][0]["url"] == "https://www.linkedin.com/jobs/view/4100000101"


@pytest.mark.parametrize("body", [
    {"entries": []}, {"entries": [{"url": "ftp://x.example.com/1", "title": "A"}]},
    {"entries": [{"url": "http://127.1/job/1", "title": "A"}]},
    {"entries": [{"url": "http://169.254.169.254/latest", "title": "A"}]},
    {"entries": [{"url": A, "title": "A"}] * 101}, {"entries": [{"url": A, "force": "yes"}]}])
def test_a_run_rejects_invalid_entries(tmp_path, root, body):
    answer = client(tmp_path, root).post("/alert-mails/runs", json=body)
    assert answer.status_code == 422 and answer.json()["error"] == "invalid request"
