"""`Runs`: progress of a running pass, and `Runs.cancel` (`design.md` → Cancel is a flag checked
before every posting, `Runs.cancel(run_id)`). A fake judge blocks on a `threading.Event`, so no
test waits on the clock."""

import threading

import pytest
from conftest import ScriptedModel, write_json
from langgraph.graph import END, START, StateGraph
from test_triage_graph import POLICY_PACK, Harness, add_posting, judge_by_title

from jobadvaisor.data.writer import read_pool, read_score
from jobadvaisor.triage import graph as graph_module
from jobadvaisor.triage.graph import run_config, start_run
from jobadvaisor.triage.runs import RunBusyError, Runs, RunStateError


class Blocking:
    """A `Runs` over postings `p1`..`p3` (and `unscreened`, which the pass asks about) whose
    judge blocks on its `block_at`-th call: it sets `entered`, then waits for `gate`."""

    def __init__(self, tmp_path, unscreened: bool = False, block_at: int | None = None):
        root = tmp_path / "data"
        write_json(root / "profile.json", {"schema_version": "1", "summary": "Developer"})
        write_json(root / "policy-pack.json", POLICY_PACK)
        for n in range(1, 4):
            add_posting(root, f"p{n}", f"Engineer {n}")
        if unscreened:
            add_posting(root, "unscreened", "Unscreened Engineer 2", guard=None)
        self.root, self.block_at = root, block_at
        self.entered, self.gate = threading.Event(), threading.Event()
        self.harness = Harness(tmp_path, root)
        self.harness.judge = ScriptedModel(self._judge)
        self.runs = Runs(self.harness.graph, self.harness.context)

    def _judge(self, schema, prompt):
        if len(self.harness.judge.calls) == self.block_at:
            self.entered.set()
            assert self.gate.wait(10), "gate never opened"
        return judge_by_title(schema, prompt)

    def start_and_wait_for_the_block(self) -> str:
        run_id = self.runs.start()
        assert self.entered.wait(10), "the judge never reached its block"
        return run_id

    def settle(self) -> None:
        """Return once the pass thread has ended its step (the executor has one worker)."""
        self.runs._executor.submit(lambda: None).result(10)


@pytest.fixture
def blocking(tmp_path) -> Blocking:
    return Blocking(tmp_path, block_at=2)


def test_progress_is_readable_while_the_pass_runs(blocking):
    run_id = blocking.start_and_wait_for_the_block()
    running = blocking.runs.read(run_id)
    assert running["status"] == "running" and running["cancel_requested"] is False
    assert running["progress"] == {"phase": "scoring", "score": {"done": 1, "total": 3}}
    running["progress"]["score"]["done"] = 99  # a copy: the run's own report stays as it was
    assert blocking.runs.read(run_id)["progress"]["score"]["done"] == 1
    blocking.gate.set()
    blocking.settle()
    assert blocking.runs.read(run_id)["status"] == "done"
    assert blocking.runs.read(run_id)["progress"]["phase"] == "storing"


def test_cancel_reports_cancel_requested_until_the_pass_has_stopped(blocking):
    run_id = blocking.start_and_wait_for_the_block()
    blocking.runs.cancel(run_id)
    requested = blocking.runs.read(run_id)
    assert requested["status"] == "running" and requested["cancel_requested"] is True
    blocking.gate.set()
    blocking.settle()
    ended = blocking.runs.read(run_id)
    assert ended["status"] == "cancelled" and ended["cancel_requested"] is False
    assert [r["status"] for r in ended["results"].values()] == ["scored", "scored", "pending"]
    assert read_score(blocking.root, "p2").score == 2 and read_score(blocking.root, "p3") is None
    assert read_pool(blocking.root).passes[0].cancelled is True
    assert blocking.runs._cancelled == set()
    assert blocking.runs.start()  # the slot is free again
    blocking.settle()


def test_a_cancel_during_the_first_score_stops_after_that_posting(tmp_path):
    blocking = Blocking(tmp_path, block_at=1)
    run_id = blocking.start_and_wait_for_the_block()
    blocking.runs.cancel(run_id)
    blocking.gate.set()
    blocking.settle()
    assert blocking.runs.read(run_id)["status"] == "cancelled"
    assert read_score(blocking.root, "p1").score == 1  # the posting in flight completes
    assert read_pool(blocking.root).passes[0].scored == 1


