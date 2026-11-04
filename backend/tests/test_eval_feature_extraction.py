"""The feature-extraction eval's harness, with a fake model. The eval itself makes real calls
and runs only through `python -m jobadvaisor.evals`."""

import json

import pytest
from conftest import FakeStructuredModel
from test_eval_scoring import PricedJudge

from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import load
from jobadvaisor.evals import __main__ as cli
from jobadvaisor.evals.feature_extraction import EXPECTED_FILE, run
from jobadvaisor.settings import REPOSITORY_ROOT, Settings

EXPECTED = json.loads(EXPECTED_FILE.read_text())["postings"]


class FailingOnce(FakeStructuredModel):
    def _answer(self, schema, messages):
        if not self.prompts:
            self.prompts.append(messages)
            raise ValueError("model answered outside the schema")
        return super()._answer(schema, messages)


def test_expected_features_cover_20_demo_postings_and_every_demo_feature():
    demo = load(FIXTURE_DIRECTORY)
    feature_ids = {feature.id for feature in demo.policy_pack.feature_set}
    assert len(EXPECTED) == 20 and set(EXPECTED) <= set(demo.postings)
    assert all(set(features) == feature_ids for features in EXPECTED.values())


def test_reports_per_field_accuracy_with_lists_compared_as_sets():
    answers = [dict(features, tech_stack=features["tech_stack"][::-1])
               for features in EXPECTED.values()]
    answers[0] = dict(answers[0], seniority="junior")
    report = run(load(FIXTURE_DIRECTORY), FakeStructuredModel(*answers), "fake")
    assert report["accuracy"]["seniority"] == 0.95
    assert {field: value for field, value in report["accuracy"].items()
            if field != "seniority"} == dict.fromkeys(report["accuracy"].keys() - {"seniority"},
                                                      1.0)
    assert (report["postings"], report["model"]) == (20, "fake")
    assert report["mismatches"] == [{"posting": "demo-031", "feature": "seniority",
                                     "expected": "lead", "got": "junior"}]


def test_a_failed_call_counts_as_wrong_and_the_eval_goes_on():
    model = FailingOnce(*list(EXPECTED.values())[1:])
    report = run(load(FIXTURE_DIRECTORY), model, "fake")
    assert report["accuracy"]["seniority"] == 0.95
    assert report["errors"] == [{"posting": "demo-031", "error": "model answered outside the "
                                                                 "schema"}]


def test_report_carries_the_cost_per_posting():
    report = run(load(FIXTURE_DIRECTORY), PricedJudge(*EXPECTED.values()), "fake")
    assert report["cost_per_posting_usd"] == 0.25 and report["uncosted_calls"] == 0


def test_non_demo_data_is_skipped_with_the_reason(data_repository):
    report = run(load(data_repository), FakeStructuredModel(), "fake")
    assert report["skipped"] == "expected features exist only for the demo persona"


def test_cli_skips_an_eval_whose_model_is_not_configured(monkeypatch, capsys):
    monkeypatch.setattr(cli, "Settings", lambda: Settings(_env_file=None))
    cli.main(["--only", "feature_extraction", "content_guard"])
    [extraction, guard] = json.loads(capsys.readouterr().out)
    assert extraction == {"eval": "feature_extraction",
                          "skipped": "EXTRACTOR_MODEL or LLM_MODEL is not set"}
    assert [row["skipped"] for row in guard["classifiers"]] == ["MISTRAL_API_KEY is not set",
                                                                "DECIDER_MODEL is not set"]


def test_cli_reports_a_failing_eval_and_keeps_the_others(monkeypatch, capsys):
    def broken(repository, settings):
        raise RuntimeError("router rejected the model")

    monkeypatch.setattr(cli, "Settings", lambda: Settings(_env_file=None))
    monkeypatch.setitem(cli.EVALS, "scoring", broken)
    cli.main(["--only", "scoring", "content_guard"])
    [scoring, guard] = json.loads(capsys.readouterr().out)
    assert scoring == {"eval": "scoring", "error": "RuntimeError: router rejected the model"}
    assert guard["eval"] == "content_guard"


def test_cli_refuses_to_write_non_demo_results_inside_the_repository(data_repository):
    with pytest.raises(SystemExit):
        cli.main(["--data", str(data_repository), "--out", str(REPOSITORY_ROOT / "results")])
