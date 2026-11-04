"""Graph-versus-agent eval (spec `match-evaluation` → Graph versus agent): triage of the held-out
postings by the fixed triage graph and by a free agent with the same tools, each repeated, with
precision@k, the router's cost per posting and the variance of precision@k over the repetitions.

Each repetition works on a copy of the data repository that holds only the labels before the
cut-off and the held-out postings without their labels, so the held-out postings are the run's
batch and no later label can serve as an example.
"""

import shutil
import statistics
import tempfile
from collections.abc import Callable
from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field

from jobadvaisor.agent import AgentContext, agent_tools, tool_errors
from jobadvaisor.data.loader import DataRepository, load
from jobadvaisor.evals.cost import metered
from jobadvaisor.evals.scoring import TimeSplit, precision_at_k, time_split
from jobadvaisor.index import LabelIndex, PostingIndex
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.tools.prompts import DATA_RULE
from jobadvaisor.triage.graph import TriageContext, build_graph, start_run

MAX_AGENT_MODEL_CALLS = 40
TRIAGE_INSTRUCTIONS = (
    "Triage the user's new job postings with your tools. For every posting in the list, check "
    "its exclusions; score every posting no rule excludes with score_posting. Then report every "
    "posting in TriageReport: excluded true with no score, or excluded false with the score "
    "score_posting gave. " + " ".join(DATA_RULE.format(tag=tag)
                                     for tag in ("posting", "page", "results"))
)


class TriagedPosting(BaseModel):
    """One posting of the agent's triage report."""

    posting_id: str
    excluded: bool
    score: int | None = Field(None, ge=0, le=10, description="0-10, absent when excluded")


class TriageReport(BaseModel):
    """The agent's triage of the whole batch."""

    postings: list[TriagedPosting]


def triage_copy(repository: DataRepository, split: TimeSplit, directory: Path) -> Path:
    """A copy of `repository` at `directory` with only the postings of `split`, the training
    labels and the held-out postings unlabeled, and no score files, since the agent's tools
    would show it the stored scores of the postings it is to score; returns its root."""
    root = Path(shutil.copytree(repository.root, directory))
    shutil.rmtree(root / "scores", ignore_errors=True)
    keep = set(split.training) | set(split.held_out)
    for path in (root / "postings").glob("*.json"):
        if path.stem not in keep:
            path.unlink()
    for path in (root / "labels").glob("*.json"):
        if path.stem not in split.training:
            path.unlink()
    return root


def graph_variant(root: Path, guard: ContentGuard, index: LabelIndex, extractor: BaseChatModel,
                  judge: BaseChatModel, batch: list[str]) -> dict[str, dict]:
    """The triage graph's result for every posting of `batch`, as the run reports it
    (`missing` for one the run left out), from one run over the copy at `root`."""
    state = start_run(build_graph(InMemorySaver()),
                      TriageContext(load(root), guard, index, extractor, judge), "eval",
                      rescore_unrated=True)
    return {posting_id: state["results"].get(posting_id, {"status": "missing"})
            for posting_id in batch}


def agent_variant(root: Path, guard: ContentGuard, indexes: tuple[LabelIndex, PostingIndex],
                  extractor: BaseChatModel, judge: BaseChatModel, model: BaseChatModel,
                  batch: list[str]) -> dict[str, dict]:
    """The agent's triage of `batch` with the conversational agent's tools, in at most
    `MAX_AGENT_MODEL_CALLS` model calls: `excluded`, `scored` with its reported score, or
    `missing` for a posting its report leaves out or gives no score."""
    context = AgentContext(load(root), guard, *indexes, extractor, judge)
    agent = create_agent(model, agent_tools(context), system_prompt=TRIAGE_INSTRUCTIONS,
                         response_format=ToolStrategy(TriageReport),
                         middleware=[ModelCallLimitMiddleware(run_limit=MAX_AGENT_MODEL_CALLS,
                                                              exit_behavior="end"),
                                     tool_errors])
    report = agent.invoke({"messages": [HumanMessage(
        "New postings to triage: " + ", ".join(batch))]}).get("structured_response")
    found = {}
    for entry in report.postings if report else []:
        if entry.excluded:
            found[entry.posting_id] = {"status": "excluded"}
        elif entry.score is not None:
            found[entry.posting_id] = {"status": "scored", "score": entry.score}
    return {posting_id: found.get(posting_id, {"status": "missing"}) for posting_id in batch}


