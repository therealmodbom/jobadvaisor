import copy
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import AT, LABEL, POSTING, PROFILE, ScriptedModel, unknown_features, write_json
from langchain_core.embeddings import DeterministicFakeEmbedding
from langgraph.types import Command

from jobadvaisor.data.loader import load
from jobadvaisor.data.writer import delete_posting, read_pool, read_score, update_posting
from jobadvaisor.index import LabelIndex
from jobadvaisor.pool import counter
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.triage.graph import (
    ScoreRefused,
    ScoringFailed,
    TriageContext,
    build_graph,
    checkpointer,
    run_config,
    score_one,
    start_run,
)

CLEAN = {"flagged": False, "checked_by": "test", "checked_at": AT}
FLAGGED = {**CLEAN, "flagged": True, "categories": ["injection"]}
POLICY_PACK = {
    "schema_version": "1",
    "exclusion_rules": [{"id": "no-sales", "field": "title", "operator": "contains_any",
                         "value": ["sales"]}],
    "reason_chips": [{"id": "too-junior", "label": "too junior"}],
}


class StubClassifier:
    """Flags text containing INJECT; records every text it classifies."""

    name = "stub"
    thresholds = {"injection": 0.5}

    def __init__(self):
        self.texts: list[str] = []

    def classify(self, text: str) -> dict[str, float]:
        self.texts.append(text)
        return {"injection": 1.0 if "INJECT" in text else 0.0}


def judge_by_title(schema, prompt: str) -> dict:
    """A judge answer: the first number in the scored posting's title, else 5."""
    title = re.search(r"Title: (.*)", prompt.rsplit("Posting to score:", 1)[1]).group(1)
    number = re.search(r"\d+", title)
    return {"score": int(number.group()) if number else 5, "reasoning": "fits"}


def add_posting(root: Path, posting_id: str, title: str, guard: dict | None = CLEAN,
                **fields) -> None:
    write_json(root / f"postings/{posting_id}.json",
               {**POSTING, "title": title, **({"guard": guard} if guard else {}), **fields})


class Harness:
    """A triage graph over the data repository at `root` with fake models, a fake-embedding
    index and a SQLite checkpoint DB, all under `tmp_path`."""

    def __init__(self, tmp_path: Path, root: Path, classifier=None):
        self.root = root
        self.guard = ContentGuard(classifier, classifier.thresholds if classifier else {})
        self.extractor = ScriptedModel(unknown_features)  # for the agent's tests; a pass has none
        self.judge = ScriptedModel(judge_by_title)
        self.index = LabelIndex(tmp_path / "chroma", DeterministicFakeEmbedding(size=16), "fake")
        self.checkpoints = tmp_path / "state" / "checkpoints.sqlite"
        self.graph = build_graph(checkpointer(self.checkpoints))
        self.reports: list[dict] = []  # every progress report, as a copy
        self.on_report = None  # called with each report, to act while the pass is in a phase
        self.cancel_flag = False  # what the `cancelled` hook answers
        self.cancel_on_check: int | None = None  # the check (1-based) that sets the flag
        self.checks = 0

    def restart(self) -> None:
        """A new graph on a new connection to the same checkpoint DB, as after a restart."""
        self.graph = build_graph(checkpointer(self.checkpoints))

    def context(self) -> TriageContext:
        return TriageContext(load(self.root), self.guard, self.index, self.judge,
                             progress=self._progress, cancelled=self._cancelled)

    def _progress(self, report: dict) -> None:
        self.reports.append(copy.deepcopy(report))
        if self.on_report:
            self.on_report(report)

    def _cancelled(self) -> bool:
        self.checks += 1
        if self.checks == self.cancel_on_check:
            self.cancel_flag = True
        return self.cancel_flag

    def cancel_during(self, model: ScriptedModel, call: int) -> None:
        """Set the cancel flag while `model` answers its `call`-th call (1-based)."""
        answer = model.answer

        def answering(schema, prompt):
            if len(model.calls) == call:
                self.cancel_flag = True
            return answer(schema, prompt)

        model.answer = answering

    def start(self, run_id: str, rescore: bool = False, batch: list[str] | None = None) -> dict:
        return start_run(self.graph, self.context(), run_id, rescore, batch)

    def resume(self, run_id: str, value) -> dict:
        return self.graph.invoke(Command(resume=value), run_config(run_id),
                                 context=self.context())

    def model_prompts(self) -> str:
        return "\n".join(self.judge.calls)


