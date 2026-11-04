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


def test_cli_skips_the_competitor_without_a_decision_model(monkeypatch, capsys):
    monkeypatch.setattr(cli, "Settings", lambda: Settings(_env_file=None))
    cli.main(["--only", "decider_competitor"])
    [report] = json.loads(capsys.readouterr().out)
    assert report == {"eval": "decider_competitor", "skipped": "DECIDER_MODEL is not set"}
