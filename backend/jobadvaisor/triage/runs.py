"""The pass lifecycle the API drives (`design.md` → A pass is the triage graph without its
rating pause): passes compute in a background thread, one at a time; a pass paused over
unscreened postings does not block a new one. A single score (`Runs.score`) runs in the
caller's thread but takes the same one slot."""

import copy
import dataclasses
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
    """Starts, reads, cancels and resumes passes. `context` builds a fresh `TriageContext` for
    every invocation, so each step sees the data repository as it is on disk; `Runs` sets its
    `progress` and `cancelled` hooks on it. Progress and cancel requests live in memory only,
    beside the checkpoint, so a restart forgets them (ADR 0013). Every graph call runs with
    `durability="sync"`, so a step's checkpoint is on disk before the next node starts; with
    the default `"async"` a read in the write window (or a restart in it) shows no next node
    and `_status` would say `done` for a pass that stored nothing."""

    def __init__(self, graph: CompiledStateGraph, context: Callable[[], TriageContext]):
        self._graph, self._context = graph, context
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._lock = threading.Lock()
        self._computing: set[str] = set()
        self._cancelled: set[str] = set()
        self._progress: dict[str, dict] = {}
        self._errors: dict[str, str] = {}

    def start(self, rescore: bool = False) -> str:
        """Start a pass in the background and return its ID at once; `rescore` as in
        `start_run` (true for the pass variant `"all"`). Raises `RunBusyError` while another
        pass or a single score computes."""
        run_id = uuid.uuid4().hex
        self._compute(run_id, lambda: start_run(self._graph, self._hooked(run_id), run_id,
                                                rescore))
        return run_id

    def read(self, run_id: str) -> dict | None:
        """The run's status, result and unscreened postings, or `None` for an unknown run.

        `status` is `running`, `awaiting_answer` (the unscreened question), `done`, `aborted`,
        `cancelled` (the user stopped it; scores computed until then are stored) or `failed`
        (with `error` when this process saw it fail; also a pass the restart ended, an old
        one stopped before the removed node `extract` included). `started_at` is the ISO time of the
        run's first checkpoint, `None` before it has one. `progress` is the last report of this
        process as a copy (`TriageContext.progress`), `None` when it holds none: before the
        first report or after a restart. `cancel_requested` is true while the run still
        computes after a cancel.
        """
        config = run_config(run_id)
        with self._lock:  # a run ending between the two reads would be judged by a stale snapshot
            computing = run_id in self._computing
            snapshot = self._graph.get_state(config)
            progress = copy.deepcopy(self._progress.get(run_id))
            requested = computing and run_id in self._cancelled
        values = snapshot.values
        if not values and not computing:
            if run_id in self._errors:  # it failed before its first checkpoint
                return {"run_id": run_id, "status": "failed", "results": {}, "unscreened": [],
                        "error": self._errors[run_id], "started_at": None, "progress": None,
                        "cancel_requested": False}
            return None
        first = next(iter(reversed(list(self._graph.get_state_history(config)))), None)
        return {"run_id": run_id, "status": self._status(snapshot, computing),
                "results": values.get("results", {}), "unscreened": values.get("unscreened", []),
                "error": self._errors.get(run_id), "started_at": first and first.created_at,
                "progress": progress, "cancel_requested": requested}

    def cancel(self, run_id: str) -> None:
        """Ask the computing pass `run_id` to stop after the posting it works on; returns at
        once. It ends `cancelled` with the scores computed until then stored, except that a
        cancel arriving after the last posting of `score`, or while storing, ends a complete
        pass. Raises `KeyError` for an ID that is no pass (a single score `score:<id>`, or one
        no checkpoint knows) and `RunStateError` unless the run computes (it waits for the
        unscreened answer or has ended, also when it did so before a restart)."""
        if run_id.startswith("score:"):
            raise KeyError(run_id)
        with self._lock:  # check and add in one section, so the end of a step cannot slip between
            if run_id in self._computing:
                self._cancelled.add(run_id)
                return
            snapshot = self._graph.get_state(run_config(run_id))
            if not snapshot.values and run_id not in self._errors:
                raise KeyError(run_id)
            status = self._status(snapshot, False) if snapshot.values else "failed"
        raise RunStateError(f"run {run_id} is {status}, not running")

    def answer_unscreened(self, run_id: str, proceed: bool) -> None:
        """Resume a run paused over unscreened postings in the background: continue with them
        (`proceed`) or abort. Raises `RunStateError` without that question pending,
        `RunBusyError` while another run computes."""
        self._require(run_id, "awaiting_answer")
        self._compute(run_id, lambda: self._graph.invoke(
            Command(resume=proceed), run_config(run_id), context=self._hooked(run_id),
            durability="sync"))

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
        """Take the one slot for `run_id` and drop a cancel request of an earlier step in the
        same lock section, so a `cancel` arriving once the slot is taken is never lost. Raises
        `RunBusyError` while another run computes."""
        with self._lock:
            if self._computing:
                raise RunBusyError(next(iter(self._computing)))
            self._computing.add(run_id)
            self._cancelled.discard(run_id)

    def _release(self, run_id: str) -> None:
        with self._lock:
            self._computing.discard(run_id)

    def _hooked(self, run_id: str) -> TriageContext:
        """A fresh context whose `progress` stores the report as a copy under the lock and
        whose `cancelled` asks whether `run_id` has a cancel pending."""
        def report(progress: dict) -> None:
            with self._lock:
                self._progress[run_id] = copy.deepcopy(progress)

        def requested() -> bool:
            with self._lock:
                return run_id in self._cancelled

        return dataclasses.replace(self._context(), progress=report, cancelled=requested)

    def _compute(self, run_id: str, step: Callable[[], object]) -> None:
        self._claim(run_id)
        self._errors.pop(run_id, None)
        self._executor.submit(self._run, run_id, step)

    def _run(self, run_id: str, step: Callable[[], object], resumed: bool = False) -> None:
        """Run one step, then end it in one lock section: read the snapshot and either free
        the slot and drop a pending cancel, or, when the step paused at the unscreened question
        while a cancel is pending, keep the slot and resume the run with `"cancel"` so it ends
        `cancelled`. That resume (`resumed`) is tried once: if it fails, the slot is freed and
        `_errors` keeps the reason. A cancel racing this section is seen here, or finds the
        slot free and gets its `RunStateError`; none is lost."""
        resume = False
        try:
            step()
        except Exception as error:  # reported through read(), the thread must not die silently
            self._errors[run_id] = f"{type(error).__name__}: {error}"
        with self._lock:
            try:
                paused = bool(self._graph.get_state(run_config(run_id)).interrupts)
                resume = paused and run_id in self._cancelled and not resumed
            except Exception as error:  # the snapshot is unreadable: end the step as failed
                self._errors[run_id] = f"{type(error).__name__}: {error}"
            if not resume:
                self._computing.discard(run_id)
                self._cancelled.discard(run_id)
        if resume:
            self._run(run_id, lambda: self._graph.invoke(
                Command(resume="cancel"), run_config(run_id), context=self._hooked(run_id),
                durability="sync"), resumed=True)

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
            if snapshot.values.get("cancelled"):
                return "cancelled"
            if snapshot.values.get("aborted"):
                return "aborted"
            # A checkpoint from before the node `extract` left has no next node here, though
            # its pass never scored: a posting still pending or extracted means it ended early.
            results = snapshot.values.get("results", {}).values()
            unfinished = any(r["status"] in ("pending", "extracted") for r in results)
            return "failed" if unfinished else "done"
        return "failed"