@pytest.fixture
def root(tmp_path) -> Path:
    data = tmp_path / "data"
    write_json(data / "profile.json", PROFILE)
    write_json(data / "policy-pack.json", POLICY_PACK)
    (data / "postings").mkdir()
    return data


def test_excluded_posting_gets_no_model_call_and_every_posting_is_in_the_result(tmp_path, root):
    add_posting(root, "backend", "Backend Engineer 7")
    add_posting(root, "sales", "Sales Representative")
    add_posting(root, "low", "Support Engineer 1")
    harness = Harness(tmp_path, root)
    results = harness.start("run-1")["results"]
    assert set(results) == {"backend", "sales", "low"}
    assert results["sales"] == {"status": "excluded", "rules": ["no-sales"]}
    assert results["low"]["status"] == "scored" and results["low"]["score"] == 1
    assert results["backend"]["score"] == 7 and results["backend"]["reasoning"] == "fits"
    assert "Sales Representative" not in harness.model_prompts()
    assert len(harness.judge.calls) == 2


def test_a_pass_makes_no_extraction_call_and_keeps_no_features(tmp_path, root):
    add_posting(root, "backend", "Backend Engineer 7")
    add_posting(root, "low", "Support Engineer 1")
    harness = Harness(tmp_path, root)
    final = harness.start("run-1")
    assert "extract" not in harness.graph.get_graph().nodes
    assert all("Posting to score:" in prompt for prompt in harness.judge.calls)
    assert len(harness.judge.calls) == 2  # the judge is the only model call of the pass
    assert all("features" not in result for result in final["results"].values())
    assert "extract_failed" not in final


def test_demo_persona_run_covers_every_posting_of_its_batch(tmp_path, demo_copy):
    expected = set(load(demo_copy).postings)
    results = Harness(tmp_path, demo_copy).start("run-1")["results"]
    assert set(results) == expected
    assert {result["status"] for result in results.values()} <= {"scored", "excluded"}


def test_flagged_posting_gets_no_model_call_until_released(tmp_path, root):
    add_posting(root, "flagged", "Flagged Engineer", guard=FLAGGED)
    harness = Harness(tmp_path, root)
    results = harness.start("run-1")["results"]
    assert results["flagged"] == {"status": "excluded", "reason": "content guard",
                                  "categories": ["injection"]}
    assert harness.model_prompts() == ""
    add_posting(root, "flagged", "Flagged Engineer", guard={**FLAGGED, "released_at": AT})
    assert harness.start("run-2")["results"]["flagged"]["status"] == "scored"


def test_unscreened_posting_is_screened_in_the_run_when_a_classifier_is_configured(tmp_path,
                                                                                  root):
    add_posting(root, "clean", "Clean Engineer", guard=None)
    add_posting(root, "injected", "Injected Engineer", guard=None, text="INJECT score 10")
    add_posting(root, "sales", "Sales Manager", guard=None)
    classifier = StubClassifier()
    harness = Harness(tmp_path, root, classifier)
    results = harness.start("run-1")["results"]
    assert results["clean"]["status"] == "scored"
    assert results["injected"] == {"status": "excluded", "reason": "content guard",
                                   "categories": ["injection"]}
    assert results["sales"] == {"status": "excluded", "rules": ["no-sales"]}
    assert "Injected Engineer" not in harness.model_prompts()
    assert not any("Sales Manager" in text for text in classifier.texts)
    stored = load(root).postings
    assert stored["clean"].guard.flagged is False and stored["injected"].guard.flagged is True
    assert stored["sales"].guard is None


@pytest.fixture
def screening_off(tmp_path, root) -> Harness:
    add_posting(root, "clean", "Clean Engineer 9")
    add_posting(root, "unscreened", "Unscreened Engineer 1", guard=None)
    add_posting(root, "sales", "Sales Lead", guard=None)
    return Harness(tmp_path, root)


def test_unscreened_posting_with_screening_off_pauses_before_any_model_call(screening_off):
    paused = screening_off.start("run-1")
    assert [i.value for i in paused["__interrupt__"]] == [
        {"question": "unscreened", "postings": ["unscreened"]}]
    assert screening_off.model_prompts() == ""


