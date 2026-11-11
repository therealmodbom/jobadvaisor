"""The pass lifecycle the API drives (`design.md` → A pass is the triage graph without its
rating pause): passes compute in a background thread, one at a time; a pass paused over
unscreened postings does not block a new one. A single score (`Runs.score`) runs in the
caller's thread but takes the same one slot."""

import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from jobadvaisor.data.models import Score
from jobadvaisor.triage.graph import TriageContext, run_config, score_one, start_run


class RunBusyError(Exception):
    """Another run is computing; `run_id` names it."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(f"run {run_id} is still computing")


class RunStateError(Exception):
    """The run is not in a state that takes this request; the message says why."""


class Runs:
    """Starts, reads and resumes passes. `context` builds a fresh `TriageContext` for every
    invocation, so each step sees the data repository as it is on disk."""

    def __init__(self, graph: CompiledStateGraph, context: Callable[[], TriageContext]):
        self._graph, self._context = graph, context
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._lock = threading.Lock()
        self._computing: set[str] = set()
        self._errors: dict[str, str] = {}

    def start(self, rescore: bool = False) -> str:
        """Start a pass in the background and return its ID at once; `rescore` as in
        `start_run`. Raises `RunBusyError` while another pass or a single score computes."""
        run_id = uuid.uuid4().hex
        self._compute(run_id, lambda: start_run(self._graph, self._context(), run_id,
                                                rescore))
        return run_id

    def read(self, run_id: str) -> dict | None:
        """The run's status, result and unscreened postings, or `None` for an unknown run.

        `status` is `running`, `awaiting_answer` (the unscreened question), `done`, `aborted`
        or `failed` (with `error` when this process saw it fail). `started_at` is the ISO time
        of the run's first checkpoint, `None` before it has one.
        """
        config = run_config(run_id)
        with self._lock:  # a run ending between the two reads would be judged by a stale snapshot
            computing = run_id in self._computing
            snapshot = self._graph.get_state(config)
        values = snapshot.values
        if not values and not computing:
            if run_id in self._errors:  # it failed before its first checkpoint
                return {"run_id": run_id, "status": "failed", "results": {}, "unscreened": [],
                        "error": self._errors[run_id], "started_at": None}
            return None
        first = next(iter(reversed(list(self._graph.get_state_history(config)))), None)
        return {"run_id": run_id, "status": self._status(snapshot, computing),
                "results": values.get("results", {}), "unscreened": values.get("unscreened", []),
                "error": self._errors.get(run_id), "started_at": first and first.created_at}

    def answer_unscreened(self, run_id: str, proceed: bool) -> None:
        """Resume a run paused over unscreened postings in the background: continue with them
        (`proceed`) or abort. Raises `RunStateError` without that question pending,
        `RunBusyError` while another run computes."""
        self._require(run_id, "awaiting_answer")
        self._compute(run_id, lambda: self._graph.invoke(
            Command(resume=proceed), run_config(run_id), context=self._context()))

    def score(self, posting_id: str) -> Score:
        """Score one posting now, in the caller's thread, and return the stored score
        (`triage.graph.score_one`). It holds the same slot as a pass: raises `RunBusyError`
        while a pass or another single score computes, and frees the slot on every outcome;
        `ScoreRefused`, `KeyError`, `ScoringFailed` and storage errors reach the caller
        unchanged."""
        run_id = f"score:{posting_id}"
        self._claim(run_id)
        try:
            return score_one(self._context(), posting_id)
        finally:
            self._release(run_id)

    def _claim(self, run_id: str) -> None:
        with self._lock:
            if self._computing:
                raise RunBusyError(next(iter(self._computing)))
            self._computing.add(run_id)

    def _release(self, run_id: str) -> None:
        with self._lock:
            self._computing.discard(run_id)

    def _compute(self, run_id: str, step: Callable[[], object]) -> None:
        self._claim(run_id)
        self._errors.pop(run_id, None)
        self._executor.submit(self._run, run_id, step)

    def _run(self, run_id: str, step: Callable[[], object]) -> None:
        try:
            step()
        except Exception as error:  # reported through read(), the thread must not die silently
            self._errors[run_id] = f"{type(error).__name__}: {error}"
        finally:
            self._release(run_id)

    def _require(self, run_id: str, *allowed: str) -> str:
        run = self.read(run_id)
        if run is None:
            raise KeyError(run_id)
        if run["status"] not in allowed:
            raise RunStateError(f"run {run_id} is {run['status']}, not {' or '.join(allowed)}")
        return run["status"]

    @staticmethod
    def _status(snapshot, computing: bool) -> str:
        if computing:
            return "running"
        if snapshot.interrupts:
            return "awaiting_answer"
        if not snapshot.next:
            return "aborted" if snapshot.values.get("aborted") else "done"
        return "failed"
