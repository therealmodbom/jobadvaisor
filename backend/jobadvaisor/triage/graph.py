"""The scoring pass over one batch (`design.md` → A pass is the triage graph without its rating
pause): load → exclude → [confirm_unscreened] → extract → score → store_scores, one thread per
run, checkpointed in SQLite.

The state holds plain JSON values only, so the checkpoint stays readable after a restart. The
models, the data repository, the content guard and the index are the runtime context, built by
the caller for every invocation and never checkpointed.
"""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from jobadvaisor.data.loader import DataRepository
from jobadvaisor.data.loader import load as load_repository
from jobadvaisor.data.models import PoolPass, Score
from jobadvaisor.data.writer import append_pass, read_pool, read_scores, write_score
from jobadvaisor.index import LabelIndex, state_path
from jobadvaisor.pool import _blocked, counter, pass_batch
from jobadvaisor.settings import Settings
from jobadvaisor.tools.exclusions import check_exclusions
from jobadvaisor.tools.extraction import extract_features, feature_set
from jobadvaisor.tools.guard import ContentGuard, screened_text
from jobadvaisor.tools.scoring import Score as Judgement
from jobadvaisor.tools.scoring import score_posting
from jobadvaisor.tools.similar import find_similar_labeled


class TriageState(TypedDict, total=False):
    """A pass's checkpointed state.

    Input: `rescore` (see `load`) and `started_at`, the pass's start as an ISO string
    (UTC), set by `start_run`. `results` maps every posting of the batch to its
    outcome: `{"status": "excluded", "rules": [...]}`,
    `{"status": "excluded", "reason": "content guard", "categories": [...]}`,
    `{"status": "unscreened"}` while the user is asked, `{"status": "scored", "features",
    "score", "reasoning", "example_ids"}` or `{"status": "failed", "error"}`. `unscreened`
    lists the postings the user is asked about; `aborted` is true when the user aborted.
    `cancelled` is set (true) by the node that sees the user's cancel and by
    `confirm_unscreened` on the answer `"cancel"`; absent otherwise. `extract_failed` counts
    the postings whose feature reading failed, so a later node can tell them from scoring
    failures. A key not declared here is silently dropped by LangGraph.
    """

    rescore: bool
    started_at: str
    batch: list[str]
    results: dict[str, dict]
    unscreened: list[str]
    aborted: bool
    cancelled: bool
    extract_failed: int


def _no_progress(progress: dict) -> None:
    """The default `progress` hook: reports nothing."""


def _never_cancelled() -> bool:
    """The default `cancelled` hook: the user never asks to stop."""
    return False


@dataclass(frozen=True)
class TriageContext:
    """What the nodes work with: the freshly loaded data repository, the content guard, the
    label index and the `extractor` and `judge` chat models, plus two runtime hooks.

    `progress` gets the pass's progress after every posting and at every phase start, as
    `{"phase": "checking" | "extracting" | "scoring" | "storing", "extract": {"done", "total"}
    | None, "score": {"done", "total"} | None}`; the counts are `None` while checking. It runs
    on the pass's thread. `cancelled` answers whether the user asked to stop; the nodes ask it
    before every posting. The defaults report nothing and never cancel.
    """

    repository: DataRepository
    guard: ContentGuard
    index: LabelIndex
    extractor: BaseChatModel
    judge: BaseChatModel
    progress: Callable[[dict], None] = _no_progress
    cancelled: Callable[[], bool] = _never_cancelled


def checkpoint_path(settings: Settings, data_repository: Path) -> Path:
    """The SQLite checkpoint DB of a data repository, next to its vector index."""
    return state_path(settings, data_repository) / "checkpoints.sqlite"