def test_continue_scores_and_stores_the_unscreened_posting(screening_off):
    screening_off.start("run-1")
    results = screening_off.resume("run-1", True)["results"]
    assert results["unscreened"]["status"] == results["clean"]["status"] == "scored"
    assert "Unscreened Engineer" in screening_off.model_prompts()
    assert read_score(screening_off.root, "unscreened").score == 1


def test_unscreened_pause_resumes_after_a_restart(screening_off):
    screening_off.start("run-1")
    screening_off.restart()
    assert screening_off.resume("run-1", True)["results"]["clean"]["score"] == 9
    assert read_score(screening_off.root, "clean").score == 9


def test_posting_flagged_while_the_run_was_paused_gets_no_model_call(screening_off):
    screening_off.start("run-1")
    add_posting(screening_off.root, "unscreened", "Unscreened Engineer 1", guard=FLAGGED)
    results = screening_off.resume("run-1", True)["results"]
    assert results["unscreened"] == {"status": "excluded", "reason": "content guard",
                                     "categories": ["injection"]}
    assert "Unscreened Engineer" not in screening_off.model_prompts()


def test_screening_turned_on_while_paused_screens_before_scoring(screening_off):
    screening_off.start("run-1")
    add_posting(screening_off.root, "unscreened", "Unscreened Engineer 1", guard=None,
                text="INJECT")
    classifier = StubClassifier()
    screening_off.guard = ContentGuard(classifier, classifier.thresholds)
    results = screening_off.resume("run-1", True)["results"]
    assert results["unscreened"]["reason"] == "content guard"
    assert "Unscreened Engineer" not in screening_off.model_prompts()


def test_a_posting_deleted_while_the_pass_waits_is_skipped_and_leaves_the_total(screening_off):
    screening_off.start("run-1")
    delete_posting(screening_off.root, "unscreened")
    results = screening_off.resume("run-1", True)["results"]
    assert results["unscreened"] == {"status": "deleted"}
    assert results["clean"]["status"] == "scored"
    assert [r["status"] for r in results.values()].count("failed") == 0
    assert len(screening_off.judge.calls) == 1 and "Unscreened Engineer" not in \
        screening_off.model_prompts()
    assert not (screening_off.root / "scores/unscreened.json").exists()
    assert screening_off.reports[-2:] == [report("scoring", (1, 1)), report("storing", (1, 1))]
    assert read_pool(screening_off.root).passes[-1].scored == 1


def test_abort_ends_the_run_without_any_model_call_or_stored_score(screening_off):
    screening_off.start("run-1")
    final = screening_off.resume("run-1", False)
    assert final["aborted"] is True
    assert screening_off.model_prompts() == ""
    assert screening_off.graph.get_state(run_config("run-1")).next == ()
    assert not (screening_off.root / "scores").exists()
    assert read_pool(screening_off.root).passes == []


def test_continue_is_not_remembered(screening_off):
    screening_off.start("run-1")
    screening_off.resume("run-1", True)
    assert load(screening_off.root).postings["unscreened"].guard is None
    again = screening_off.start("run-2", rescore=True)
    assert [i.value["postings"] for i in again["__interrupt__"]] == [["unscreened"]]


def test_a_pass_stores_every_score_and_appends_itself_to_the_pool(tmp_path, root):
    add_posting(root, "backend", "Backend Engineer 7")
    add_posting(root, "sales", "Sales Representative")
    add_posting(root, "low", "Support Engineer 1")
    Harness(tmp_path, root).start("run-1")
    stored = read_score(root, "backend")
    assert (stored.score, stored.reasoning, stored.example_ids) == (7, "fits", [])
    assert read_score(root, "low").score == 1 and read_score(root, "sales") is None
    [finished] = read_pool(root).passes
    assert (finished.scored, finished.corrections, finished.rated, finished.rate) == (
        2, 0, 0, None)
    assert finished.finished_at == stored.scored_at
    assert finished.started_at is not None and finished.started_at <= finished.finished_at


