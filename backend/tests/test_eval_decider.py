"""The hosted decision-model competitor, with a fake decision-model client. Live runs go through
`python -m jobadvaisor.evals`."""

import json
from types import SimpleNamespace

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import load
from jobadvaisor.evals import __main__ as cli
from jobadvaisor.evals import decider as decider_eval
from jobadvaisor.evals.feature_extraction import EXPECTED_FILE
from jobadvaisor.evals.scoring import time_split
from jobadvaisor.index import LabelIndex
from jobadvaisor.llm import Decider
from jobadvaisor.settings import Settings
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.tools.prompts import posting_block

DEMO = load(FIXTURE_DIRECTORY)
GUARD = ContentGuard(None, {})  # every demo posting carries a clean stored guard
EXPECTED = json.loads(EXPECTED_FILE.read_text())["postings"]


class FakeDecider:
    """A decision-model client: `answer(request)` gives the answers; every call costs 0.001."""

    def __init__(self, answer):
        self.answer, self.requests = answer, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **request):
        self.requests.append(request)
        content = json.dumps(self.answer(request))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                               usage=SimpleNamespace(cost=0.001))


def knows_verdicts(request):
    """Score level index 9 for postings rated positive, 0 otherwise."""
    text = request["messages"][-1]["content"]
    posting = text.rsplit("Posting to score:\n", 1)[1]
    positive = any(posting == posting_block(DEMO.postings[posting_id])
                   for posting_id, label in DEMO.labels.items() if label.verdict == "positive")
    return {"fit": {"type": "score", "score": 9.0 if positive else 0.0}}


def knows_features(request):
    """Every choice question answered with the expected value of the posting in the message."""
    text = request["messages"][-1]["content"]
    posting_id = next(key for key in EXPECTED if posting_block(DEMO.postings[key]) in text)
    return {question: {"type": "choice", "choice": EXPECTED[posting_id][question]}
            for question in request["response_format"]["questions"]}


@pytest.fixture(scope="module")
def index(tmp_path_factory):
    built = LabelIndex(tmp_path_factory.mktemp("chroma"), DeterministicFakeEmbedding(size=16),
                       "fake-16")
    built.sync(DEMO)
    return built


def test_scoring_ranks_by_the_score_question(index):
    client = FakeDecider(knows_verdicts)
    report = decider_eval.run_scoring(DEMO, index, GUARD, Decider(client, "jev"), k=5,
                                      held_out=15)
    split = time_split(DEMO, 15)
    assert report["precision_at_k"] == 1.0 and report["held_out"] == 15
    assert report["cut_off"] == split.cut_off.isoformat()
    assert report["cost_per_posting_usd"] == pytest.approx(0.001)
    [question] = client.requests[0]["response_format"]["questions"].values()
    assert question["type"] == "score" and len(question["criteria"]) == 10
    used = [example_id for row in report["scores"] for example_id in row["example_ids"]]
    assert used and all(DEMO.labels[example_id].rated_at < split.cut_off for example_id in used)


def test_score_maps_the_level_index_to_one_to_ten():
    client = FakeDecider(lambda request: {"fit": {"type": "score", "score": 4.5}})
    posting = next(iter(DEMO.postings.values()))
    assert decider_eval.decider_score(Decider(client, "jev"), posting, DEMO.profile,
                                      DEMO.policy_pack, []) == 5.5


def test_extraction_asks_one_choice_question_per_categorical_feature():
    client = FakeDecider(knows_features)
    report = decider_eval.run_extraction(DEMO, Decider(client, "jev"))
    questions = client.requests[0]["response_format"]["questions"]
    assert {question["type"] for question in questions.values()} == {"choice"}
    assert set(questions) == {"role_type", "seniority", "domain", "location", "remote_option",
                              "company_stage"}
    assert all("unknown" in question["criteria"] for question in questions.values())
    assert report["postings"] == 20 and set(report["accuracy"].values()) == {1.0}
    assert report["cost_per_posting_usd"] == pytest.approx(0.001)


def test_cli_skips_the_competitor_without_model(monkeypatch, capsys):
    monkeypatch.setattr(cli, "Settings", lambda: Settings(_env_file=None, guard_model="x/guard"))
    cli.main(["--only", "decider_competitor"])
    [report] = json.loads(capsys.readouterr().out)
    assert report == {"eval": "decider_competitor", "skipped": "--model is not given"}


@pytest.fixture
def candidate_run(monkeypatch):
    """`cli.main` with the decision-model client, the index, the guard and both evals stubbed;
    returns the (model, base URL) pairs a client was built for and the candidates the evals got."""
    built, seen = [], {}
    monkeypatch.setattr(cli, "Settings", lambda: Settings(
        _env_file=None, guard_model="x/guard", llm_base_url="https://router.example/v1"))
    monkeypatch.setattr(cli, "decider_client", lambda model, base_url, settings: built.append(
        (model, base_url)) or Decider(FakeDecider(lambda request: {}), model))
    monkeypatch.setattr(cli, "_synced_index", lambda repository, settings: None)
    monkeypatch.setattr(cli, "configured_guard", lambda settings: GUARD)
    monkeypatch.setattr(cli.decider_competitor, "run", lambda repository, index, guard, chosen:
                        seen.update(competitor=chosen.model) or {"eval": "decider_competitor"})
    monkeypatch.setattr(cli.content_guard, "run", lambda repository, classifier, thresholds:
                        seen.setdefault("guard", []).append(classifier.name) or {})
    return built, seen


def test_model_names_the_competitor_and_the_guard_row_of_one_run(candidate_run, capsys):
    built, seen = candidate_run
    cli.main(["--only", "decider_competitor", "content_guard", "--model", "typesafe/jev-1.14.0"])
    assert built == [("typesafe/jev-1.14.0", "https://router.example/v1")]
    assert seen == {"competitor": "typesafe/jev-1.14.0",
                    "guard": ["decider:typesafe/jev-1.14.0"]}


def test_base_url_goes_with_model(candidate_run):
    built, _ = candidate_run
    cli.main(["--only", "content_guard", "--model", "m", "--base-url", "https://other.example/v1"])
    assert built == [("m", "https://other.example/v1")]


def test_a_failing_candidate_client_fails_only_the_evals_that_need_it(monkeypatch, capsys):
    def broken(model, base_url, settings):
        raise RuntimeError("no API key")

    monkeypatch.setattr(cli, "Settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(cli, "decider_client", broken)
    cli.main(["--only", "baseline", "content_guard", "--model", "m"])
    baseline, guard = json.loads(capsys.readouterr().out)
    assert "error" not in baseline
    assert guard == {"eval": "content_guard", "error": "RuntimeError: no API key"}


def test_the_candidate_is_built_once_for_both_evals(candidate_run):
    built, _ = candidate_run
    cli.main(["--only", "decider_competitor", "content_guard", "--model", "m"])
    assert built == [("m", "https://router.example/v1")]


def test_the_guard_setting_alone_does_not_make_a_candidate(candidate_run):
    built, seen = candidate_run
    cli.main(["--only", "decider_competitor", "content_guard"])
    assert built == [] and seen == {}
