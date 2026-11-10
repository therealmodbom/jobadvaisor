import json
import threading
import time

import pytest
from conftest import LABEL, FakeStructuredModel, ScriptedModel, write_json
from fastapi.testclient import TestClient
from test_triage_graph import POLICY_PACK, Harness, add_posting, judge_by_title

from jobadvaisor.api.app import configured_intake, configured_runs, create_app
from jobadvaisor.data.loader import DataRepositoryError
from jobadvaisor.data.writer import read_pool, read_posting, read_score
from jobadvaisor.intake.postings import Intake
from jobadvaisor.settings import Settings
from jobadvaisor.triage.graph import checkpoint_path
from jobadvaisor.triage.runs import Runs


class Api:
    """A test client over a triage graph with fake models; the judge waits for `gate`."""

    def __init__(self, harness: Harness):
        self.harness, self.gate = harness, threading.Event()
        self.gate.set()
        harness.judge = ScriptedModel(self._judge)
        self.runs = Runs(harness.graph, harness.context)
        self.started: list[bool] = []  # the `rescore_unrated` of every pass started
        start = self.runs.start
        self.runs.start = lambda rescore_unrated=False: (
            self.started.append(rescore_unrated), start(rescore_unrated))[1]
        self.client = TestClient(create_app(self.runs,
                                            Intake(harness.root, FakeStructuredModel(),
                                                   harness.guard),
                                            frontend=harness.root / "no-frontend-build"),
                                 raise_server_exceptions=False)

    def _judge(self, schema, prompt):
        assert self.gate.wait(10), "gate never opened"
        return judge_by_title(schema, prompt)

    def start(self) -> str:
        response = self.client.post("/pool/passes")
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
    busy = api.client.post("/pool/passes")
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


def test_progress_counts_the_finished_postings_and_the_pass_stores_them(api, root):
    progress = api.settled(api.start())
    assert progress["total"] == 6 and progress["done"] == 6 and progress["unscreened"] == []
    assert progress["error"] is None and progress["started_at"]
    assert set(progress) == {"pass_id", "status", "started_at", "error", "total", "done",
                             "unscreened"}
    assert read_score(root, "p5").score == 5
    assert read_pool(root).passes[0].scored == 5


def test_progress_while_the_pass_computes_has_a_total_or_none_yet(api):
    api.gate.clear()
    progress = api.client.get(f"/pool/passes/{api.start()}").json()
    assert progress["status"] == "running" and progress["done"] <= progress["total"]
    api.gate.set()


def test_a_pass_that_fails_before_its_first_step_reports_failed(api, root):
    write_json(root / "postings/broken.json", {"schema_version": "1"})
    progress = api.settled(api.start())
    assert progress["status"] == "failed" and "postings/broken.json" in progress["error"]
    assert progress["total"] == 0 and progress["unscreened"] == []


def test_unknown_pass_answers_with_error_and_detail(api):
    unknown = api.client.get("/pool/passes/nope")
    assert unknown.status_code == 404 and set(unknown.json()) == {"error", "detail"}
    answer = api.client.post("/pool/passes/nope/unscreened", json={"continue": True})
    assert answer.status_code == 404 and set(answer.json()) == {"error", "detail"}


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
    api.settled(api.start())
    write_json(root / "labels/p5.json", LABEL)
    add_posting(root, "similar", "Engineer 8")
    progress = api.settled(api.start())
    assert progress["total"] == 2 and progress["done"] == 2
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
    assert progress["done"] < progress["total"]
    assert unscreened.harness.extractor.calls == []


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
    assert progress["status"] == "done" and progress["done"] == progress["total"] == 7
    assert read_score(root, "unscreened").score == 2


def test_abort_answer_ends_the_pass(unscreened):
    pass_id = unscreened.start()
    unscreened.settled(pass_id)
    unscreened.client.post(f"/pool/passes/{pass_id}/unscreened", json={"continue": False})
    assert unscreened.settled(pass_id)["status"] == "aborted"
    assert unscreened.harness.extractor.calls == []


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
    assert unscreened.client.post("/pool/passes").status_code == 202


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
    assert before["next_pass"] == {"count": 4, "rescore_unrated": False}
    assert [row["state"] for row in before["rows"]].count("unscored") == 5
    api.settled(api.start())
    pool = api.client.get("/pool").json()
    ids = [row["posting_id"] for row in pool["rows"]]
    assert ids[0] == "p1" and ids[-1] == "sales" and set(ids) == {"p1", "p2", "p3", "p4", "p5",
                                                                  "sales"}
    assert pool["rows"][0]["label"]["verdict"] == "positive"
    assert pool["rows"][-1]["state"] == "excluded" and pool["rows"][-1]["rules"] == ["no-sales"]
    assert pool["counter"]["corrections"] == 0 and pool["counter"]["hint"] == "fits"
    assert pool["settings"] == {"correction_threshold": 10, "correction_rate": 0.3}
    assert pool["next_pass"] == {"count": 0, "rescore_unrated": False}
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


def test_a_pass_rescores_unrated_postings_after_a_correction_was_counted(api, root):
    api.settled(api.start())
    assert api.started == [False]
    write_json(root / "labels/p5.json", LABEL | {"rated_at": "2099-01-01T00:00:00+00:00"})
    assert api.client.get("/pool").json()["counter"]["corrections"] == 1
    api.settled(api.start())
    assert api.started == [False, True]


def test_a_pass_without_a_counted_correction_does_not_rescore(api, root):
    api.settled(api.start())
    write_json(root / "labels/p2.json", LABEL | {"verdict": "negative",
                                                 "rated_at": "2099-01-01T00:00:00+00:00"})
    assert api.client.get("/pool").json()["counter"]["corrections"] == 0
    api.settled(api.start())
    assert api.started == [False, False]


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