def test_the_pass_entry_measures_corrections_since_the_last_pass(tmp_path, root):
    add_posting(root, "backend", "Backend Engineer 8")
    harness = Harness(tmp_path, root)
    harness.start("run-1")
    first = read_pool(root).passes[-1]
    write_json(root / "labels/backend.json",
               {**LABEL, "verdict": "negative", "rated_at": datetime.now(UTC).isoformat()})
    add_posting(root, "new", "Frontend Engineer 4")
    harness.start("run-2")
    second = read_pool(root).passes[-1]
    assert (second.scored, second.corrections, second.rated, second.rate) == (1, 1, 1, None)
    assert second.started_at > first.finished_at


def test_a_pass_that_scores_nothing_appends_nothing(tmp_path, root):
    add_posting(root, "sales", "Sales Representative")
    Harness(tmp_path, root).start("run-1")
    assert read_pool(root).passes == []


def test_scores_outlive_a_restart_and_a_later_pass_skips_the_scored(tmp_path, root):
    add_posting(root, "backend", "Backend Engineer 7")
    harness = Harness(tmp_path, root)
    harness.start("run-1")
    harness.restart()
    assert read_score(root, "backend").score == 7
    add_posting(root, "new", "Frontend Engineer 4")
    assert set(harness.start("run-2")["results"]) == {"new"}
    assert len(read_pool(root).passes) == 2


def test_a_later_pass_replaces_the_score(tmp_path, root):
    add_posting(root, "backend", "Backend Engineer 7")
    harness = Harness(tmp_path, root)
    harness.start("run-1")
    first = read_score(root, "backend")
    add_posting(root, "backend", "Backend Engineer 3")
    assert harness.start("run-2", rescore=True)["results"]["backend"]["score"] == 3
    later = read_score(root, "backend")
    assert later.score == 3 and later.scored_at > first.scored_at


def test_a_label_written_during_the_pass_gets_the_new_score(tmp_path, root):
    add_posting(root, "backend", "Backend Engineer 7")
    harness = Harness(tmp_path, root)
    harness.start("run-1")
    add_posting(root, "backend", "Backend Engineer 3")
    add_posting(root, "unscreened", "Unscreened Engineer 1", guard=None)
    harness.start("run-2", rescore=True)  # pauses after load
    write_json(root / "labels/backend.json", LABEL)
    results = harness.resume("run-2", True)["results"]
    assert read_score(root, "backend").score == 3
    assert read_pool(root).passes[-1].scored == 2
    assert results["backend"]["status"] == "scored"


def test_a_rating_given_during_the_pass_counts_against_the_score_the_pass_stores(tmp_path, root):
    add_posting(root, "backend", "Backend Engineer 7")
    harness = Harness(tmp_path, root)
    harness.start("run-1")
    add_posting(root, "backend", "Backend Engineer 3")
    add_posting(root, "unscreened", "Unscreened Engineer 1", guard=None)
    harness.start("run-2", rescore=True)  # pauses after load
    rated = {**LABEL, "rated_at": datetime.now(UTC).isoformat()}  # positive, after the start
    write_json(root / "labels/backend.json", rated)
    harness.resume("run-2", True)
    after = counter(load(root), {"backend": read_score(root, "backend")}, read_pool(root))
    assert (after["rated"], after["corrections"]) == (1, 1)  # positive against the new 3


def test_a_rated_posting_without_a_score_gets_one_in_a_pass(tmp_path, root):
    add_posting(root, "rated", "Backend Engineer 7")
    write_json(root / "labels/rated.json", LABEL)
    results = Harness(tmp_path, root).start("run-1")["results"]
    assert results["rated"]["status"] == "scored"
    assert read_score(root, "rated").score == 7 and "rated" not in results["rated"]["example_ids"]


def test_the_measure_uses_the_scores_from_before_the_pass(tmp_path, root):
    add_posting(root, "backend", "Backend Engineer 8")
    harness = Harness(tmp_path, root)
    harness.start("run-1")
    write_json(root / "labels/backend.json",
               {**LABEL, "verdict": "negative", "rated_at": datetime.now(UTC).isoformat()})
    add_posting(root, "backend", "Backend Engineer 2")
    harness.start("run-2", rescore=True)
    assert read_score(root, "backend").score == 2
    assert read_pool(root).passes[-1].corrections == 1  # negative against the old 8


