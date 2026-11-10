"""The scoring pass over one batch (`design.md` → A pass is the triage graph without its rating
pause): load → exclude → [confirm_unscreened] → extract → score → store_scores, one thread per
run, checkpointed in SQLite.

The state holds plain JSON values only, so the checkpoint stays readable after a restart. The
models, the data repository, the content guard and the index are the runtime context, built by
the caller for every invocation and never checkpointed.
"""

import sqlite3
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
from jobadvaisor.pool import counter, pass_batch
from jobadvaisor.settings import Settings
from jobadvaisor.tools.exclusions import check_exclusions
from jobadvaisor.tools.extraction import extract_features, feature_set
from jobadvaisor.tools.guard import ContentGuard
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
    """

    rescore: bool
    started_at: str
    batch: list[str]
    results: dict[str, dict]
    unscreened: list[str]
    aborted: bool


@dataclass(frozen=True)
class TriageContext:
    """What the nodes work with: the freshly loaded data repository, the content guard, the
    label index and the `extractor` and `judge` chat models."""

    repository: DataRepository
    guard: ContentGuard
    index: LabelIndex
    extractor: BaseChatModel
    judge: BaseChatModel


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
    graph.add_conditional_edges("exclude", _after_exclude, ["confirm_unscreened", "extract"])
    graph.add_conditional_edges("confirm_unscreened", _after_confirm, ["extract", END])
    graph.add_edge("extract", "score")
    graph.add_edge("score", "store_scores")
    graph.add_edge("store_scores", END)
    return graph.compile(checkpointer=saver)


def start_run(graph: CompiledStateGraph, context: TriageContext, run_id: str,
              rescore: bool = False, batch: list[str] | None = None) -> dict:
    """Run a new pass until it pauses or ends and return its state. `rescore` makes `load`
    take every posting, scored and rated ones included; the caller sets it (when corrections
    were counted since the last pass). `batch`, when given, is the exact list of posting IDs
    to take instead (the eval's held-out postings). The pass's `started_at` is set here."""
    state: TriageState = {"rescore": rescore, "started_at": datetime.now(UTC).isoformat()}
    if batch is not None:
        state["batch"] = batch
    return graph.invoke(state, run_config(run_id), context=context)


def load(state: TriageState, runtime: Runtime[TriageContext]) -> dict:
    """The batch, in posting-ID order: the caller's explicit `batch`, else `pool.pass_batch`
    (the same function the pool preview uses): every posting without a score, rated or not, or
    every posting when rescoring. An unreadable score file counts as unscored."""
    if "batch" in state:
        return {"batch": sorted(state["batch"])}
    repository = runtime.context.repository
    scores, _ = read_scores(repository.root)
    return {"batch": pass_batch(repository, scores, state.get("rescore", False))}


def exclude(state: TriageState, runtime: Runtime[TriageContext]) -> dict:
    """Apply the exclusion rules, then the content guard to the rest: a flagged, unreleased
    posting is excluded; an unscreened one is screened now (result stored) when a classifier
    is configured, else marked `unscreened` for the user to decide."""
    repository = runtime.context.repository
    results, unscreened = {}, []
    for posting_id in state["batch"]:
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
    (continue) or `False` (abort). The answer is not stored anywhere else."""
    proceed = interrupt({"question": "unscreened", "postings": state["unscreened"]})
    if not proceed:
        return {"aborted": True}
    return {"aborted": False, "results": state["results"] | {
        posting_id: {"status": "pending"} for posting_id in state["unscreened"]}}


def extract(state: TriageState, runtime: Runtime[TriageContext]) -> dict:
    """Extract the feature set from every pending posting; a failed call fails that posting
    only. The guard rules again first on the posting as stored now, since a paused run may
    resume after it was flagged or screening was turned on; an unscreened posting passes only
    when the user continued with it."""
    context = runtime.context
    features = feature_set(context.repository.policy_pack.feature_set)
    results = dict(state["results"])
    continued = set(state.get("unscreened", []))
    for posting_id in _with_status(results, "pending"):
        try:
            ruling = _guard_ruling(context, posting_id)
            if ruling and not (ruling["status"] == "unscreened" and posting_id in continued):
                results[posting_id] = ruling
                continue
            posting = context.repository.postings[posting_id]
            extracted = extract_features(posting, features, context.extractor,
                                         context.repository.company_of(posting))
        except Exception as error:  # one bad answer must not end the run
            results[posting_id] = {"status": "failed", "error": str(error)}
        else:
            results[posting_id] = {"status": "extracted", "features": extracted}
    return {"results": results}


def score(state: TriageState, runtime: Runtime[TriageContext]) -> dict:
    """Score every extracted posting with its most similar labeled postings as examples,
    after syncing the index with the repository's labels."""
    context = runtime.context
    repository = context.repository
    context.index.sync(repository)
    results = dict(state["results"])
    for posting_id in _with_status(results, "extracted"):
        posting = repository.postings[posting_id]
        try:
            examples = find_similar_labeled(context.guard, context.index, repository, posting,
                                            posting_id=posting_id)
            scored = score_posting(posting, repository.profile, repository.policy_pack,
                                   examples, context.judge)
        except Exception as error:  # one bad answer must not end the run
            results[posting_id] = {"status": "failed", "error": str(error)}
        else:
            results[posting_id] = {"status": "scored",
                                   "features": results[posting_id]["features"],
                                   "score": scored.score, "reasoning": scored.reasoning,
                                   "example_ids": scored.example_ids}
    return {"results": results}


def store_scores(state: TriageState, runtime: Runtime[TriageContext]) -> dict:
    """Write `scores/<id>.json` for every scored posting, rated or not (replacing an earlier
    score), then append this pass to `pool.json` when it scored anything. The scores are written
    first so a broken file found afterwards cannot discard paid work. The pass's quality
    measure is the correction counter against the pool and the scores from before this pass,
    read before writing, since the pass may have rescored rated postings. Score times and
    `finished_at` are one instant."""
    root = runtime.context.repository.root
    now = datetime.now(UTC)
    scored = _with_status(state["results"], "scored")
    if not scored:
        return {}
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
                               rate=measured["rate"]))
    return {}


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
    return "confirm_unscreened" if state["unscreened"] else "extract"


def _after_confirm(state: TriageState) -> str:
    return END if state["aborted"] else "extract"


def _with_status(results: dict[str, dict], status: str) -> list[str]:
    return [posting_id for posting_id, result in results.items() if result["status"] == status]
