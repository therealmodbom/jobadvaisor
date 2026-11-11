"""`Runs.score`: a single score shares the pass's one computing slot."""

import threading

import pytest
from conftest import ScriptedModel, write_json
from test_triage_graph import POLICY_PACK, Harness, add_posting, judge_by_title

from jobadvaisor.data.writer import read_score
from jobadvaisor.triage.graph import ScoreRefused, ScoringFailed
from jobadvaisor.triage.runs import RunBusyError, Runs


class Gated:
    """A `Runs` over a fake judge that signals `entered` and then waits for `gate`."""

    def __init__(self, tmp_path):
        root = tmp_path / "data"
        write_json(root / "profile.json", {"schema_version": "1", "summary": "Developer"})
        write_json(root / "policy-pack.json", POLICY_PACK)
        add_posting(root, "p1", "Engineer 1")
        add_posting(root, "p2", "Engineer 2")
        self.root = root
        self.entered, self.gate = threading.Event(), threading.Event()
        self.gate.set()
        harness = Harness(tmp_path, root)
        harness.judge = ScriptedModel(self._judge)
        self.runs = Runs(harness.graph, harness.context)

    judge_fails = False

    def _judge(self, schema, prompt):
        if self.judge_fails:
            raise ConnectionError("model down")
        self.entered.set()
        assert self.gate.wait(10), "gate never opened"
        return judge_by_title(schema, prompt)

    def hold_a_single_score(self) -> threading.Thread:
        """Start a single score of p1 in a thread and return once its judge is running."""
        self.gate.clear()
        thread = threading.Thread(target=self.runs.score, args=("p1",))
        thread.start()
        assert self.entered.wait(10), "judge never entered"
        return thread

    def release(self, thread: threading.Thread) -> None:
        self.gate.set()
        thread.join(10)


@pytest.fixture
def gated(tmp_path) -> Gated:
    return Gated(tmp_path)


def test_a_single_score_scores_and_returns_the_stored_score(gated):
    assert gated.runs.score("p1").score == 1
    assert read_score(gated.root, "p1").score == 1


def test_a_single_score_during_a_computing_pass_is_busy(gated):
    gated.gate.clear()
    run_id = gated.runs.start()
    assert gated.entered.wait(10)
    with pytest.raises(RunBusyError) as busy:
        gated.runs.score("p2")
    assert busy.value.run_id == run_id
    gated.gate.set()


def test_a_pass_started_during_a_single_score_is_busy(gated):
    thread = gated.hold_a_single_score()
    with pytest.raises(RunBusyError):
        gated.runs.start()
    gated.release(thread)


def test_a_second_single_score_during_a_first_is_busy(gated):
    thread = gated.hold_a_single_score()
    with pytest.raises(RunBusyError):
        gated.runs.score("p2")
    gated.release(thread)
    assert gated.runs.score("p2").score == 2


def test_the_slot_is_free_again_after_a_failing_single_score(gated):
    add_posting(gated.root, "sales", "Sales Lead")
    with pytest.raises(ScoreRefused):
        gated.runs.score("sales")
    assert gated.runs.score("p1").score == 1


def test_the_slot_is_free_again_after_an_unknown_posting_and_after_a_judge_error(gated):
    with pytest.raises(KeyError):
        gated.runs.score("nope")
    gated.judge_fails = True
    with pytest.raises(ScoringFailed):
        gated.runs.score("p1")
    gated.judge_fails = False
    assert gated.runs.score("p1").score == 1