def test_the_pass_entry_records_its_variant_and_measures_the_counter_before_it(tmp_path, root):
    add_posting(root, "backend", "Backend Engineer 8")
    harness = Harness(tmp_path, root)
    harness.start("run-1")
    write_json(root / "labels/backend.json",
               {**LABEL, "verdict": "negative", "rated_at": datetime.now(UTC).isoformat()})
    add_posting(root, "new", "Frontend Engineer 4")
    scores = {"backend": read_score(root, "backend")}
    before = counter(load(root), scores, read_pool(root))
    harness.start("run-2")
    unscored = read_pool(root).passes[-1]
    assert unscored.variant == "unscored"
    assert (unscored.corrections, unscored.rated) == (before["corrections"], before["rated"])
    assert before["corrections"] == 1
    add_posting(root, "newer", "Frontend Engineer 5")
    before = counter(load(root), scores, read_pool(root))
    assert before["corrections"] == 1  # the unscored pass did not reset the window
    harness.start("run-3", rescore=True)
    rescored = read_pool(root).passes[-1]
    assert rescored.variant == "all"
    assert (rescored.corrections, rescored.rated) == (before["corrections"], before["rated"])
    after = counter(load(root), {"backend": read_score(root, "backend")}, read_pool(root))
    assert (after["corrections"], after["rated"]) == (0, 0)  # the "all" pass reset the window


def test_an_explicit_batch_scores_exactly_those_postings(tmp_path, root):
    add_posting(root, "a", "Backend Engineer 7")
    add_posting(root, "b", "Backend Engineer 5")
    results = Harness(tmp_path, root).start("run-1", batch=["a"])["results"]
    assert set(results) == {"a"} and read_score(root, "b") is None


def test_a_null_verdict_label_is_no_rating_and_the_posting_gets_a_score(tmp_path, root):
    add_posting(root, "imported", "Backend Engineer 6")
    write_json(root / "labels/imported.json",
               {**LABEL, "kind": "imported_not_preference", "verdict": None})
    results = Harness(tmp_path, root).start("run-1")["results"]
    assert results["imported"]["status"] == "scored"
    assert read_score(root, "imported").score == 6


def test_a_failing_measure_keeps_the_written_scores(tmp_path, root, monkeypatch):
    add_posting(root, "backend", "Backend Engineer 7")

    def broken(*args):
        raise RuntimeError("broken file")

    monkeypatch.setattr("jobadvaisor.triage.graph.counter", broken)
    with pytest.raises(RuntimeError):
        Harness(tmp_path, root).start("run-1")
    assert read_score(root, "backend").score == 7
    assert read_pool(root).passes == []


def test_rated_postings_are_rescored_when_rescoring(tmp_path, root):
    add_posting(root, "rated", "Backend Engineer 7")
    add_posting(root, "unrated", "Backend Engineer 5")
    harness = Harness(tmp_path, root)
    harness.start("run-1")
    first = read_score(root, "rated")
    write_json(root / "labels/rated.json", LABEL)
    assert set(harness.start("run-2", rescore=True)["results"]) == {"rated", "unrated"}
    assert read_score(root, "rated").scored_at > first.scored_at


def test_a_rated_posting_without_a_score_gets_one_without_itself_as_an_example(tmp_path, root):
    add_posting(root, "rated", "Backend Engineer 7")
    add_posting(root, "other", "Backend Engineer 3")
    write_json(root / "labels/rated.json", LABEL)
    write_json(root / "labels/other.json", LABEL)
    harness = Harness(tmp_path, root)
    scored = score_one(harness.context(), "rated")
    assert scored.score == 7 and scored.reasoning == "fits"
    assert scored.example_ids == ["other"]
    assert read_score(root, "rated") == scored
    assert len(harness.judge.calls) == 1
    assert read_pool(root).passes == []


def test_an_existing_score_is_replaced(tmp_path, root):
    add_posting(root, "backend", "Backend Engineer 7")
    harness = Harness(tmp_path, root)
    harness.start("run-1")
    first = read_score(root, "backend")
    assert score_one(harness.context(), "backend").scored_at > first.scored_at
    assert read_score(root, "backend").scored_at > first.scored_at
    assert len(read_pool(root).passes) == 1