def checkpointer(path: Path) -> SqliteSaver:
    """A SQLite checkpointer on the file at `path`, creating its directory; the one place the
    later Postgres adapter replaces. The connection may be used from other threads."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))


def run_config(run_id: str) -> RunnableConfig:
    """The graph config of a run: its ID is the thread ID."""
    return {"configurable": {"thread_id": run_id}}


def build_graph(saver: BaseCheckpointSaver) -> CompiledStateGraph:
    """The compiled triage graph, checkpointed by `saver`. Invoke it with a `TriageContext` as
    `context` and `run_config(run_id)`; resume a pause with `Command(resume=...)`."""
    graph = StateGraph(TriageState, context_schema=TriageContext)
    for node in (load, exclude, confirm_unscreened, extract, score, store_scores):
        graph.add_node(node.__name__, node)
    graph.add_edge(START, "load")
    graph.add_edge("load", "exclude")
    graph.add_conditional_edges("exclude", _after_exclude,
                                ["confirm_unscreened", "extract", END])
    graph.add_conditional_edges("confirm_unscreened", _after_confirm, ["extract", END])
    graph.add_edge("extract", "score")
    graph.add_edge("score", "store_scores")
    graph.add_edge("store_scores", END)
    return graph.compile(checkpointer=saver)


def start_run(graph: CompiledStateGraph, context: TriageContext, run_id: str,
              rescore: bool = False, batch: list[str] | None = None) -> dict:
    """Run a new pass until it pauses or ends and return its state. `rescore` makes `load`
    take every posting, scored and rated ones included; the caller sets it for variant `"all"`.
    `batch`, when given, is the exact list of posting IDs
    to take instead (the eval's held-out postings). The pass's `started_at` is set here."""
    state: TriageState = {"rescore": rescore, "started_at": datetime.now(UTC).isoformat()}
    if batch is not None:
        state["batch"] = batch
    return graph.invoke(state, run_config(run_id), context=context)


class ScoreRefused(Exception):
    """`score_one` refused a posting no pass would score. `reason` is `held` (flagged by the
    content guard, not released), `excluded` (an exclusion rule matches) or `unscreened` (no
    guard result and no classifier to make one); `detail` the categories or rule IDs, empty
    for `unscreened`."""

    def __init__(self, reason: str, detail: list[str]):
        self.reason, self.detail = reason, detail
        super().__init__(reason)


class ScoringFailed(Exception):
    """A model or service `score_one` called failed: the judge, the label index or the
    content-guard classifier. The message names the cause's type and text, `__cause__` is
    the original error. Trying again may help; a failure to store the guard result or the
    score is not this."""


def score_one(context: TriageContext, posting_id: str) -> Score:
    """Score one posting now and store `scores/<id>.json`, replacing an earlier score; returns
    the stored `Score`. For any posting, rated or not, that a pass would let through: held and
    excluded postings (held first, as in the pool) and unscreened ones without a classifier
    raise `ScoreRefused`; an unchecked posting is checked now when a classifier is configured.
    No extraction, and nothing is appended to `pool.json`. No locking: the caller keeps it off
    a running pass (`Runs.score`). Raises `KeyError` for an unknown posting, `ScoringFailed`
    when the classifier, the index or the judge fails; an error storing the guard result or
    the score propagates unchanged."""
    repository = context.repository
    posting = repository.postings[posting_id]
    if blocked := _blocked(repository, posting):
        raise ScoreRefused(*blocked)
    if posting.guard is None and context.guard.classifier is not None:
        try:
            guard = context.guard.screen(screened_text(posting))
        except Exception as error:  # the classifier is an outside service
            raise ScoringFailed(f"{type(error).__name__}: {error}") from error
        context.guard.store(repository, posting_id, guard)  # a storage error is no retry case
    if ruling := _guard_ruling(context, posting_id):
        if ruling["status"] == "unscreened":
            raise ScoreRefused("unscreened", [])
        raise ScoreRefused("held", ruling["categories"])
    try:
        context.index.sync(repository)
        judged = _judge(context, posting_id)
    except Exception as error:  # the embedder and the judge are outside services
        raise ScoringFailed(f"{type(error).__name__}: {error}") from error
    stored = Score(schema_version="1", score=judged.score, reasoning=judged.reasoning,
                   example_ids=judged.example_ids, scored_at=datetime.now(UTC))
    write_score(repository.root, posting_id, stored)
    return stored


def load(state: TriageState, runtime: Runtime[TriageContext]) -> dict:
    """The batch, in posting-ID order: the caller's explicit `batch`, else `pool.pass_batch`
    (the same function the pool preview uses): every posting without a score, rated or not, or
    every posting when rescoring. An unreadable score file counts as unscored. Reports the
    phase `checking`."""
    _report(runtime.context, "checking")
    if "batch" in state:
        return {"batch": sorted(state["batch"])}
    repository = runtime.context.repository
    scores, _ = read_scores(repository.root)
    return {"batch": pass_batch(repository, scores, state.get("rescore", False))}


def exclude(state: TriageState, runtime: Runtime[TriageContext]) -> dict:
    """Apply the exclusion rules, then the content guard to the rest: a flagged, unreleased
    posting is excluded; an unscreened one is screened now (result stored) when a classifier
    is configured, else marked `unscreened` for the user to decide. Reports the phase
    `checking`. Asks `cancelled()` before every posting; on a cancel it stops and returns the
    results so far with `cancelled: True` (the postings it did not reach are left out)."""
    context = runtime.context
    repository = context.repository
    _report(context, "checking")
    results, unscreened = {}, []
    for posting_id in state["batch"]:
        if context.cancelled():
            return {"results": results, "unscreened": unscreened, "cancelled": True}
        posting = repository.postings[posting_id]
        if rules := check_exclusions(posting, repository.policy_pack.exclusion_rules):
            results[posting_id] = {"status": "excluded", "rules": rules}
            continue
        results[posting_id] = _guard_ruling(runtime.context, posting_id) or {"status": "pending"}
        if results[posting_id]["status"] == "unscreened":
            unscreened.append(posting_id)
    return {"results": results, "unscreened": unscreened}


def confirm_unscreened(state: TriageState, runtime: Runtime[TriageContext]) -> dict:
    """Pause and ask whether to continue with the unscreened postings; resumed with `True`
    (continue), `False` (abort) or `"cancel"` (the user cancelled the pass while it was on its
    way here; ends it as cancelled). The answer is not stored anywhere else."""
    proceed = interrupt({"question": "unscreened", "postings": state["unscreened"]})
    if proceed == "cancel":
        return {"cancelled": True}
    if not proceed:
        return {"aborted": True}
    return {"aborted": False, "results": state["results"] | {
        posting_id: {"status": "pending"} for posting_id in state["unscreened"]}}


def extract(state: TriageState, runtime: Runtime[TriageContext]) -> dict:
    """Extract the feature set from every pending posting; a failed call fails that posting
    only. The guard rules again first on the posting as stored now, since a paused run may
    resume after it was flagged or screening was turned on; an unscreened posting passes only
    when the user continued with it.

    Reports `extracting` after every posting (`design.md` → The progress shape): a ruling
    removes the posting from both counts, a failed reading counts as done and removes it from
    the scoring count. Asks `cancelled()` before every posting; on a cancel it returns the
    results so far with `cancelled: True`. `extract_failed` in the return counts the failed
    readings."""
    context = runtime.context
    features = feature_set(context.repository.policy_pack.feature_set)
    results = dict(state["results"])
    continued = set(state.get("unscreened", []))
    pending = _with_status(results, "pending")
    total, done, failed = len(pending), 0, 0

    def report() -> None:
        _report(context, "extracting", (done, total), (0, total - failed))

    report()
    for posting_id in pending:
        if context.cancelled():
            return {"results": results, "extract_failed": failed, "cancelled": True}
        try:
            ruling = _guard_ruling(context, posting_id)
            if ruling and not (ruling["status"] == "unscreened" and posting_id in continued):
                results[posting_id] = ruling
                total -= 1
                report()
                continue
            posting = context.repository.postings[posting_id]
            extracted = extract_features(posting, features, context.extractor,
                                         context.repository.company_of(posting))
        except Exception as error:  # one bad answer must not end the run
            results[posting_id] = {"status": "failed", "error": str(error)}
            failed += 1
        else:
            results[posting_id] = {"status": "extracted", "features": extracted}
        done += 1
        report()
    return {"results": results, "extract_failed": failed}


def score(state: TriageState, runtime: Runtime[TriageContext]) -> dict:
    """Score every extracted posting with its most similar labeled postings as examples,
    after syncing the index with the repository's labels. Reports `scoring` after every
    posting, a failed one included. Asks `cancelled()` before every posting; on a cancel it
    returns the results so far with `cancelled: True`. A state that is already cancelled
    skips the sync and the loop."""
    context = runtime.context
    if state.get("cancelled"):
        return {}
    results = dict(state["results"])
    queue = _with_status(results, "extracted")
    read = len(queue) + state.get("extract_failed", 0)
    done = 0
    _report(context, "scoring", (read, read), (done, len(queue)))
    context.index.sync(context.repository)
    for posting_id in queue:
        if context.cancelled():
            return {"results": results, "cancelled": True}
        try:
            scored = _judge(context, posting_id)
        except Exception as error:  # one bad answer must not end the run
            results[posting_id] = {"status": "failed", "error": str(error)}
        else:
            results[posting_id] = {"status": "scored",
                                   "features": results[posting_id]["features"],
                                   "score": scored.score, "reasoning": scored.reasoning,
                                   "example_ids": scored.example_ids}
        done += 1
        _report(context, "scoring", (read, read), (done, len(queue)))
    return {"results": results}


def store_scores(state: TriageState, runtime: Runtime[TriageContext]) -> dict:
    """Write `scores/<id>.json` for every scored posting, rated or not (replacing an earlier
    score), then append this pass to `pool.json` when it scored anything. The scores are written
    first so a broken file found afterwards cannot discard paid work. The pass's quality
    measure is the correction counter against the pool and the scores from before this pass,
    read before writing, since the pass may have rescored rated postings. The entry's `variant`
    is `"all"` for a pass with `rescore`, else `"unscored"`; `cancelled` is true when the state
    says the user cancelled. Score times and `finished_at` are one instant. Reports `storing`
    with the final counts, only when something is stored, and never asks `cancelled()`: a cancel
    that arrives from here on ends a complete pass."""
    root = runtime.context.repository.root
    now = datetime.now(UTC)
    scored = _with_status(state["results"], "scored")
    if not scored:
        return {}
    _report_storing(runtime.context, state)
    before, _ = read_scores(root)
    for posting_id in scored:
        result = state["results"][posting_id]
        write_score(root, posting_id, Score(schema_version="1", score=result["score"],
                                            reasoning=result["reasoning"],
                                            example_ids=result["example_ids"], scored_at=now))
    measured = counter(load_repository(root), before, read_pool(root))
    started = datetime.fromisoformat(state.get("started_at", now.isoformat()))
    append_pass(root, PoolPass(started_at=started, finished_at=now, scored=len(scored),
                               corrections=measured["corrections"], rated=measured["rated"],
                               rate=measured["rate"],
                               variant="all" if state.get("rescore") else "unscored",
                               cancelled=True if state.get("cancelled") else None))
    return {}


def _report(context: TriageContext, phase: str, extract: tuple[int, int] | None = None,
            score: tuple[int, int] | None = None) -> None:
    """Hand the pass's progress to `context.progress`; the counts are `(done, total)`, `None`
    while checking."""
    def counts(pair):
        return None if pair is None else {"done": pair[0], "total": pair[1]}

    context.progress({"phase": phase, "extract": counts(extract), "score": counts(score)})


def _report_storing(context: TriageContext, state: TriageState) -> None:
    """Report `storing` with the counts as the nodes before it left them, derived from the
    results: a posting read is `scored`, `failed` or `extracted` (still to score after a
    cancel), one still `pending` was not reached; `extract_failed` of the failures were
    readings."""
    results = state["results"].values()
    count = {status: sum(r["status"] == status for r in results)
             for status in ("scored", "failed", "extracted", "pending")}
    read_failed = state.get("extract_failed", 0)
    read_done = count["scored"] + count["failed"] + count["extracted"]
    read_total = read_done + count["pending"]
    _report(context, "storing", (read_done, read_total),
            (count["scored"] + count["failed"] - read_failed, read_total - read_failed))


def _judge(context: TriageContext, posting_id: str) -> Judgement:
    """The judge's verdict on one posting, shown its most similar labeled postings (never the
    posting itself). The index must be synced already. Raises what the example search or the
    judge raises."""
    repository = context.repository
    posting = repository.postings[posting_id]
    examples = find_similar_labeled(context.guard, context.index, repository, posting,
                                    posting_id=posting_id)
    return score_posting(posting, repository.profile, repository.policy_pack, examples,
                         context.judge)


def _guard_ruling(context: TriageContext, posting_id: str) -> dict | None:
    """The content guard's result for a stored posting: excluded when flagged and not released,
    `unscreened` when it carries no guard, `None` when a model may see it. An unscreened
    posting is screened now, and the result stored, when a classifier is configured."""
    repository = context.repository
    if repository.postings[posting_id].guard is None and context.guard.classifier is not None:
        context.guard.posting(repository, posting_id)
    guard = repository.postings[posting_id].guard
    if guard is None:
        return {"status": "unscreened"}
    if guard.flagged and guard.released_at is None:
        return {"status": "excluded", "reason": "content guard", "categories": guard.categories}
    return None


def _after_exclude(state: TriageState) -> str:
    if state.get("cancelled"):
        return END
    return "confirm_unscreened" if state["unscreened"] else "extract"


def _after_confirm(state: TriageState) -> str:
    return END if state.get("cancelled") or state.get("aborted") else "extract"


def _with_status(results: dict[str, dict], status: str) -> list[str]:
    return [posting_id for posting_id, result in results.items() if result["status"] == status]
