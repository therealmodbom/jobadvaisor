"""The graph-versus-agent eval, with fake models. Live runs go through
`python -m jobadvaisor.evals`."""

import json
import shutil
from pathlib import Path

from conftest import ScriptedModel, ToolScriptModel, unknown_features
from langchain_core.embeddings import DeterministicFakeEmbedding

from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import load
from jobadvaisor.data.writer import read_scores
from jobadvaisor.evals import __main__ as cli
from jobadvaisor.evals import graph_vs_agent
from jobadvaisor.evals.agent import seed_scores
from jobadvaisor.evals.scoring import time_split
from jobadvaisor.index import LabelIndex, PostingIndex
from jobadvaisor.settings import Settings
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.tools.prompts import posting_block

DEMO = load(FIXTURE_DIRECTORY)
GUARD = ContentGuard(None, {})  # every demo posting carries a clean stored guard
SPLIT = time_split(DEMO, 15)


def judge_knowing_verdicts():
    """Scores 9 for postings rated positive and 1 otherwise."""
    verdicts = {posting_block(posting): DEMO.labels[posting_id].verdict
                for posting_id, posting in DEMO.postings.items() if posting_id in DEMO.labels}
    return ScriptedModel(lambda schema, prompt: {
        "score": 9 if verdicts[prompt.rsplit("Posting to score:\n", 1)[1]] == "positive" else 1,
        "reasoning": "r"})


def agent_reporting(scores: dict[str, int], times: int = 3) -> ToolScriptModel:
    report = {"postings": [{"posting_id": posting_id, "excluded": False, "score": score}
                           for posting_id, score in scores.items()]}
    return ToolScriptModel(plan=[("TriageReport", report)] * times)


def index_factory(tmp_path):
    embedding = DeterministicFakeEmbedding(size=16)
    return lambda root: (LabelIndex(tmp_path / "chroma", embedding, "fake-16"),
                         PostingIndex(tmp_path / "chroma", embedding, "fake-16"))


def test_cli_skips_graph_vs_agent_without_models(monkeypatch, capsys):
    monkeypatch.setattr(cli, "Settings", lambda: Settings(_env_file=None))
    cli.main(["--only", "graph_vs_agent"])
    [report] = json.loads(capsys.readouterr().out)
    assert report["eval"] == "graph_vs_agent" and "is not set" in report["skipped"]


def test_triage_copy_keeps_training_labels_and_unlabels_the_held_out(tmp_path):
    root = graph_vs_agent.triage_copy(DEMO, SPLIT, tmp_path / "copy")
    copy = load(root)
    assert set(copy.labels) == set(SPLIT.training)
    assert set(copy.postings) == set(SPLIT.training) | set(SPLIT.held_out)


def test_triage_copy_drops_stored_scores_so_the_agent_cannot_read_them(tmp_path):
    source = Path(shutil.copytree(FIXTURE_DIRECTORY, tmp_path / "scored"))
    seed_scores(source)
    root = graph_vs_agent.triage_copy(load(source), SPLIT, tmp_path / "copy")
    assert read_scores(root) == ({}, {})


def test_report_shows_precision_cost_and_variance_for_both_variants(tmp_path):
    scores = {posting_id: 9 if DEMO.labels[posting_id].verdict == "positive" else 1
              for posting_id in SPLIT.held_out}
    report = graph_vs_agent.run(DEMO, GUARD, index_factory(tmp_path),
                                ScriptedModel(unknown_features), judge_knowing_verdicts(),
                                agent_reporting(scores), k=5, held_out=15, repetitions=3)
    assert (report["k"], report["held_out"], report["repetitions"]) == (5, 15, 3)
    for name in ("graph", "agent"):
        variant = report["variants"][name]
        assert variant["precision_at_k"] == [1.0, 1.0, 1.0], name
        assert variant["mean"] == 1.0 and variant["variance"] == 0.0
        assert "cost_per_posting_usd" in variant and variant["errors"] == []


def test_agent_variant_ranks_excluded_and_missing_postings_last(tmp_path):
    [first, second, *rest] = SPLIT.held_out
    model = ToolScriptModel(plan=[("TriageReport", {"postings": [
        {"posting_id": first, "excluded": True, "score": None},
        {"posting_id": second, "excluded": False, "score": 3}]})])
    root = graph_vs_agent.triage_copy(DEMO, SPLIT, tmp_path / "copy")
    results = graph_vs_agent.agent_variant(root, GUARD, index_factory(tmp_path)(root),
                                           ScriptedModel(unknown_features),
                                           judge_knowing_verdicts(), model, SPLIT.held_out)
    assert results[first] == {"status": "excluded"}
    assert results[second] == {"status": "scored", "score": 3}
    assert all(results[posting_id] == {"status": "missing"} for posting_id in rest)
    assert graph_vs_agent.ranked(results)[0] == second


def test_agent_variant_is_told_the_batch(tmp_path):
    model = ToolScriptModel(plan=[("TriageReport", {"postings": []})])
    root = graph_vs_agent.triage_copy(DEMO, SPLIT, tmp_path / "copy")
    graph_vs_agent.agent_variant(root, GUARD, index_factory(tmp_path)(root),
                                 ScriptedModel(unknown_features), judge_knowing_verdicts(),
                                 model, SPLIT.held_out)
    assert all(posting_id in model.seen_text() for posting_id in SPLIT.held_out)
    assert {"check_exclusions", "score_posting", "TriageReport"} <= set(model.tool_names)