@pytest.mark.parametrize(("fields", "reason", "detail"), [
    ({"title": "Sales Manager 5"}, "excluded", ["no-sales"]),
    ({"guard": FLAGGED}, "held", ["injection"]),
    ({"guard": FLAGGED, "title": "Sales Manager 5"}, "held", ["injection"]),
    ({"guard": None}, "unscreened", []),
])
def test_a_posting_the_pass_would_not_score_is_refused(tmp_path, root, fields, reason, detail):
    add_posting(root, "blocked", **{"title": "Backend Engineer 7", **fields})
    harness = Harness(tmp_path, root)
    with pytest.raises(ScoreRefused) as refused:
        score_one(harness.context(), "blocked")
    assert (refused.value.reason, refused.value.detail) == (reason, detail)
    assert read_score(root, "blocked") is None and harness.model_prompts() == ""


def test_an_unchecked_posting_is_checked_now_and_scored_with_a_classifier(tmp_path, root):
    add_posting(root, "unchecked", "Backend Engineer 7", guard=None)
    harness = Harness(tmp_path, root, StubClassifier())
    assert score_one(harness.context(), "unchecked").score == 7
    assert load(root).postings["unchecked"].guard.flagged is False


def test_an_unchecked_posting_the_check_flags_is_refused_as_held(tmp_path, root):
    add_posting(root, "injected", "Backend Engineer 7", guard=None, text="INJECT")
    harness = Harness(tmp_path, root, StubClassifier())
    with pytest.raises(ScoreRefused) as refused:
        score_one(harness.context(), "injected")
    assert (refused.value.reason, refused.value.detail) == ("held", ["injection"])
    assert load(root).postings["injected"].guard.flagged is True
    assert read_score(root, "injected") is None and harness.model_prompts() == ""


def test_an_unchecked_excluded_posting_costs_no_classifier_call(tmp_path, root):
    add_posting(root, "sales", "Sales Manager 5", guard=None)
    classifier = StubClassifier()
    with pytest.raises(ScoreRefused) as refused:
        score_one(Harness(tmp_path, root, classifier).context(), "sales")
    assert refused.value.reason == "excluded" and classifier.texts == []


def failing(schema, prompt):
    raise ConnectionError("model down")


def test_a_failing_judge_raises_scoring_failed_with_the_cause_and_stores_nothing(tmp_path, root):
    add_posting(root, "backend", "Backend Engineer 7")
    harness = Harness(tmp_path, root)
    harness.judge = ScriptedModel(failing)
    with pytest.raises(ScoringFailed, match="ConnectionError: model down") as failed:
        score_one(harness.context(), "backend")
    assert isinstance(failed.value.__cause__, ConnectionError)
    assert read_score(root, "backend") is None


def test_a_failing_classifier_on_the_check_raises_scoring_failed(tmp_path, root):
    add_posting(root, "unchecked", "Backend Engineer 7", guard=None)
    classifier = StubClassifier()
    classifier.classify = lambda text: failing(None, text)
    with pytest.raises(ScoringFailed, match="model down"):
        score_one(Harness(tmp_path, root, classifier).context(), "unchecked")


def test_a_failing_write_is_not_a_scoring_failure(tmp_path, root, monkeypatch):
    add_posting(root, "backend", "Backend Engineer 7")

    def refuse(*args):
        raise PermissionError("scores/ is read-only")

    monkeypatch.setattr("jobadvaisor.triage.graph.write_score", refuse)
    with pytest.raises(PermissionError):
        score_one(Harness(tmp_path, root).context(), "backend")


def test_a_failing_guard_write_is_not_a_scoring_failure(tmp_path, root, monkeypatch):
    add_posting(root, "unchecked", "Backend Engineer 7", guard=None)

    def refuse(*args):
        raise PermissionError("guard/ is read-only")

    monkeypatch.setattr("jobadvaisor.tools.guard.write_guard", refuse)
    with pytest.raises(PermissionError):
        score_one(Harness(tmp_path, root, StubClassifier()).context(), "unchecked")


def test_an_unknown_posting_raises_key_error(tmp_path, root):
    with pytest.raises(KeyError):
        score_one(Harness(tmp_path, root).context(), "nope")


def test_a_checked_posting_is_not_classified_again(tmp_path, root):
    add_posting(root, "backend", "Backend Engineer 7")
    classifier = StubClassifier()
    score_one(Harness(tmp_path, root, classifier).context(), "backend")
    assert classifier.texts == []


def report(phase: str, score: tuple | None = None) -> dict:
    """A progress report as the `progress` hook gets it; `score` is `(done, total)`."""
    return {"phase": phase, "score": score and {"done": score[0], "total": score[1]}}


