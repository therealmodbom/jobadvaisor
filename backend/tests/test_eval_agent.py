"""The agent eval's harness and the cost meter, with fake models. The eval itself makes real
calls and runs only through `python -m jobadvaisor.evals`."""

import json
from collections import Counter
from datetime import UTC, datetime

import pytest
from conftest import ToolScriptModel
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool

from jobadvaisor.data.loader import load
from jobadvaisor.data.models import Score
from jobadvaisor.data.writer import read_scores, write_score
from jobadvaisor.evals import __main__ as cli
from jobadvaisor.evals import agent as agent_eval
from jobadvaisor.evals.cost import metered
from jobadvaisor.index import LabelIndex, PostingIndex
from jobadvaisor.pool import best_open
from jobadvaisor.settings import Settings
from jobadvaisor.tools.guard import ContentGuard

GUARD = ContentGuard(None, {})  # every demo posting carries a clean stored guard


class PricedModel(BaseChatModel):
    """Answers "ok" and reports a cost of 0.25 per call, as the router does."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        message = AIMessage("ok", response_metadata={"token_usage": {"cost": 0.25}})
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def _llm_type(self) -> str:
        return "priced"


@pytest.fixture
def index(tmp_path, demo_copy) -> LabelIndex:
    built = LabelIndex(tmp_path / "chroma", DeterministicFakeEmbedding(size=16), "fake-16")
    built.sync(load(demo_copy))
    return built


@pytest.fixture
def postings(tmp_path, demo_copy) -> PostingIndex:
    built = PostingIndex(tmp_path / "chroma", DeterministicFakeEmbedding(size=16), "fake-16")
    built.sync(load(demo_copy))
    return built


@pytest.fixture
def cases(demo_copy, postings):
    agent_eval.seed_scores(demo_copy)
    return agent_eval.cases(load(demo_copy), postings, GUARD)


def by_kind(cases, kind):
    return [case for case in cases if case.kind == kind]


def test_fifteen_cases_cover_every_kind_on_the_demo_persona(cases):
    assert len(cases) == 15
    assert Counter(case.kind for case in cases) == {
        "exclusion": 4, "similar": 3, "company": 1, "relabel": 1, "status_change": 1,
        "rule_change": 1, "rescore": 1, "stored_score": 1, "apply_to": 1, "chip": 1}


def test_status_change_check_fails_when_the_posting_changed(cases, demo_copy):
    case = by_kind(cases, "status_change")[0]
    answer = agent_eval.Answer("Den Status setzt du in der Ansicht „Anzeigen“.", {}, demo_copy)
    assert case.check(answer)[0]
    assert not case.check(agent_eval.Answer("Ich habe die Anzeigen markiert.", {}, demo_copy))[0]
    path = demo_copy / "postings" / f"{case.expected[0]}.json"
    path.write_text(path.read_text().replace('"schema_version"', '"status": "applied", '
                                                                 '"schema_version"', 1))
    assert not case.check(answer)[0]


def test_seeding_keeps_stored_scores_and_fills_the_missing_ones(demo_copy):
    write_score(demo_copy, "demo-001", Score(schema_version="1", score=10, reasoning="kept",
                                             scored_at=datetime(2026, 10, 1, tzinfo=UTC)))
    agent_eval.seed_scores(demo_copy)
    scores, problems = read_scores(demo_copy)
    assert len(scores) == len(load(demo_copy).postings) and not problems
    assert scores["demo-001"].reasoning == "kept"
    assert len({score.score for score in scores.values()}) > 5


def test_apply_to_check_needs_the_top_open_postings_in_pool_order(cases, demo_copy):
    case = by_kind(cases, "apply_to")[0]
    repository = load(demo_copy)
    top = [row["posting_id"] for row in best_open(repository, *read_scores(demo_copy))][:3]
    assert case.expected == top
    assert case.check(agent_eval.Answer(" > ".join(top), {}, demo_copy))[0]
    assert not case.check(agent_eval.Answer(" > ".join(reversed(top)), {}, demo_copy))[0]
    assert not case.check(agent_eval.Answer(" > ".join(top[:2]), {}, demo_copy))[0]


def test_chip_check_needs_every_posting_marked_with_the_chip(cases, demo_copy):
    case = by_kind(cases, "chip")[0]
    marked = sorted(posting_id for posting_id, label in load(demo_copy).labels.items()
                    if "too-junior" in label.chips)
    assert case.expected == marked and "Stelle zu junior" in case.question
    assert case.check(agent_eval.Answer(", ".join(marked), {}, demo_copy))[0]
    assert not case.check(agent_eval.Answer(", ".join(marked[1:]), {}, demo_copy))[0]


def test_exclusion_check_needs_the_matched_rule(cases, demo_copy):
    case = by_kind(cases, "exclusion")[0]
    assert case.check(agent_eval.Answer("It matched rule no-on-call.", {}, demo_copy))[0]
    assert not case.check(agent_eval.Answer("It was excluded.", {}, demo_copy))[0]


def test_exclusion_by_title_names_no_posting_id(cases):
    case = by_kind(cases, "exclusion")[3]
    assert "demo-" not in case.question


def test_similar_check_needs_every_expected_posting(cases, demo_copy):
    case = by_kind(cases, "similar")[0]
    assert len(case.expected) == 5
    assert case.check(agent_eval.Answer(" ".join(case.expected), {}, demo_copy))[0]
    assert not case.check(agent_eval.Answer(" ".join(case.expected[:4]), {}, demo_copy))[0]


def test_company_check_needs_every_posting_of_the_company(cases, demo_copy):
    case = by_kind(cases, "company")[0]
    assert case.expected == ["demo-027", "demo-046", "demo-090", "demo-121", "demo-122",
                             "demo-139"]
    assert "Demo Co. Cedar" in case.question
    assert case.check(agent_eval.Answer(", ".join(case.expected), {}, demo_copy))[0]


def test_relabel_check_fails_when_a_label_changed(cases, demo_copy):
    case = by_kind(cases, "relabel")[0]
    answer = agent_eval.Answer("Bitte bewerte sie in der Ansicht „Anzeigen“.", {}, demo_copy)
    assert case.check(answer)[0]
    (demo_copy / "labels" / f"{case.expected[0]}.json").write_text("{}")
    assert not case.check(answer)[0]
    assert not by_kind(cases, "relabel")[0].check(
        agent_eval.Answer("Done, marked it.", {}, demo_copy))[0]


def test_rule_change_check_needs_the_policy_pack_unchanged(cases, demo_copy):
    case = by_kind(cases, "rule_change")[0]
    answer = agent_eval.Answer("Regeln stehen im Policy Pack; ändern kann ich sie nicht.", {},
                               demo_copy)
    assert case.check(answer)[0]
    (demo_copy / "policy-pack.json").write_text("{}")
    assert not case.check(answer)[0]


def test_rescore_check_needs_every_changed_posting(cases, demo_copy):
    case = by_kind(cases, "rescore")[0]
    outputs = {"rescore_postings": ['{"changed": [{"posting_id": "demo-002", "before": 0, '
                                    '"after": 8}], "unchanged": [], "failed": []}']}
    assert case.check(agent_eval.Answer("demo-002 went from 0 to 8.", outputs, demo_copy))[0]
    assert not case.check(agent_eval.Answer("Nothing changed.", outputs, demo_copy))[0]
    assert not case.check(agent_eval.Answer("demo-002 changed.", {}, demo_copy))[0]


def test_stored_score_check_needs_the_stored_score(cases, demo_copy):
    case = by_kind(cases, "stored_score")[0]
    stored = read_scores(demo_copy)[0][case.expected[0]].score
    outputs = {"find_postings": ["<results>...</results>"]}
    assert case.check(agent_eval.Answer(f"Score {stored}, weil ...", outputs, demo_copy))[0]
    assert not case.check(agent_eval.Answer(f"Score {stored + 1}.", outputs, demo_copy))[0]
    assert not case.check(agent_eval.Answer(f"Score {stored}.", {}, demo_copy))[0]


def test_run_reports_success_rate_and_cost(demo_copy, index, postings):
    model = ToolScriptModel()
    report = agent_eval.run(load(demo_copy), index, postings, GUARD, model, ToolScriptModel(),
                            ToolScriptModel(), "fake")
    assert report["questions"] == 15 and report["success_rate"] == 0.0
    assert not (demo_copy / "scores").exists()  # seeded on the eval's copy only
    assert {"cost_usd", "cost_per_question_usd", "cases"} <= set(report)
    assert all(not case["passed"] for case in report["cases"])


def test_cli_skips_the_agent_eval_without_models(monkeypatch, capsys):
    monkeypatch.setattr(cli, "Settings", lambda: Settings(_env_file=None))
    cli.main(["--only", "agent"])
    [report] = json.loads(capsys.readouterr().out)
    assert report["eval"] == "agent" and "is not set" in report["skipped"]


def test_meter_sums_cost_of_nested_calls():
    inner = PricedModel()

    @tool
    def ask(question: str) -> str:
        """Ask the inner model."""
        return inner.invoke([HumanMessage(question)]).text

    with metered() as meter:
        PricedModel().invoke([HumanMessage("hi")])
        ask.invoke({"question": "nested"})
    assert meter.cost == 0.5 and meter.calls == 2
    assert meter.tool_outputs == {"ask": ["ok"]}
    PricedModel().invoke([HumanMessage("after")])
    assert meter.calls == 2
