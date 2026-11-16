"""The alert-mail eval (`design.md` → Eval): postings found and links correct, per rule and for
the model."""

import json
import re

import pytest
from conftest import FakeStructuredModel
from test_guard import THRESHOLDS, StubClassifier

from jobadvaisor.evals import alert_mail
from jobadvaisor.evals.__main__ import EVALS
from jobadvaisor.intake.alert_mail import Entry, Found, find_postings
from jobadvaisor.llm import ModelNotConfiguredError
from jobadvaisor.tools.guard import ContentGuard

RULE_CASES = {"linkedin-digest", "linkedin-single", "ba-list", "ba-plain", "career-site-a",
              "career-site-b"}


def not_configured():
    raise ModelNotConfiguredError("INTAKE_MODEL or LLM_MODEL is not set")


@pytest.mark.parametrize(("expected", "found", "scores"), [
    ([{"url": "a"}, {"url": "b"}], Found([Entry("a", "A")], [], []), (0.5, 1.0)),
    ([{"url": "a"}], Found([Entry("a", "A"), Entry("x", "X")], [], []), (1.0, 0.5)),
    ([], Found([], [], []), (1.0, 1.0)),
    ({"held": True}, Found([], [], [], held=True), (1.0, 1.0)),
    ({"held": True}, Found([Entry("a", "A")], [], []), (0.0, 0.0)),
])
def test_scores(expected, found, scores):
    assert alert_mail.scores(expected, found) == scores


def test_rule_cases_score_one_and_model_cases_are_skipped_without_a_model(deepeval):
    report = alert_mail.run(not_configured, ContentGuard(StubClassifier(), THRESHOLDS), "m",
                            deepeval)
    cases = {case["case"]: case for case in report["cases"]}
    assert {name for name, case in cases.items() if case.get("postings_found") == 1.0
            and case.get("links_correct") == 1.0} == RULE_CASES | {"no-postings"}
    assert all("not set" in cases[name]["skipped"]
               for name in ("unknown-jobid", "unknown-redirect", "injection"))
    assert report["groups"]["linkedin"] == {"cases": 2, "postings_found": 1.0,
                                            "links_correct": 1.0}
    assert set(report["groups"]) == {"linkedin", "bundesagentur", "career_site", "model"}
    assert report["eval"] == "alert_mail" and report["guard"] == "stub"


def test_model_cases_are_skipped_with_screening_off(deepeval):
    report = alert_mail.run(lambda: FakeStructuredModel(), ContentGuard(None, {}), "m", deepeval)
    cases = {case["case"]: case for case in report["cases"]}
    assert cases["unknown-jobid"]["skipped"] == "screening off"
    assert cases["no-postings"]["postings_found"] == 1.0 and report["guard"] is None


def test_model_cases_are_scored_with_a_model(deepeval):
    class Picker:
        """Picks every kept link whose text holds an expected title."""

        def with_structured_output(self, schema):
            outer = self

            class Runnable:
                def invoke(self, messages):
                    outer.prompt = messages[-1].content
                    picks = [{"link": int(n), "title": t} for t, n in
                             re.findall(r"\[([^\]]+)\]\(#(\d+) ", outer.prompt)]
                    return schema.model_validate({"postings": picks})
            return Runnable()

    report = alert_mail.run(Picker, ContentGuard(StubClassifier(), THRESHOLDS), "m", deepeval)
    model = report["groups"]["model"]
    assert model["cases"] == 4 and 0 < model["links_correct"] < 1


@pytest.mark.parametrize("case", sorted(RULE_CASES | {"no-postings"}))
def test_default_run_rule_cases_match_their_fixture(case):
    """Runs in the default `pytest`, without DeepEval: a rule regression or a changed expected
    title fails CI."""
    mail = next(mail for mail in alert_mail.load_cases() if mail.name == case)
    found = find_postings(mail.html, mail.text, model=None, guard=ContentGuard(None, {}))
    assert [{"url": e.url, "title": e.title} for e in found.entries] == mail.expected


def test_cases_cover_every_fixture():
    assert {mail.name for mail in alert_mail.load_cases()} == RULE_CASES | {
        "no-postings", "unknown-jobid", "unknown-redirect", "injection"}


def test_alert_mail_is_registered():
    assert "alert_mail" in EVALS


def test_report_is_json(deepeval):
    report = alert_mail.run(not_configured, ContentGuard(None, {}), "m", deepeval)
    assert json.loads(json.dumps(report)) == report