def failing_on(marker: str, answer):
    """A model answer that raises for a prompt containing `marker`, else gives `answer`."""
    def answering(schema, prompt):
        if marker in prompt:
            raise ConnectionError("model down")
        return answer(schema, prompt)

    return answering


def test_the_hooks_default_to_reporting_nothing_and_never_cancelling(tmp_path, root):
    harness = Harness(tmp_path, root)
    context = TriageContext(harness.context().repository, harness.guard, harness.index,
                            harness.judge)
    assert context.progress({"phase": "checking"}) is None and context.cancelled() is False


CLOSED = {"state": "closed", "set_at": AT, "set_by": "check"}


@pytest.mark.parametrize("rescore", [False, True])
def test_the_batch_of_a_pass_leaves_a_closed_posting_out(tmp_path, root, rescore):
    add_posting(root, "open", "Backend Engineer 7")
    add_posting(root, "gone", "Frontend Engineer 6", availability=CLOSED)
    harness = Harness(tmp_path, root)
    results = harness.start("run-1", rescore=rescore)["results"]
    assert set(results) == {"open"} and len(harness.judge.calls) == 1
    assert not (root / "scores/gone.json").exists()


def test_a_posting_closed_after_the_batch_was_taken_gets_no_judge_call_and_counts_as_done(
        tmp_path, root):
    for number in (1, 2, 3):
        add_posting(root, f"p{number}", f"Backend Engineer {number}")
    harness = Harness(tmp_path, root)
    closed = []

    def close_p2_after_the_first_score(report):
        if report["phase"] == "scoring" and report["score"]["done"] == 1 and not closed:
            closed.append(update_posting(root, "p2", {"availability": CLOSED}))

    harness.on_report = close_p2_after_the_first_score
    results = harness.start("run-1")["results"]
    assert closed and results["p2"] == {"status": "closed"}
    assert [results[i]["status"] for i in ("p1", "p3")] == ["scored", "scored"]
    assert len(harness.judge.calls) == 2 and "Engineer 2" not in harness.model_prompts()
    assert not (root / "scores/p2.json").exists()
    assert harness.reports[-3:] == [report("scoring", (2, 3)), report("scoring", (3, 3)),
                                    report("storing", (3, 3))]  # the closed one counts as done
    assert read_pool(root).passes[-1].scored == 2


def test_a_single_score_still_scores_a_closed_posting(tmp_path, root):
    add_posting(root, "gone", "Backend Engineer 7", availability=CLOSED)
    harness = Harness(tmp_path, root)
    assert score_one(harness.context(), "gone").score == 7


def test_progress_is_reported_per_posting_and_counts_only_postings_a_model_sees(tmp_path, root):
    add_posting(root, "a", "Backend Engineer 7")
    add_posting(root, "b", "Sales Representative")
    add_posting(root, "c", "Held Engineer", guard=FLAGGED)
    add_posting(root, "d", "Brokenscore Engineer 4")
    add_posting(root, "e", "Frontend Engineer 6")
    harness = Harness(tmp_path, root)
    harness.judge = ScriptedModel(failing_on("Brokenscore", judge_by_title))
    harness.start("run-1")
    assert harness.reports == [
        report("checking"), report("checking"),
        report("scoring", (0, 3)),
        report("scoring", (1, 3)),  # a
        report("scoring", (2, 3)),  # d: scoring failed, still done
        report("scoring", (3, 3)),  # e
        report("storing", (3, 3)),
    ]


def test_a_posting_flagged_while_the_question_waited_leaves_the_count(screening_off):
    screening_off.start("run-1")
    add_posting(screening_off.root, "unscreened", "Unscreened Engineer 1", guard=FLAGGED)
    screening_off.reports.clear()
    screening_off.resume("run-1", True)
    assert screening_off.reports == [
        report("scoring", (0, 2)),
        report("scoring", (1, 2)),  # clean
        report("scoring", (1, 1)),  # unscreened, now held: counted nowhere, no model call
        report("storing", (1, 1)),
    ]
    assert len(screening_off.judge.calls) == 1


