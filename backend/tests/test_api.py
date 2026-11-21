import json
import threading
import time
from datetime import UTC, datetime

import pytest
from conftest import LABEL, FakeStructuredModel, ScriptedModel, write_json
from fastapi.testclient import TestClient
from test_availability import Clock, Site, reply
from test_triage_graph import (
    FLAGGED,
    POLICY_PACK,
    Harness,
    StubClassifier,
    add_posting,
    judge_by_title,
)

from jobadvaisor.api import app as app_module
from jobadvaisor.api.app import configured_intake, configured_runs, create_app
from jobadvaisor.availability import AvailabilityChecks, check_batch
from jobadvaisor.data.loader import DataRepositoryError
from jobadvaisor.data.loader import load as load_repository
from jobadvaisor.data.writer import delete_posting, read_pool, read_posting, read_score
from jobadvaisor.intake.ladder import LadderResult
from jobadvaisor.intake.postings import Intake
from jobadvaisor.settings import Settings
from jobadvaisor.triage.graph import checkpoint_path
from jobadvaisor.triage.runs import Runs


class Api:
    """A test client over a triage graph with fake models; the judge waits for `gate`."""

    def __init__(self, harness: Harness, checks: AvailabilityChecks | None = None):
        self.harness, self.gate = harness, threading.Event()
        self.entered = threading.Event()  # set when the judge is first called
        self.gate.set()
        harness.judge = ScriptedModel(self._judge)
        self.runs = Runs(harness.graph, harness.context)
        self.started: list[bool] = []  # the `rescore` of every pass started
        start = self.runs.start
        self.runs.start = lambda rescore=False: (
            self.started.append(rescore), start(rescore))[1]
        self.client = TestClient(create_app(self.runs,
                                            Intake(harness.root, FakeStructuredModel(),
                                                   harness.guard),
                                            checks=checks,
                                            frontend=harness.root / "no-frontend-build"),
                                 raise_server_exceptions=False)

    def _judge(self, schema, prompt):
        self.entered.set()
        assert self.gate.wait(10), "gate never opened"
        return judge_by_title(schema, prompt)

    def start(self, variant: str = "unscored") -> str:
        """Start a pass of `variant` and return its ID."""
        response = self.client.post("/pool/passes", json={"variant": variant})
        assert response.status_code == 202, response.text
        return response.json()["pass_id"]

    def settled(self, pass_id: str) -> dict:
        """The pass once it no longer computes."""
        deadline = time.monotonic() + 10
        url = f"/pool/passes/{pass_id}"
        while (progress := self.client.get(url).json())["status"] == "running":
            assert time.monotonic() < deadline, "pass never settled"
            time.sleep(0.02)
        return progress


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "data"
    write_json(root / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(root / "policy-pack.json", POLICY_PACK)
    for n in range(1, 6):
        add_posting(root, f"p{n}", f"Engineer {n}")
    add_posting(root, "sales", "Sales Lead")
    return root


@pytest.fixture
def api(tmp_path, root) -> Api:
    return Api(Harness(tmp_path, root))


def test_start_returns_a_pass_id_before_the_pass_finishes(api):
    api.gate.clear()
    pass_id = api.start()
    assert api.client.get(f"/pool/passes/{pass_id}").json()["status"] == "running"
    busy = api.client.post("/pool/passes", json={"variant": "unscored"})
    assert busy.status_code == 409 and busy.json()["error"] == "pass in progress"
    assert pass_id in busy.json()["detail"]
    api.gate.set()
    progress = api.settled(pass_id)
    assert progress["status"] == "done", progress


def test_a_read_racing_the_pass_end_reports_it_running(api, monkeypatch):
    graph, get_state = api.harness.graph, api.harness.graph.get_state

    def snapshot_then_let_the_pass_finish(config):
        snapshot = get_state(config)
        api.gate.set()
        time.sleep(1)  # the pass ends here, unless the read holds it off
        return snapshot

    api.gate.clear()
    pass_id = api.start()
    monkeypatch.setattr(graph, "get_state", snapshot_then_let_the_pass_finish)
    status = api.client.get(f"/pool/passes/{pass_id}").json().get("status")
    monkeypatch.setattr(graph, "get_state", get_state)
    assert status == "running"
    assert api.settled(pass_id)["status"] == "done"


def test_a_finished_pass_reports_its_last_progress_and_the_scores_it_stored(api, root):
    progress = api.settled(api.start())
    assert progress["scored"] == 5 and progress["unscreened"] == []
    assert progress["error"] is None and progress["started_at"]
    assert progress["cancel_requested"] is False
    assert progress["progress"] == {"phase": "storing", "score": {"done": 5, "total": 5}}
    assert set(progress) == {"pass_id", "status", "started_at", "error", "progress",
                             "cancel_requested", "scored", "unscreened"}
    assert read_score(root, "p5").score == 5
    assert read_pool(root).passes[0].scored == 5


def test_progress_is_readable_while_the_pass_computes(api):
    api.gate.clear()
    pass_id = api.start()
    assert api.entered.wait(10)
    progress = api.client.get(f"/pool/passes/{pass_id}").json()
    assert progress["status"] == "running" and progress["scored"] == 0
    assert progress["progress"] == {"phase": "scoring", "score": {"done": 0, "total": 5}}
    api.gate.set()
    api.settled(pass_id)


def test_a_pass_that_fails_before_its_first_step_reports_failed(api, root):
    write_json(root / "postings/broken.json", {"schema_version": "1"})
    progress = api.settled(api.start())
    assert progress["status"] == "failed" and "postings/broken.json" in progress["error"]
    assert progress["progress"] is None and progress["scored"] == 0
    assert progress["cancel_requested"] is False and progress["unscreened"] == []


def test_unknown_pass_answers_with_error_and_detail(api):
    unknown = api.client.get("/pool/passes/nope")
    assert unknown.status_code == 404 and set(unknown.json()) == {"error", "detail"}
    answer = api.client.post("/pool/passes/nope/unscreened", json={"continue": True})
    assert answer.status_code == 404 and set(answer.json()) == {"error", "detail"}
    cancel = api.client.post("/pool/passes/nope/cancel")
    assert cancel.status_code == 404 and cancel.json()["error"] == "not found"
    assert set(cancel.json()) == {"error", "detail"}


def test_cancel_answers_202_and_the_pass_stops_after_its_posting_with_its_scores_stored(api, root):
    api.gate.clear()
    pass_id = api.start()
    assert api.entered.wait(10)
    answer = api.client.post(f"/pool/passes/{pass_id}/cancel")
    assert answer.status_code == 202 and answer.json() == {"pass_id": pass_id}
    requested = api.client.get(f"/pool/passes/{pass_id}").json()
    assert requested["status"] == "running" and requested["cancel_requested"] is True
    api.gate.set()
    ended = api.settled(pass_id)
    assert ended["status"] == "cancelled" and ended["cancel_requested"] is False
    assert ended["scored"] == 1 and ended["error"] is None
    assert read_score(root, "p1").score == 1 and read_score(root, "p2") is None
    assert read_pool(root).passes[0].cancelled is True


def test_cancel_of_a_pass_that_waits_for_the_answer_or_has_ended_is_409_not_running(
        unscreened):
    waiting = unscreened.settled(unscreened.start())["pass_id"]
    refused = unscreened.client.post(f"/pool/passes/{waiting}/cancel")
    assert refused.status_code == 409 and refused.json()["error"] == "pass not running"
    assert set(refused.json()) == {"error", "detail"}
    assert unscreened.client.get(f"/pool/passes/{waiting}").json()["status"] == "awaiting_answer"
    unscreened.client.post(f"/pool/passes/{waiting}/unscreened", json={"continue": True})
    assert unscreened.settled(waiting)["status"] == "done"
    ended = unscreened.client.post(f"/pool/passes/{waiting}/cancel")
    assert ended.status_code == 409 and ended.json()["error"] == "pass not running"
    assert unscreened.client.get(f"/pool/passes/{waiting}").json()["status"] == "done"


def test_cancel_of_a_single_score_is_404_and_the_score_goes_on(api, root):
    api.gate.clear()
    answers = []
    single = threading.Thread(target=lambda: answers.append(post_score(api, "p2").status_code))
    single.start()
    assert api.entered.wait(10)
    refused = api.client.post("/pool/passes/score:p2/cancel")
    assert refused.status_code == 404 and refused.json()["error"] == "not found"
    api.gate.set()
    single.join(10)
    assert answers == [200] and read_score(root, "p2").score == 2


def test_the_old_run_routes_the_rating_route_and_the_run_list_are_gone(api):
    pass_id = api.settled(api.start())["pass_id"]
    rated = api.client.post(f"/pool/passes/{pass_id}/ratings",
                            json={"ratings": [{"posting_id": "p1", "verdict": "positive"}]})
    assert rated.status_code == 404
    assert api.client.get("/runs").status_code == 404
    assert api.client.post("/runs").status_code == 404
    assert api.client.get(f"/runs/{pass_id}").status_code == 404
    answered = api.client.post(f"/runs/{pass_id}/unscreened", json={"continue": True})
    assert answered.status_code == 404


def test_new_label_is_retrievable_in_the_next_pass_without_a_rebuild(api, root):
    api.settled(api.start("all"))
    write_json(root / "labels/p5.json", LABEL)
    add_posting(root, "similar", "Engineer 8")
    progress = api.settled(api.start())
    assert progress["scored"] == 1
    assert "p5" in read_score(root, "similar").example_ids


def test_configured_app_keeps_its_checkpoints_under_the_state_directory(tmp_path, demo_copy):
    settings = Settings(_env_file=None, data_repository=demo_copy,
                        state_directory=tmp_path / "state", llm_model="openai:gpt-test",
                        llm_api_key="unused", embedding_model="openai:text-embedding-test")
    client = TestClient(create_app(configured_runs(settings), configured_intake(settings)))
    assert client.get("/pool/passes/nope").status_code == 404
    assert checkpoint_path(settings, demo_copy).is_file()
    assert checkpoint_path(settings, demo_copy).is_relative_to(tmp_path / "state")
    with pytest.raises(DataRepositoryError):
        configured_runs(Settings(_env_file=None, state_directory=tmp_path / "state"))


@pytest.fixture
def unscreened(tmp_path, root) -> Api:
    add_posting(root, "unscreened", "Unscreened Engineer 2", guard=None)
    return Api(Harness(tmp_path, root))


def test_pass_paused_over_unscreened_postings_reports_them_with_title_and_company(unscreened):
    progress = unscreened.settled(unscreened.start())
    assert progress["status"] == "awaiting_answer"
    assert progress["unscreened"] == [{"posting_id": "unscreened",
                                       "title": "Unscreened Engineer 2",
                                       "company": "Example Corp"}]
    assert progress["scored"] == 0 and progress["progress"]["phase"] == "checking"
    assert unscreened.harness.judge.calls == []


def test_an_unscreened_posting_that_is_gone_falls_back_to_its_id(unscreened, root):
    pass_id = unscreened.start()
    unscreened.settled(pass_id)
    (root / "postings/unscreened.json").unlink()
    entry = unscreened.client.get(f"/pool/passes/{pass_id}").json()["unscreened"][0]
    assert entry == {"posting_id": "unscreened", "title": "unscreened", "company": "unscreened"}


def test_continue_answer_resumes_the_pass_and_stores_its_scores(unscreened, root):
    pass_id = unscreened.start()
    unscreened.settled(pass_id)
    response = unscreened.client.post(f"/pool/passes/{pass_id}/unscreened",
                                      json={"continue": True})
    assert response.status_code == 202 and response.json() == {"pass_id": pass_id}
    progress = unscreened.settled(pass_id)
    assert progress["status"] == "done" and progress["scored"] == 6
    assert read_score(root, "unscreened").score == 2


def test_abort_answer_ends_the_pass(unscreened):
    pass_id = unscreened.start()
    unscreened.settled(pass_id)
    unscreened.client.post(f"/pool/passes/{pass_id}/unscreened", json={"continue": False})
    assert unscreened.settled(pass_id)["status"] == "aborted"
    assert unscreened.harness.judge.calls == []


def test_answer_without_a_pending_question_is_rejected(api):
    pass_id = api.start()
    api.settled(pass_id)
    response = api.client.post(f"/pool/passes/{pass_id}/unscreened", json={"continue": True})
    assert response.status_code == 409 and set(response.json()) == {"error", "detail"}


def test_malformed_answer_is_rejected_with_error_and_detail(unscreened):
    pass_id = unscreened.start()
    unscreened.settled(pass_id)
    malformed = unscreened.client.post(f"/pool/passes/{pass_id}/unscreened", json={})
    assert malformed.status_code == 422 and set(malformed.json()) == {"error", "detail"}


def test_a_paused_pass_does_not_block_a_new_one(unscreened):
    assert unscreened.settled(unscreened.start())["status"] == "awaiting_answer"
    assert unscreened.client.post("/pool/passes", json={"variant": "unscored"}).status_code == 202


def test_the_built_frontend_is_served_and_the_api_still_responds(tmp_path, root):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>JobAdvAIsor</title>")
    (dist / "assets/app.js").write_text("console.log('app')")
    harness = Harness(tmp_path, root)
    client = TestClient(create_app(Runs(harness.graph, harness.context),
                                   Intake(root, FakeStructuredModel(), harness.guard),
                                   frontend=dist))
    page = client.get("/")
    assert page.status_code == 200 and "<title>JobAdvAIsor</title>" in page.text
    assert client.get("/assets/app.js").text == "console.log('app')"
    assert client.get("/policy-pack/login-wall-hosts").status_code == 200
    assert client.get("/pool/passes/unknown").json()["error"] == "not found"


def test_without_a_build_the_api_runs_alone(tmp_path, root):
    harness = Harness(tmp_path, root)
    client = TestClient(create_app(Runs(harness.graph, harness.context),
                                   Intake(root, FakeStructuredModel(), harness.guard),
                                   frontend=tmp_path / "missing"))
    assert client.get("/").status_code == 404
    assert client.get("/policy-pack/login-wall-hosts").status_code == 200


def test_pool_lists_the_rows_in_rank_order_with_counter_settings_and_next_pass(api, root):
    write_json(root / "labels/p1.json", LABEL)
    before = api.client.get("/pool").json()
    # rated p1 has no score yet; sales is excluded
    assert before["next_pass"] == {"default": "unscored", "unscored": 5, "all": 5}
    assert [row["state"] for row in before["rows"]].count("unscored") == 5
    api.settled(api.start("all"))
    pool = api.client.get("/pool").json()
    ids = [row["posting_id"] for row in pool["rows"]]
    assert ids[0] == "p1" and ids[-1] == "sales" and set(ids) == {"p1", "p2", "p3", "p4", "p5",
                                                                  "sales"}
    assert pool["rows"][0]["label"]["verdict"] == "positive"
    assert pool["rows"][0]["state"] == "scored"
    assert pool["rows"][-1]["state"] == "excluded" and pool["rows"][-1]["rules"] == ["no-sales"]
    assert pool["counter"]["corrections"] == 0 and pool["counter"]["hint"] == "fits"
    assert pool["settings"] == {"correction_threshold": 10, "correction_rate": 0.3}
    assert pool["next_pass"] == {"default": "unscored", "unscored": 0, "all": 5}
    assert pool["reason_chips"] == [{"id": "too-junior", "label": "too junior",
                                     "polarity": None}]


def test_a_corrupt_score_file_shows_on_its_row_and_the_route_still_answers(api, root):
    api.settled(api.start())
    (root / "scores/p3.json").write_text("{")
    response = api.client.get("/pool")
    assert response.status_code == 200
    row = next(row for row in response.json()["rows"] if row["posting_id"] == "p3")
    assert row["score"] is None and "scores/p3.json" in row["score_problem"]


def test_posting_page_carries_text_score_with_reasoning_and_examples(api, root):
    write_json(root / "labels/p1.json", LABEL)
    api.settled(api.start())
    page = api.client.get("/postings/p5").json()
    assert page["row"]["posting_id"] == "p5" and page["row"]["exploration"] is False
    assert page["posting"]["text"] == "We build things." and page["posting"]["status"] == "open"
    assert page["score"]["score"] == 5 and page["score"]["reasoning"]
    assert page["score"]["example_ids"] == ["p1"] and page["score"]["scored_at"]
    assert page["examples"] == [{"posting_id": "p1", "title": "Engineer 1",
                                 "company": "Example Corp"}]
    assert page["reason_chips"][0]["id"] == "too-junior"


def test_posting_page_without_a_score_has_none_and_an_unscored_row(api, root):
    page = api.client.get("/postings/p2").json()
    assert page["score"] is None and page["row"]["state"] == "unscored"


def test_posting_page_says_whether_a_check_can_read_the_posting(api, root):
    """`checkable` follows the check's link rule: a pasted posting (no link) is not checkable."""
    add_posting(root, "linked", "Linked Engineer", source_type="url",
                urls=["https://jobs.example.org/stelle/1"])
    assert api.client.get("/postings/linked").json()["checkable"] is True
    assert api.client.get("/postings/p5").json()["checkable"] is False


def test_pool_and_posting_page_say_whether_screening_is_on(tmp_path, root):
    off = Api(Harness(tmp_path / "off", root))
    assert off.client.get("/pool").json()["screening"] is False
    assert off.client.get("/postings/p1").json()["screening"] is False
    on = Api(Harness(tmp_path / "on", root, StubClassifier()))
    assert on.client.get("/pool").json()["screening"] is True
    assert on.client.get("/postings/p1").json()["screening"] is True


def test_rows_say_which_postings_have_no_guard_result(unscreened):
    rows = unscreened.client.get("/pool").json()["rows"]
    assert {row["posting_id"] for row in rows if row["unscreened"]} == {"unscreened"}
    page = unscreened.client.get("/postings/unscreened").json()
    assert page["row"]["unscreened"] is True


def post_score(api: Api, posting_id: str):
    return api.client.post(f"/postings/{posting_id}/score")


def test_scoring_a_posting_answers_the_page_with_counter_and_next_pass(api, root):
    response = post_score(api, "p2")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["score"]["score"] == 2 and body["score"]["reasoning"]
    assert body["row"]["state"] == "scored" and body["row"]["score"] == 2
    assert body["row"]["exploration"] is False and body["posting"]["title"] == "Engineer 2"
    assert body["screening"] is False and body["reason_chips"][0]["id"] == "too-junior"
    assert body["counter"]["corrections"] == 0
    # p1, p3, p4, p5 have no score; sales is out
    assert body["next_pass"] == {"default": "unscored", "unscored": 4, "all": 5}
    assert read_score(root, "p2").score == 2
    assert read_pool(root).passes == []


def test_a_rated_posting_without_a_score_probes_the_counter(api, root):
    write_json(root / "labels/p1.json", LABEL)  # rated positive; its title scores 1
    body = post_score(api, "p1").json()
    assert body["row"]["label"]["verdict"] == "positive" and body["row"]["score"] == 1
    assert body["counter"]["corrections"] == 1 and body["counter"]["rated"] == 1
    assert body["next_pass"] == {"default": "unscored", "unscored": 4, "all": 5}  # 1 < threshold
    assert api.client.get("/pool").json()["counter"]["corrections"] == 1


def test_a_rating_counts_for_the_probe_only_after_the_last_pass_started(api, root):
    write_json(root / "labels/p1.json", LABEL)  # rated in January, before any pass
    api.settled(api.start("all"))
    add_posting(root, "late", "Engineer 2")
    write_json(root / "labels/late.json", {**LABEL, "rated_at": datetime.now(UTC).isoformat()})
    body = post_score(api, "late").json()
    assert body["row"]["score"] == 2
    assert body["counter"]["rated"] == 1 and body["counter"]["corrections"] == 1  # not p1


def test_scoring_again_replaces_the_score(api, root):
    post_score(api, "p2")
    first = read_score(root, "p2").scored_at
    assert post_score(api, "p2").status_code == 200
    assert read_score(root, "p2").scored_at > first


def test_scoring_an_unknown_posting_is_404(api):
    response = post_score(api, "nope")
    assert response.status_code == 404 and set(response.json()) == {"error", "detail"}
    assert "nope" in response.json()["detail"]


@pytest.mark.parametrize(("posting_id", "error", "detail"), [
    ("sales", "excluded", "no-sales"),
    ("flagged", "held", "injection"),
    ("unscreened", "unscreened", "screening is off"),
])
def test_scoring_a_posting_no_pass_would_score_is_409_with_its_reason(
        tmp_path, root, posting_id, error, detail):
    add_posting(root, "flagged", "Flagged Engineer", guard=FLAGGED)
    add_posting(root, "unscreened", "Unscreened Engineer 2", guard=None)
    api = Api(Harness(tmp_path, root))
    response = post_score(api, posting_id)
    assert response.status_code == 409
    assert response.json()["error"] == error and detail in response.json()["detail"]
    assert read_score(root, posting_id) is None


def test_a_held_posting_without_categories_is_409_held_not_the_unscreened_text(tmp_path, root):
    add_posting(root, "flagged", "Flagged Engineer", guard={**FLAGGED, "categories": []})
    response = post_score(Api(Harness(tmp_path, root)), "flagged")
    assert response.status_code == 409 and response.json()["error"] == "held"
    assert "screening is off" not in response.json()["detail"]


def test_a_posting_the_check_on_the_click_flags_is_409_held_and_its_row_says_so(tmp_path, root):
    add_posting(root, "injected", "Engineer 3", guard=None, text="INJECT")
    api = Api(Harness(tmp_path, root, StubClassifier()))
    response = post_score(api, "injected")
    assert response.status_code == 409 and response.json()["error"] == "held"
    page = api.client.get("/postings/injected").json()
    assert page["row"]["state"] == "held" and page["row"]["unscreened"] is False
    assert page["score"] is None


def test_a_failing_classifier_on_the_click_is_502_scoring_failed(tmp_path, root):
    add_posting(root, "unchecked", "Engineer 3", guard=None)
    classifier = StubClassifier()
    classifier.classify = lambda text: (_ for _ in ()).throw(ConnectionError("classifier down"))
    response = post_score(Api(Harness(tmp_path, root, classifier)), "unchecked")
    assert response.status_code == 502 and response.json()["error"] == "scoring failed"
    assert "classifier down" in response.json()["detail"]


def test_a_failing_write_after_the_judge_is_500_not_a_retryable_502(api, root, monkeypatch):
    def refuse(*args):
        raise PermissionError("scores/ is read-only")

    monkeypatch.setattr("jobadvaisor.triage.graph.write_score", refuse)
    response = post_score(api, "p2")
    assert response.status_code == 500 and response.json()["error"] == "internal error"


def test_a_failing_guard_write_on_the_click_is_500_not_a_retryable_502(tmp_path, root, monkeypatch):
    add_posting(root, "unchecked", "Engineer 3", guard=None)

    def refuse(*args):
        raise PermissionError("guard/ is read-only")

    monkeypatch.setattr("jobadvaisor.tools.guard.write_guard", refuse)
    response = post_score(Api(Harness(tmp_path, root, StubClassifier())), "unchecked")
    assert response.status_code == 500 and response.json()["error"] == "internal error"


def test_a_posting_deleted_during_the_request_is_404(api, monkeypatch):
    def gone(posting_id):
        raise KeyError(posting_id)

    monkeypatch.setattr(api.runs, "score", gone)
    assert post_score(api, "p2").status_code == 404


def start_delete(api: Api, posting_id: str) -> tuple[threading.Thread, list]:
    """Delete `posting_id` in a thread; the list gets its answer's status code."""
    answers: list = []
    thread = threading.Thread(
        target=lambda: answers.append(api.client.delete(f"/postings/{posting_id}").status_code))
    thread.start()
    return thread, answers


REQUESTS = {
    "page": ("rank", lambda api: api.client.get("/postings/p2")),
    "rating": ("rank", lambda api: api.client.put("/postings/p2/rating",
                                                   json={"verdict": "positive"})),
    "patch": ("amend_posting", lambda api: api.client.patch("/postings/p2",
                                                            json={"title": "Renamed"})),
    "score": ("rank", lambda api: post_score(api, "p2")),
}


@pytest.mark.parametrize("name", REQUESTS)
def test_a_delete_waits_until_a_request_on_the_posting_has_answered(api, root, monkeypatch, name):
    """The request holds the write gate from its 404 check to its answer, so the delete that
    arrives in between neither breaks it (a 500) nor changes what it answers."""
    target, request = REQUESTS[name]
    entered, release = threading.Event(), threading.Event()
    real = getattr(app_module, target)

    def hold_once(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            assert release.wait(10), "the request was never released"
        return real(*args, **kwargs)

    monkeypatch.setattr(app_module, target, hold_once)
    answers: list = []
    running = threading.Thread(target=lambda: answers.append(request(api)))
    running.start()
    assert entered.wait(10), "the request never reached its answer"
    deleting, deleted = start_delete(api, "p2")
    deleting.join(0.3)
    assert deleting.is_alive() and (root / "postings/p2.json").exists()  # the delete waits
    release.set()
    running.join(10)
    deleting.join(10)
    assert answers[0].status_code == 200, answers[0].text
    assert deleted == [204] and not (root / "postings/p2.json").exists()


def test_every_request_on_a_deleted_posting_is_404_and_writes_no_file(api, root):
    assert api.client.delete("/postings/p2").status_code == 204
    for answer in (api.client.get("/postings/p2"),
                   api.client.put("/postings/p2/rating", json={"verdict": "positive"}),
                   api.client.patch("/postings/p2", json={"availability": "closed"}),
                   api.client.patch("/postings/p2", json={"title": "Renamed"}),
                   post_score(api, "p2")):
        assert answer.status_code == 404 and answer.json()["error"] == "not found"
    assert not any((root / name / "p2.json").exists() for name in ("postings", "labels", "scores"))
    assert [path.name for path in (root / "postings").glob(".*")] == []  # no temporary file


def test_a_posting_deleted_between_the_judge_and_the_answer_is_404(api, root, monkeypatch):
    score = api.runs.score

    def score_then_delete(posting_id):
        stored = score(posting_id)  # the slot is released here, the answer is still to come
        delete_posting(root, posting_id)
        return stored

    monkeypatch.setattr(api.runs, "score", score_then_delete)
    response = post_score(api, "p2")
    assert response.status_code == 404 and response.json()["error"] == "not found"
    assert not (root / "scores/p2.json").exists()


def test_a_delete_answers_204_and_the_posting_is_gone_from_page_pool_and_counter(api, root):
    write_json(root / "labels/p1.json", LABEL)
    write_json(root / "labels/p2.json", LABEL)
    api.settled(api.start())
    before = api.client.get("/pool").json()
    assert before["counter"]["rated"] == 2 and read_score(root, "p1") is not None
    deleted = api.client.delete("/postings/p1")
    assert deleted.status_code == 204 and deleted.content == b""
    assert api.client.get("/postings/p1").status_code == 404
    pool = api.client.get("/pool").json()
    assert "p1" not in [row["posting_id"] for row in pool["rows"]]
    assert pool["counter"]["rated"] == 1
    assert pool["next_pass"]["all"] == before["next_pass"]["all"] - 1
    assert not any((root / name / "p1.json").exists() for name in ("postings", "labels", "scores"))
    assert set(load_repository(root).postings) == {"p2", "p3", "p4", "p5", "sales"}


def test_a_score_keeps_naming_a_deleted_example_and_the_page_leaves_it_out(api, root):
    write_json(root / "labels/p1.json", LABEL)
    api.settled(api.start())
    stored = read_score(root, "p5")
    assert stored.example_ids == ["p1"]
    assert api.client.delete("/postings/p1").status_code == 204
    assert read_score(root, "p5") == stored  # the record of the past score is untouched
    page = api.client.get("/postings/p5").json()
    assert page["score"]["example_ids"] == ["p1"] and page["examples"] == []


def test_a_pass_after_a_delete_shows_the_judge_no_deleted_example(api, root):
    write_json(root / "labels/p1.json", LABEL)
    assert api.client.delete("/postings/p1").status_code == 204
    api.settled(api.start())
    assert read_score(root, "p5").example_ids == []
    assert "Engineer 1" not in "\n".join(api.harness.judge.calls)


def test_a_second_delete_and_an_unknown_or_unsafe_id_answer_404(api):
    assert api.client.delete("/postings/p1").status_code == 204
    for posting_id in ("p1", "nope", "Bad_ID", "..%2Fx"):
        response = api.client.delete(f"/postings/{posting_id}")
        assert response.status_code == 404, posting_id
        assert response.json()["error"] == "not found" and set(response.json()) == {
            "error", "detail"}


def test_a_delete_during_a_single_score_is_409_scoring_in_progress_and_changes_nothing(api, root):
    api.gate.clear()
    answers = []
    single = threading.Thread(target=lambda: answers.append(post_score(api, "p2").status_code))
    single.start()
    assert api.entered.wait(10)
    refused = api.client.delete("/postings/p3")
    assert refused.status_code == 409 and refused.json()["error"] == "scoring in progress"
    assert refused.json()["detail"] == "score:p2"
    assert (root / "postings/p3.json").exists()
    assert api.client.get("/postings/p3").json()["delete_blocked"] == "scoring"
    api.gate.set()
    single.join(10)
    assert answers == [200]
    assert api.client.get("/postings/p3").json()["delete_blocked"] is None
    assert api.client.delete("/postings/p3").status_code == 204


def test_a_delete_during_a_pass_is_409_naming_the_pass(api, root):
    api.gate.clear()
    pass_id = api.start()
    assert api.entered.wait(10)
    refused = api.client.delete("/postings/p3")
    assert refused.status_code == 409 and refused.json()["error"] == "scoring in progress"
    assert refused.json()["detail"] == pass_id and (root / "postings/p3.json").exists()
    api.gate.set()
    api.settled(pass_id)


def test_a_delete_during_a_check_is_409_check_in_progress_and_changes_nothing(tmp_path, root):
    add_posting(root, "linked", "Engineer 9", urls=["https://a.example.org/1"])
    release, entered = threading.Event(), threading.Event()
    site = Site()
    site.on_request = lambda url: (entered.set(), release.wait(30))
    api = checked_api(tmp_path, root, site)
    check_id = api.client.post("/availability/checks").json()["check_id"]
    assert entered.wait(10)
    refused = api.client.delete("/postings/p3")
    assert refused.status_code == 409 and refused.json()["error"] == "check in progress"
    assert refused.json()["detail"] == check_id and (root / "postings/p3.json").exists()
    assert api.client.get("/postings/p3").json()["delete_blocked"] == "check"
    release.set()
    assert settled_check(api, check_id)["status"] == "done"
    assert api.client.get("/postings/p3").json()["delete_blocked"] is None
    assert api.client.delete("/postings/p3").status_code == 204


def test_a_delete_refused_for_a_check_leaves_the_run_slot_free(tmp_path, root):
    add_posting(root, "linked", "Engineer 9", urls=["https://a.example.org/1"])
    release, entered = threading.Event(), threading.Event()
    site = Site()
    site.on_request = lambda url: (entered.set(), release.wait(30))
    api = checked_api(tmp_path, root, site)
    api.client.post("/availability/checks")
    assert entered.wait(10)
    assert api.client.delete("/postings/p3").status_code == 409
    assert post_score(api, "p2").status_code == 200  # the slot was not left claimed
    release.set()


def test_delete_blocked_is_null_on_the_posting_page_of_an_idle_app(api):
    assert api.client.get("/postings/p1").json()["delete_blocked"] is None
    assert post_score(api, "p2").json()["delete_blocked"] is None


def test_a_check_and_a_delete_started_together_never_deadlock_with_a_reading_request(
        tmp_path, root):
    """Page reads, a check start and deletes race; none may wait for another forever."""
    add_posting(root, "linked", "Engineer 9", urls=["https://a.example.org/1"])
    api = checked_api(tmp_path, root, Site())
    errors: list = []

    def hammer(call):
        try:
            for _ in range(15):
                call()
        except Exception as error:  # noqa: BLE001 - reported below
            errors.append(error)

    threads = [threading.Thread(target=hammer, args=(call,)) for call in (
        lambda: api.client.get("/postings/p1"),
        lambda: api.client.post("/availability/checks"),
        lambda: api.client.put("/postings/p1/rating", json={"verdict": "positive"}),
        lambda: api.client.delete("/postings/nope"),
        lambda: api.client.get("/pool"))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert not any(thread.is_alive() for thread in threads), "a request never answered"
    assert not errors


def test_scoring_during_a_pass_is_409_scoring_in_progress_and_a_pass_during_scoring_too(api):
    api.gate.clear()
    pass_id = api.start()
    busy = post_score(api, "p2")
    assert busy.status_code == 409 and busy.json()["error"] == "scoring in progress"
    assert pass_id in busy.json()["detail"]
    api.gate.set()
    api.settled(pass_id)

    api.gate.clear()
    calls = len(api.harness.judge.calls)
    answers = []
    single = threading.Thread(target=lambda: answers.append(post_score(api, "p2").status_code))
    single.start()
    deadline = time.monotonic() + 10
    while len(api.harness.judge.calls) == calls:  # until the single score reaches the judge
        assert time.monotonic() < deadline, "single score never reached the judge"
        time.sleep(0.02)
    response = api.client.post("/pool/passes", json={"variant": "unscored"})
    assert response.status_code == 409 and response.json()["error"] == "pass in progress"
    assert "score:p2" in response.json()["detail"]
    api.gate.set()
    single.join(10)
    assert answers == [200]


def test_a_failing_judge_is_502_scoring_failed_and_frees_the_slot(api, root):
    def broken(schema, prompt):
        raise RuntimeError("model down")

    api.harness.judge = ScriptedModel(broken)
    response = post_score(api, "p2")
    assert response.status_code == 502 and response.json()["error"] == "scoring failed"
    assert "model down" in response.json()["detail"]
    assert read_score(root, "p2") is None
    api.harness.judge = ScriptedModel(judge_by_title)
    assert post_score(api, "p2").status_code == 200


@pytest.mark.parametrize("posting_id", ["nope", "Bad_ID", "..%2Fx"])
def test_posting_page_for_an_unknown_or_unsafe_id_is_404(api, posting_id):
    response = api.client.get(f"/postings/{posting_id}")
    assert response.status_code == 404 and set(response.json()) == {"error", "detail"}


def test_settings_are_stored_and_the_passes_are_kept(api, root):
    api.settled(api.start())
    response = api.client.put("/pool/settings",
                              json={"correction_threshold": 3, "correction_rate": 0.5})
    assert response.status_code == 200
    assert response.json() == {"settings": {"correction_threshold": 3, "correction_rate": 0.5}}
    pool = read_pool(root)
    assert pool.settings.correction_threshold == 3 and len(pool.passes) == 1
    assert api.client.get("/pool").json()["settings"]["correction_rate"] == 0.5


@pytest.mark.parametrize("body", [
    {"correction_threshold": 0, "correction_rate": 0.3},
    {"correction_threshold": 5, "correction_rate": 1.5},
    {"correction_threshold": 5},
    {"correction_rate": 0.3},
    {"correction_threshold": 5, "correction_rate": 0.3, "other": 1},
])
def test_invalid_settings_are_rejected_and_nothing_is_written(api, root, body):
    response = api.client.put("/pool/settings", json=body)
    assert response.status_code == 422 and set(response.json()) == {"error", "detail"}
    assert not (root / "pool.json").exists()


def test_patch_status_is_stored_and_lifts_a_version_1_posting_to_2(api, root):
    assert read_posting(root, "p1").schema_version == "1"
    response = api.client.patch("/postings/p1", json={"status": "applied"})
    assert response.status_code == 200 and response.json()["posting"]["status"] == "applied"
    stored = read_posting(root, "p1")
    assert stored.status == "applied" and stored.schema_version == "2"
    rows = {row["posting_id"]: row for row in api.client.get("/pool").json()["rows"]}
    assert rows["p1"]["status"] == "applied"


def test_patch_without_status_keeps_the_version_and_still_corrects(api, root):
    response = api.client.patch("/postings/p1", json={"title": "Renamed"})
    assert response.status_code == 200
    stored = read_posting(root, "p1")
    assert stored.title == "Renamed" and stored.schema_version == "1"


def test_patch_rejects_an_invalid_status_an_empty_body_and_an_unknown_posting(api):
    assert api.client.patch("/postings/p1", json={"status": "maybe"}).status_code == 422
    empty = api.client.patch("/postings/p1", json={})
    assert empty.status_code == 422 and "name a field" in empty.json()["detail"]
    assert api.client.patch("/postings/nope", json={"status": "done"}).status_code == 404


def test_patch_rejects_explicit_nulls_with_a_problem_body(api):
    for field in ("status", "title", "company", "location_raw"):
        response = api.client.patch("/postings/p1", json={field: None})
        assert response.status_code == 422, field
        assert {"error", "detail"} <= response.json().keys()


def patch_availability(api: Api, value: str, posting_id: str = "p1"):
    return api.client.patch(f"/postings/{posting_id}", json={"availability": value})


def pool_row(api: Api, posting_id: str) -> dict:
    rows = api.client.get("/pool").json()["rows"]
    return next(row for row in rows if row["posting_id"] == posting_id)


def test_a_posting_is_closed_by_hand_and_reopened_by_hand(api, root):
    closed = patch_availability(api, "closed")
    assert closed.status_code == 200, closed.text
    stored = read_posting(root, "p1")
    assert (stored.availability.state, stored.availability.set_by) == ("closed", "user")
    assert closed.json()["posting"]["availability"]["state"] == "closed"
    assert (stored.status, stored.schema_version) == ("open", "1")  # status apart, no new version
    assert pool_row(api, "p1")["availability"]["state"] == "closed"
    reopened = patch_availability(api, "available")
    assert reopened.status_code == 200
    stored = read_posting(root, "p1")
    assert (stored.availability.state, stored.availability.set_by) == ("available", "user")
    assert pool_row(api, "p1")["availability"]["set_by"] == "user"


def test_a_hand_setting_leaves_the_application_status_alone(api, root):
    api.client.patch("/postings/p1", json={"status": "applied"})
    patch_availability(api, "closed")
    stored = read_posting(root, "p1")
    assert (stored.status, stored.availability.state) == ("applied", "closed")


def test_a_hand_setting_of_unknown_or_anything_else_is_a_422(api, root):
    for value in ("unknown", "open", "", "check"):  # "check" no longer removes a setting
        response = patch_availability(api, value)
        assert response.status_code == 422, value
    assert api.client.patch("/postings/p1", json={"availability": None}).status_code == 422
    assert read_posting(root, "p1").availability is None


def test_a_hand_setting_of_an_unknown_posting_is_a_404(api):
    assert patch_availability(api, "closed", "nope").status_code == 404


def test_a_closed_posting_is_scored_on_request_and_stays_closed(api, root):
    patch_availability(api, "closed", "p2")
    response = post_score(api, "p2")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["score"]["score"] == 2 and read_score(root, "p2").score == 2
    assert body["row"]["availability"]["state"] == "closed"
    assert read_posting(root, "p2").availability.state == "closed"


def checked_api(tmp_path, root, site: Site) -> Api:
    """An `Api` whose availability checks fetch through `site`, with no spacing."""
    checks = AvailabilityChecks(root, http=site.client, throttle=Clock().throttle())
    return Api(Harness(tmp_path, root), checks)


def settled_check(api: Api, check_id: str) -> dict:
    deadline = time.monotonic() + 10
    while (state := api.client.get(f"/availability/checks/{check_id}").json())[
            "status"] == "running":
        assert time.monotonic() < deadline, "check never settled"
        time.sleep(0.02)
    return state


def test_the_pool_announces_what_a_check_would_cover(api, root):
    assert api.client.get("/pool").json()["next_check"] == {"total": 0}  # no posting has a link
    add_posting(root, "linked", "Engineer 9", urls=["https://jobs.example.org/9"])
    assert api.client.get("/pool").json()["next_check"] == {"total": 1}


def test_a_check_started_through_the_api_reports_and_stores_its_findings(tmp_path, root):
    add_posting(root, "open", "Engineer 8", urls=["https://a.example.org/1"])
    add_posting(root, "gone", "Engineer 9", urls=["https://b.example.org/2"])
    api = checked_api(tmp_path, root, Site({"https://b.example.org/2": reply(404)}))
    started = api.client.post("/availability/checks")
    assert started.status_code == 202, started.text
    assert set(started.json()) == {"check_id", "total"} and started.json()["total"] == 2
    state = settled_check(api, started.json()["check_id"])
    assert state["status"] == "done" and (state["total"], state["done"]) == (2, 2)
    assert state["counts"] == {"available": 1, "closed": 1, "unknown": 0}
    assert [c["posting_id"] for c in state["closed"]] == ["gone"]
    assert pool_row(api, "gone")["availability"]["state"] == "closed"
    assert pool_row(api, "open")["availability"]["set_by"] == "check"
    assert api.client.get("/pool").json()["next_check"] == {"total": 2}  # closed: again


def test_a_second_check_is_refused_naming_the_running_one(tmp_path, root):
    add_posting(root, "linked", "Engineer 9", urls=["https://a.example.org/1"])
    release, entered = threading.Event(), threading.Event()
    site = Site()
    site.on_request = lambda url: (entered.set(), release.wait(30))
    api = checked_api(tmp_path, root, site)
    first = api.client.post("/availability/checks").json()["check_id"]
    assert entered.wait(10)
    refused = api.client.post("/availability/checks")
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"] == "check in progress" and refused.json()["check_id"] == first
    assert api.client.get(f"/availability/checks/{first}").json()["status"] == "running"
    release.set()
    assert settled_check(api, first)["status"] == "done"


def test_a_check_is_cancelled_through_the_api_and_an_ended_or_unknown_one_is_refused(tmp_path,
                                                                                      root):
    add_posting(root, "a", "Engineer 8", urls=["https://a.example.org/1"])
    add_posting(root, "b", "Engineer 9", urls=["https://b.example.org/2"])
    release, entered = threading.Event(), threading.Event()
    site = Site()
    site.on_request = lambda url: (entered.set(), release.wait(30))
    api = checked_api(tmp_path, root, site)
    check_id = api.client.post("/availability/checks").json()["check_id"]
    assert entered.wait(10)
    cancelled = api.client.post(f"/availability/checks/{check_id}/cancel")
    assert cancelled.status_code == 202 and cancelled.json() == {"check_id": check_id}
    assert api.client.get(f"/availability/checks/{check_id}").json()["cancel_requested"] is True
    release.set()
    state = settled_check(api, check_id)
    assert (state["status"], state["done"], state["total"]) == ("cancelled", 1, 2)
    ended = api.client.post(f"/availability/checks/{check_id}/cancel")
    assert ended.status_code == 409 and ended.json()["error"] == "check not running"
    unknown = api.client.post("/availability/checks/nope/cancel")
    assert unknown.status_code == 404
    assert unknown.json() == {"error": "not found", "detail": "no availability check nope"}


def test_an_unknown_check_is_not_found(api):
    response = api.client.get("/availability/checks/nope")
    assert response.status_code == 404
    assert response.json() == {"error": "not found", "detail": "no availability check nope"}


def test_a_hand_setting_does_not_take_a_posting_out_of_the_next_check(api, root):
    add_posting(root, "linked", "Engineer 9", urls=["https://a.example.org/1"])
    patch_availability(api, "closed", "linked")
    assert "linked" in check_batch(load_repository(root))
    patch_availability(api, "available", "linked")
    assert "linked" in check_batch(load_repository(root))
    assert api.client.get("/pool").json()["next_check"] == {"total": 1}


def test_a_closed_link_is_closed_in_both_intake_answers(api, root, closed_site, monkeypatch):
    write_json(root / "policy-pack.json", POLICY_PACK | {"closed_rules": closed_site.rules})
    monkeypatch.setattr("jobadvaisor.intake.postings.run_intake_loop",
                        lambda url, attempts, *args, **kwargs: LadderResult(None, attempts))
    link = f"{closed_site.url}/expired/1"
    single = api.client.post("/postings", data={"url": link})
    assert single.status_code == 422 and single.json()["closed"] is True
    batch = api.client.post("/postings/batch", json={"urls": [link]}).json()["results"][0]
    assert batch["outcome"] == "closed" and batch["attempts"] == single.json()["attempts"]
    assert closed_site.hits == ["/expired/1", "/expired/1"]


@pytest.fixture
def polar(root):
    """The policy pack with a positive, a negative and a polarity-less chip."""
    write_json(root / "policy-pack.json", POLICY_PACK | {"reason_chips": [
        {"id": "remote", "label": "remote", "polarity": "positive"},
        {"id": "onsite", "label": "onsite only", "polarity": "negative"},
        {"id": "other", "label": "other"}]})


def test_a_rating_with_a_chip_is_stored_and_answered_with_row_counter_and_next_pass(api, root,
                                                                                      polar):
    api.settled(api.start())
    response = api.client.put("/postings/p5/rating",
                              json={"verdict": "positive", "chips": ["remote"], "note": "nice"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"row", "counter", "next_pass"}
    assert body["row"]["posting_id"] == "p5"
    assert body["row"]["label"]["verdict"] == "positive"
    assert body["row"]["label"]["chips"] == ["remote"] and body["row"]["label"]["note"] == "nice"
    stored = json.loads((root / "labels/p5.json").read_text())
    assert stored["kind"] == "rating" and stored["note"] == "nice" and stored["rated_at"]
    assert body["counter"]["rated"] == 1 and body["counter"]["corrections"] == 1  # p5 scored 5
    assert body["next_pass"] == {"default": "unscored", "unscored": 0, "all": 5}
    assert body["counter"] == api.client.get("/pool").json()["counter"]


def test_the_counter_in_the_answer_counts_the_new_rating(api):
    api.settled(api.start())
    body = api.client.put("/postings/p5/rating", json={"verdict": "negative"}).json()
    assert body["counter"]["corrections"] == 0 and body["counter"]["rated"] == 1
    body = api.client.put("/postings/p5/rating", json={"verdict": "positive"}).json()
    assert body["counter"]["rated"] == 1 and body["counter"]["corrections"] == 1
    assert api.client.put("/postings/p4/rating", json={"verdict": "negative"}).json()[
        "counter"]["rated"] == 2


def test_mixed_chips_keep_the_explicit_verdict(api, polar):
    body = api.client.put("/postings/p1/rating", json={"verdict": "negative",
                                                       "chips": ["remote", "onsite"]}).json()
    assert body["row"]["label"]["verdict"] == "negative"
    assert body["row"]["label"]["chips"] == ["remote", "onsite"]


def test_the_verdict_comes_from_the_first_chip_with_a_polarity(api, polar):
    body = api.client.put("/postings/p1/rating",
                          json={"chips": ["other", "onsite", "remote"]}).json()
    assert body["row"]["label"]["verdict"] == "negative"


def test_no_verdict_to_derive_is_422(api, polar):
    for body in ({}, {"chips": ["other"]}):
        response = api.client.put("/postings/p1/rating", json=body)
        assert response.status_code == 422 and "verdict is missing" in response.json()["detail"]
    assert not (api.harness.root / "labels/p1.json").exists()


def test_an_unknown_chip_is_422_naming_it_and_nothing_is_written(api, root, polar):
    response = api.client.put("/postings/p1/rating",
                              json={"verdict": "positive", "chips": ["nope"]})
    assert response.status_code == 422 and "nope" in response.json()["detail"]
    assert not (root / "labels/p1.json").exists()


def test_rating_an_unknown_posting_is_404(api):
    response = api.client.put("/postings/nope/rating", json={"verdict": "positive"})
    assert response.status_code == 404 and response.json()["detail"] == "no posting nope"


def test_rating_rejects_an_unknown_field_and_re_rating_replaces_the_label(api, root, polar):
    assert api.client.put("/postings/p1/rating",
                          json={"verdict": "positive", "x": 1}).status_code == 422
    api.client.put("/postings/p1/rating", json={"verdict": "positive", "chips": ["remote"],
                                                "note": "first"})
    api.client.put("/postings/p1/rating", json={"verdict": "negative"})
    stored = json.loads((root / "labels/p1.json").read_text())
    assert stored["verdict"] == "negative" and "chips" in stored and stored["chips"] == []
    assert "note" not in stored


@pytest.mark.parametrize(("verdict", "strength"), [
    ("positive", "strong"), ("positive", "weak"), ("negative", "weak"), ("negative", "strong")])
def test_each_of_the_four_levels_round_trips_through_put_pool_and_the_posting_page(
        api, root, verdict, strength):
    answer = api.client.put("/postings/p1/rating",
                            json={"verdict": verdict, "strength": strength}).json()
    assert answer["row"]["label"]["strength"] == strength
    assert json.loads((root / "labels/p1.json").read_text())["strength"] == strength
    rows = {row["posting_id"]: row for row in api.client.get("/pool").json()["rows"]}
    assert (rows["p1"]["label"]["verdict"], rows["p1"]["label"]["strength"]) == (verdict, strength)
    page = api.client.get("/postings/p1").json()
    assert page["row"]["label"]["strength"] == strength


def test_a_rating_without_strength_stores_none_and_re_rating_without_it_clears_it(api, root):
    body = api.client.put("/postings/p1/rating", json={"verdict": "negative"}).json()
    assert body["row"]["label"]["strength"] is None
    assert "strength" not in json.loads((root / "labels/p1.json").read_text())
    api.client.put("/postings/p1/rating", json={"verdict": "negative", "strength": "weak"})
    body = api.client.put("/postings/p1/rating", json={"verdict": "negative"}).json()
    assert body["row"]["label"]["strength"] is None
    assert "strength" not in json.loads((root / "labels/p1.json").read_text())


def test_a_strength_without_a_verdict_is_422_even_when_a_chip_would_derive_one(api, root, polar):
    for body in ({"strength": "weak"}, {"strength": "strong", "chips": ["remote"]}):
        response = api.client.put("/postings/p1/rating", json=body)
        assert response.status_code == 422 and "strength needs a verdict" in response.json()[
            "detail"]
    assert not (root / "labels/p1.json").exists()


def test_an_unknown_strength_is_422(api):
    response = api.client.put("/postings/p1/rating",
                              json={"verdict": "positive", "strength": "medium"})
    assert response.status_code == 422


@pytest.mark.parametrize("corrected", [False, True])
def test_the_variant_alone_decides_whether_a_pass_rescores(api, root, corrected):
    api.settled(api.start("unscored"))
    if corrected:  # p5 scored 5, rated positive: a counted correction
        write_json(root / "labels/p5.json", LABEL | {"rated_at": "2099-01-01T00:00:00+00:00"})
    assert api.client.get("/pool").json()["counter"]["corrections"] == corrected
    api.settled(api.start("unscored"))
    api.settled(api.start("all"))
    assert api.started == [False, False, True]


@pytest.mark.parametrize("body", [{}, {"variant": "both"}, {"variant": None}, {"variant": "all",
                                                                              "x": 1}])
def test_a_missing_unknown_or_extra_variant_is_422_and_starts_nothing(api, body):
    response = api.client.post("/pool/passes", json=body)
    assert response.status_code == 422 and set(response.json()) == {"error", "detail"}
    assert api.started == []


def test_a_pass_without_a_body_is_422_and_starts_nothing(api):
    assert api.client.post("/pool/passes").status_code == 422
    assert api.started == []


def test_a_pass_starts_even_when_the_repository_does_not_load(api, root):
    (root / "pool.json").write_text("{not json")
    assert api.settled(api.start("all"))["status"] == "failed"
    assert api.started == [True]


def test_health_is_ok_for_a_loading_repository(api, monkeypatch, tmp_path):
    monkeypatch.setattr("jobadvaisor.api.app.VERSION_FILE", tmp_path / "VERSION")
    response = api.client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"data_repo": "ok"}, "version": "dev"}


def test_health_fails_with_the_load_error_and_still_reports_the_version(
        api, root, monkeypatch, tmp_path):
    (tmp_path / "VERSION").write_text("v0.1.0\n")
    monkeypatch.setattr("jobadvaisor.api.app.VERSION_FILE", tmp_path / "VERSION")
    (root / "pool.json").write_text("{not json")
    response = api.client.get("/health")
    body = response.json()
    assert response.status_code == 503
    assert body["status"] == "fail" and body["version"] == "v0.1.0"
    assert body["checks"]["data_repo"] != "ok" and "pool.json" in body["checks"]["data_repo"]


def test_health_version_is_the_trimmed_content_of_the_version_file(api, monkeypatch, tmp_path):
    (tmp_path / "VERSION").write_text("v0.1.0\n")
    monkeypatch.setattr("jobadvaisor.api.app.VERSION_FILE", tmp_path / "VERSION")
    assert api.client.get("/health").json()["version"] == "v0.1.0"


def test_health_version_ignores_environment_variables(api, monkeypatch, tmp_path):
    (tmp_path / "VERSION").write_text("v0.1.0\n")
    monkeypatch.setattr("jobadvaisor.api.app.VERSION_FILE", tmp_path / "VERSION")
    for name in ("APP_VERSION", "VERSION", "JOBADVAISOR_TAG"):
        monkeypatch.setenv(name, "other")
    assert api.client.get("/health").json()["version"] == "v0.1.0"


def test_there_is_no_version_route(api):
    assert api.client.get("/version").status_code == 404
