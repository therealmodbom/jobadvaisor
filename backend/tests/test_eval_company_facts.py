"""The company-facts eval's harness, with a fake model. The eval itself makes a real call and runs
only through `python -m jobadvaisor.evals`."""

import json

import pytest
from conftest import FakeStructuredModel
from test_eval_scoring import PricedJudge

from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import load
from jobadvaisor.evals import __main__ as cli
from jobadvaisor.evals.company_facts import CASE_FILE, run

CASE = json.loads(CASE_FILE.read_text())
ANSWER = {"role_type": "android", "seniority": "mid", "domain": "fitness", "tech_stack": ["kotlin"],
          "location": "unknown", "remote_option": "remote", "company_stage": "enterprise"}


@pytest.fixture(scope="module")
def demo():
    return load(FIXTURE_DIRECTORY)


def test_the_posting_text_states_neither_size_nor_stage():
    text = CASE["posting"]["text"].casefold()
    assert not any(word in text for word in (
        "startup", "scale-up", "enterprise", "agency", "employees", "founded", "global"))


def test_the_stage_is_correct_when_it_matches_and_the_call_carries_the_facts(demo):
    model = FakeStructuredModel(ANSWER)
    report = run(demo, model, "fake")
    assert (report["expected"], report["got"], report["correct"]) == (
        "enterprise", "enterprise", True)
    human = model.prompts[0][1].content
    assert "Size class: 10,001+ employees. Founded: 1978." in human
    assert (report["model"], report["errors"]) == ("fake", [])


def test_an_unknown_stage_is_wrong(demo):
    report = run(demo, FakeStructuredModel({**ANSWER, "company_stage": "unknown"}), "fake")
    assert (report["got"], report["correct"]) == ("unknown", False)


def test_a_failed_call_is_an_error_and_counts_as_wrong(demo):
    report = run(demo, FakeStructuredModel(), "fake")  # no answer left: the call raises
    assert report["correct"] is False and len(report["errors"]) == 1


def test_the_report_carries_the_cost(demo):
    report = run(demo, PricedJudge(ANSWER), "fake")
    assert report["cost_usd"] == 0.25 and report["uncosted_calls"] == 0


def test_other_data_is_skipped(data_repository):
    report = run(load(data_repository), FakeStructuredModel(ANSWER), "fake")
    assert "skipped" in report and "correct" not in report


def test_the_eval_is_registered_under_its_name():
    assert "company_facts" in cli.EVALS