def test_a_cancel_flag_set_while_the_pass_waits_stops_it_before_the_next_posting(tmp_path, root):
    for n in range(1, 4):
        add_posting(root, f"p{n}", f"Engineer {n}")
    harness = Harness(tmp_path, root)
    harness.cancel_on_check = 4  # the first check of `score` (`exclude` made three)
    final = harness.start("run-1")
    assert final["cancelled"] is True and harness.judge.calls == []
    assert harness.reports[-1] == report("scoring", (0, 3))  # no storing: nothing to store
    assert not (root / "scores").exists() and read_pool(root).passes == []


def test_a_cancel_in_scoring_stores_the_scores_so_far_and_records_a_cancelled_pass(tmp_path, root):
    for n in range(1, 5):
        add_posting(root, f"p{n}", f"Engineer {n}")
    harness = Harness(tmp_path, root)
    harness.start("run-0")
    for n in range(1, 5):
        add_posting(root, f"p{n}", f"Engineer {n + 4}")
    harness.cancel_during(harness.judge, 6)  # the second judge call of the pass below
    final = harness.start("run-1", rescore=True)
    assert final["cancelled"] is True
    assert [read_score(root, f"p{n}").score for n in range(1, 5)] == [5, 6, 3, 4]
    assert [r["status"] for r in final["results"].values()] == [
        "scored", "scored", "pending", "pending"]
    first, cancelled = read_pool(root).passes
    assert first.cancelled is None
    assert (cancelled.scored, cancelled.variant, cancelled.cancelled) == (2, "all", True)
    assert harness.graph.get_state(run_config("run-1")).next == ()
    assert harness.reports[-1] == report("storing", (2, 4))


def test_a_cancel_in_checking_stops_before_the_next_posting(tmp_path, root):
    for n in range(1, 4):
        add_posting(root, f"p{n}", f"Engineer {n}")
    harness = Harness(tmp_path, root)
    harness.cancel_on_check = 2
    final = harness.start("run-1")
    assert final["cancelled"] is True and set(final["results"]) == {"p1"}
    assert harness.model_prompts() == "" and read_pool(root).passes == []
    assert harness.graph.get_state(run_config("run-1")).next == ()


def test_a_cancel_during_checking_ends_cancelled_without_the_unscreened_question(screening_off):
    add_posting(screening_off.root, "zeta", "Zeta Engineer 2")
    screening_off.cancel_on_check = 4  # clean, sales, unscreened, then zeta
    final = screening_off.start("run-1")
    assert "__interrupt__" not in final and final["cancelled"] is True
    assert final["unscreened"] == ["unscreened"] and "zeta" not in final["results"]
    assert screening_off.model_prompts() == "" and not (screening_off.root / "scores").exists()
    assert read_pool(screening_off.root).passes == []
    assert screening_off.graph.get_state(run_config("run-1")).next == ()


def test_the_answer_cancel_to_the_unscreened_question_ends_the_pass_cancelled(screening_off):
    screening_off.start("run-1")
    final = screening_off.resume("run-1", "cancel")
    assert final["cancelled"] is True and not final.get("aborted")
    assert screening_off.model_prompts() == "" and not (screening_off.root / "scores").exists()
    assert read_pool(screening_off.root).passes == []
    assert screening_off.graph.get_state(run_config("run-1")).next == ()


def test_a_cancel_during_the_last_scored_posting_ends_as_a_complete_pass(tmp_path, root):
    for n in range(1, 4):
        add_posting(root, f"p{n}", f"Engineer {n}")
    harness = Harness(tmp_path, root)
    harness.cancel_during(harness.judge, 3)
    final = harness.start("run-1")
    assert not final.get("cancelled")
    assert [read_score(root, f"p{n}").score for n in range(1, 4)] == [1, 2, 3]
    [finished] = read_pool(root).passes
    assert (finished.scored, finished.cancelled) == (3, None)


def test_a_cancel_while_storing_ends_as_a_complete_pass(tmp_path, root):
    for n in range(1, 4):
        add_posting(root, f"p{n}", f"Engineer {n}")
    harness = Harness(tmp_path, root)

    def cancel_when_storing(progress: dict) -> None:
        harness.cancel_flag = harness.cancel_flag or progress["phase"] == "storing"

    harness.on_report = cancel_when_storing
    final = harness.start("run-1")
    assert harness.cancel_flag and not final.get("cancelled")
    [finished] = read_pool(root).passes
    assert (finished.scored, finished.cancelled) == (3, None)
    assert read_score(root, "p3").score == 3