def test_a_pass_resumed_with_the_answer_is_cancelled_too(tmp_path):
    blocking = Blocking(tmp_path, unscreened=True, block_at=2)
    run_id = blocking.runs.start()
    blocking.settle()
    assert blocking.runs.read(run_id)["status"] == "awaiting_answer"
    blocking.runs.answer_unscreened(run_id, True)
    assert blocking.entered.wait(10)
    blocking.runs.cancel(run_id)
    blocking.gate.set()
    blocking.settle()
    assert blocking.runs.read(run_id)["status"] == "cancelled"
    assert read_score(blocking.root, "p3") is None


def test_a_cancel_after_the_last_check_of_checking_ends_cancelled_without_the_question(
        tmp_path, monkeypatch):
    blocking = Blocking(tmp_path, unscreened=True)
    entered, gate = threading.Event(), threading.Event()
    exclusions = graph_module.check_exclusions

    def last_posting_blocks(posting, rules):
        if posting.title.startswith("Unscreened"):  # the last posting of the batch
            entered.set()
            assert gate.wait(10), "gate never opened"
        return exclusions(posting, rules)

    monkeypatch.setattr(graph_module, "check_exclusions", last_posting_blocks)
    run_id = blocking.runs.start()
    assert entered.wait(10)
    blocking.runs.cancel(run_id)  # accepted: no check of `exclude` follows
    gate.set()
    blocking.settle()
    ended = blocking.runs.read(run_id)
    assert ended["status"] == "cancelled" and ended["unscreened"] == ["unscreened"]
    assert blocking.harness.judge.calls == [] and read_pool(blocking.root).passes == []
    assert blocking.runs._cancelled == set() and blocking.runs.start()
    blocking.settle()


def test_a_failing_cancel_resume_is_tried_once_and_frees_the_slot(tmp_path, monkeypatch):
    blocking = Blocking(tmp_path, unscreened=True)
    entered, gate = threading.Event(), threading.Event()
    exclusions = graph_module.check_exclusions

    def last_posting_blocks(posting, rules):
        if posting.title.startswith("Unscreened"):
            entered.set()
            assert gate.wait(10), "gate never opened"
        return exclusions(posting, rules)

    monkeypatch.setattr(graph_module, "check_exclusions", last_posting_blocks)
    runs, attempts = blocking.runs, []
    context = runs._context

    def context_failing_on_the_resume():
        attempts.append(1)
        if len(attempts) == 2:  # the first call is the pass's own, the second is the resume's
            raise OSError("repository unreadable")
        return context()

    runs._context = context_failing_on_the_resume
    run_id = runs.start()
    assert entered.wait(10)
    runs.cancel(run_id)
    gate.set()
    blocking.settle()
    assert len(attempts) == 2  # one resume, no second try
    assert runs._computing == set() and runs._cancelled == set()
    assert "repository unreadable" in runs.read(run_id)["error"]
    assert runs.start()  # the slot is free
    blocking.settle()


def test_claiming_the_slot_drops_a_cancel_of_an_earlier_step_at_once(tmp_path):
    runs = Blocking(tmp_path).runs
    runs._cancelled.add("run-1")  # the request of an earlier step
    runs._claim("run-1")
    assert runs._cancelled == set()  # no gap in which a new request could be lost


class SpyLock:
    """A lock that sets `attempted` when `watched` tries to take it."""

    def __init__(self):
        self._lock = threading.Lock()
        self.attempted, self.watched = threading.Event(), None

    def __enter__(self):
        if threading.current_thread() is self.watched:
            self.attempted.set()
        self._lock.acquire()
        return self

    def __exit__(self, *exc):
        self._lock.release()


def test_a_cancel_that_waits_on_the_lock_of_the_end_section_finds_the_slot_free(tmp_path):
    blocking = Blocking(tmp_path, unscreened=True)
    runs = blocking.runs
    spy, outcome = SpyLock(), {}
    runs._lock = spy

    def cancel_it():
        try:
            runs.cancel(run_id)
        except Exception as error:
            outcome["error"] = error

    canceller = threading.Thread(target=cancel_it)
    spy.watched = canceller
    get_state, main = runs._graph.get_state, threading.current_thread()

    def get_state_in_the_end_section(config):
        if threading.current_thread() is not main and not canceller.is_alive():
            canceller.start()  # the end section holds the lock here
            assert spy.attempted.wait(10), "the cancel never reached the lock"
        return get_state(config)

    runs._graph.get_state = get_state_in_the_end_section
    run_id = runs.start()
    blocking.settle()
    canceller.join(10)
    runs._graph.get_state = get_state
    assert isinstance(outcome["error"], RunStateError)
    assert "awaiting_answer" in str(outcome["error"])
    assert runs._cancelled == set()
    assert runs.read(run_id)["status"] == "awaiting_answer"