def ranked(results: dict[str, dict]) -> list[str]:
    """Posting IDs by score, highest first (ties by ID), then every unscored posting by ID."""
    scored = sorted((-result["score"], posting_id) for posting_id, result in results.items()
                    if result["status"] == "scored")
    rest = sorted(posting_id for posting_id, result in results.items()
                  if result["status"] != "scored")
    return [posting_id for _, posting_id in scored] + rest


def run(repository: DataRepository, guard: ContentGuard,
        indexes_for: Callable[[Path], tuple[LabelIndex, PostingIndex]],
        extractor: BaseChatModel, judge: BaseChatModel, agent_model: BaseChatModel,
        k: int = 5, held_out: int = 15, repetitions: int = 3) -> dict:
    """Triage the `held_out` latest labeled postings `repetitions` times with each variant and
    report, per variant, precision@k per repetition, its mean and variance, the mean cost per
    posting and every posting left unscored. `indexes_for(root)` gives the label and posting
    indexes for a copy; copies hold the same data, so one directory serves all of them."""
    report = {"eval": "graph_vs_agent",
              "metric": "precision@k, cost per posting and variance over repetitions",
              "data": repository.root.name}
    usable = sum(label.verdict is not None for label in repository.labels.values())
    if usable <= held_out:
        return report | {"skipped": f"{usable} usable labels, need more than the {held_out} "
                                    "held out"}
    split = time_split(repository, held_out)
    batch = split.held_out
    variants = {
        "graph": lambda root, indexes: graph_variant(root, guard, indexes[0], extractor, judge,
                                                     batch),
        "agent": lambda root, indexes: agent_variant(root, guard, indexes, extractor, judge,
                                                     agent_model, batch)}
    rows = {name: {"precision_at_k": [], "costs": [], "uncosted_calls": 0, "errors": []}
            for name in variants}
    with tempfile.TemporaryDirectory() as directory:
        for repetition in range(repetitions):
            for name, variant in variants.items():
                row = rows[name]
                root = triage_copy(repository, split, Path(directory) / f"{name}-{repetition}")
                with metered() as meter:
                    try:
                        results = variant(root, indexes_for(root))
                    except Exception as error:  # one failed repetition must not end the eval
                        row["errors"].append({"repetition": repetition,
                                              "error": f"{type(error).__name__}: {error}"})
                        continue
                row["costs"].append(meter.cost / len(batch))
                row["uncosted_calls"] += meter.uncosted
                row["errors"] += [{"repetition": repetition, "posting": posting_id,
                                   "status": result["status"]}
                                  for posting_id, result in results.items()
                                  if result["status"] in ("missing", "failed")]
                row["precision_at_k"].append(precision_at_k(
                    [repository.labels[posting_id].verdict for posting_id in ranked(results)], k))
    verdicts = [repository.labels[posting_id].verdict for posting_id in batch]
    return report | {
        "k": k, "held_out": len(batch), "cut_off": split.cut_off.isoformat(),
        "repetitions": repetitions, "base_rate": verdicts.count("positive") / len(verdicts),
        "variants": {name: {
            "precision_at_k": row["precision_at_k"],
            "mean": statistics.fmean(row["precision_at_k"]) if row["precision_at_k"] else None,
            "variance": statistics.pvariance(row["precision_at_k"])
            if row["precision_at_k"] else None,
            "cost_per_posting_usd": statistics.fmean(row["costs"]) if row["costs"] else None,
            "uncosted_calls": row["uncosted_calls"], "errors": row["errors"]}
            for name, row in rows.items()},
    }
