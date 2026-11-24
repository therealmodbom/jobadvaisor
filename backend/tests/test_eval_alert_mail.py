"""The alert-mail eval (`design.md` → Eval): how well a model picks the postings of a mail no rule
reads, as postings found and links correct. The rule cases are a regression test
(`test_alert_mail_regression.py`), not part of the eval."""

import json
import re

import pytest
from conftest import FakeStructuredModel
from test_guard import THRESHOLDS, StubClassifier

from jobadvaisor.evals import alert_mail
from jobadvaisor.evals.__main__ import EVALS
from jobadvaisor.intake.alert_mail import Entry, Found
from jobadvaisor.llm import ModelNotConfiguredError
from jobadvaisor.tools.guard import ContentGuard

MIME_MODEL_CASES = {"unknown-preheader", "unknown-quoted-printable", "unknown-multipart"}
MODEL_CASES = {"unknown-jobid", "unknown-redirect", "injection"} | MIME_MODEL_CASES


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


def test_the_eval_runs_only_the_model_cases_and_skips_them_without_a_model(deepeval):
    report = alert_mail.run(not_configured, ContentGuard(StubClassifier(), THRESHOLDS), "m",
                            deepeval)
    assert {case["case"] for case in report["cases"]} == MODEL_CASES
    assert all("not set" in case["skipped"] for case in report["cases"])
    assert report["figures"]["cases"] == 0 and "not set" in report["figures"]["skipped"]
    assert report["eval"] == "alert_mail" and report["guard"] == "stub"
    assert "groups" not in report


def test_model_cases_are_skipped_with_screening_off(deepeval):
    report = alert_mail.run(lambda: FakeStructuredModel(), ContentGuard(None, {}), "m", deepeval)
    assert {case["case"]: case["skipped"] for case in report["cases"]} == {
        name: "screening off" for name in MODEL_CASES}
    assert report["guard"] is None


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
    figures = report["figures"]
    assert figures["cases"] == len(MODEL_CASES) and 0 < figures["links_correct"] < 1


def test_the_mime_cases_are_read_as_mime_and_reach_the_model():
    """The `.eml` cases come in as their decoded HTML part, with the hidden preheader and a link
    split over quoted-printable lines intact, and no rule reads them."""
    cases = {case.name: case for case in alert_mail.load_cases()}
    assert MIME_MODEL_CASES <= set(cases)
    assert all(alert_mail.needs_model(cases[name]) for name in MIME_MODEL_CASES)
    assert "Embedded-Entwicklerin, Teamleitung Fertigung" in cases["unknown-preheader"].html
    quoted = cases["unknown-quoted-printable"]
    assert "leiter-it-betrieb-und-infrastruktur-musterstadt-4811?source=" in quoted.html
    multipart = cases["unknown-multipart"]
    assert "Datenarchitekt (m/w/d)" in multipart.html
    assert "HTML-Ansicht" in multipart.text


def test_alert_mail_is_registered():
    assert "alert_mail" in EVALS


def test_report_is_json(deepeval):
    report = alert_mail.run(not_configured, ContentGuard(None, {}), "m", deepeval)
    assert json.loads(json.dumps(report)) == report