def test_cancel_refuses_an_unknown_run_and_a_single_score(tmp_path):
    blocking = Blocking(tmp_path, block_at=1)
    runs = blocking.runs
    with pytest.raises(KeyError):
        runs.cancel("nope")
    single = threading.Thread(target=runs.score, args=("p1",))
    single.start()
    assert blocking.entered.wait(10)
    with pytest.raises(KeyError):
        runs.cancel("score:p1")  # it computes, and is no pass
    with pytest.raises(RunBusyError):
        runs.start()
    blocking.gate.set()
    single.join(10)
    assert read_score(blocking.root, "p1").score == 1  # the score went on


def test_cancel_refuses_a_pass_that_waits_for_the_answer_or_has_ended(tmp_path):
    blocking = Blocking(tmp_path, unscreened=True)
    runs = blocking.runs
    waiting = runs.start()
    blocking.settle()
    with pytest.raises(RunStateError, match="awaiting_answer"):
        runs.cancel(waiting)
    assert runs._cancelled == set()
    runs.answer_unscreened(waiting, True)
    blocking.settle()
    with pytest.raises(RunStateError, match="done"):
        runs.cancel(waiting)
    fresh = Runs(blocking.harness.graph, blocking.harness.context)  # as after a restart
    with pytest.raises(RunStateError, match="done"):
        fresh.cancel(waiting)
    with pytest.raises(KeyError):
        fresh.cancel("nope")


def test_a_fresh_runs_over_the_same_saver_knows_no_progress(tmp_path):
    blocking = Blocking(tmp_path)
    run_id = blocking.runs.start()
    blocking.settle()
    assert blocking.runs.read(run_id)["progress"]["phase"] == "storing"
    fresh = Runs(blocking.harness.graph, blocking.harness.context)
    restarted = fresh.read(run_id)
    assert restarted["status"] == "done"
    assert restarted["progress"] is None and restarted["cancel_requested"] is False


def test_a_restart_during_a_pass_leaves_it_failed_without_progress_and_not_cancellable(blocking):
    run_id = blocking.start_and_wait_for_the_block()
    fresh = Runs(blocking.harness.graph, blocking.harness.context)  # the process restarted
    restarted = fresh.read(run_id)
    assert restarted["status"] == "failed" and restarted["progress"] is None
    assert restarted["cancel_requested"] is False
    with pytest.raises(RunStateError, match="failed"):
        fresh.cancel(run_id)
    blocking.gate.set()
    blocking.settle()


def test_a_stale_cancel_does_not_stop_a_pass_resumed_with_the_answer(tmp_path):
    blocking = Blocking(tmp_path, unscreened=True)
    runs = blocking.runs
    run_id = runs.start()
    blocking.settle()
    runs._cancelled.add(run_id)  # a request that outlived its step; `cancel` itself refuses one
    runs.answer_unscreened(run_id, True)
    blocking.settle()
    assert runs.read(run_id)["status"] == "done"
    assert read_score(blocking.root, "unscreened").score == 2


def graph_with_the_extract_node(saver):
    """The triage graph as it was before the pass stopped reading features, for a pass without
    unscreened postings: a node `extract` between `exclude` and `score`, and a static stop before
    it, which leaves the checkpoint a restart in that node would have left."""
    old = StateGraph(graph_module.TriageState, context_schema=graph_module.TriageContext)
    for node in (graph_module.load, graph_module.exclude, graph_module.score,
                 graph_module.store_scores):
        old.add_node(node.__name__, node)
    old.add_node("extract", lambda state: {})
    old.add_edge(START, "load")
    old.add_edge("load", "exclude")
    old.add_edge("exclude", "extract")
    old.add_edge("extract", "score")
    old.add_edge("score", "store_scores")
    old.add_edge("store_scores", END)
    return old.compile(checkpointer=saver, interrupt_before=["extract"])


def test_an_old_checkpoint_whose_next_node_was_extract_reads_failed_not_done(tmp_path):
    blocking = Blocking(tmp_path)
    harness = blocking.harness
    old = graph_with_the_extract_node(harness.graph.checkpointer)
    start_run(old, harness.context(), "old-run")
    assert old.get_state(run_config("old-run")).next == ("extract",)
    assert harness.graph.get_state(run_config("old-run")).next == ()  # the new graph has no node
    run = blocking.runs.read("old-run")
    assert run["status"] == "failed"
    assert run["results"]["p1"] == {"status": "pending"}
    assert read_pool(blocking.root).passes == []  # nothing was stored
    with pytest.raises(RunStateError, match="failed"):
        blocking.runs.cancel("old-run")
