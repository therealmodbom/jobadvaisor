"""Regression test of the alert-mail finder's rules (`design.md` → Regression test): every fixture
mail the rules read, and the one without postings, must give exactly its expected links and
titles. The code is deterministic, so this runs in the default `pytest` and needs no model; it
is not an eval (`AGENTS.md` → Evaluation)."""

import pytest

from jobadvaisor.evals.alert_mail import load_cases
from jobadvaisor.intake.alert_mail import find_postings
from jobadvaisor.tools.guard import ContentGuard

RULE_CASES = {"linkedin-digest", "linkedin-single", "ba-list", "ba-plain", "career-site-a",
              "career-site-b"}
MODEL_CASES = {"unknown-jobid", "unknown-redirect", "injection"}


@pytest.mark.parametrize("case", sorted(RULE_CASES | {"no-postings"}))
def test_rule_cases_match_their_fixture(case):
    """A rule regression or a changed expected title fails CI."""
    mail = next(mail for mail in load_cases() if mail.name == case)
    found = find_postings(mail.html, mail.text, model=None, guard=ContentGuard(None, {}))
    assert [{"url": e.url, "title": e.title} for e in found.entries] == mail.expected


def test_every_fixture_is_a_rule_case_or_a_model_case():
    """A new fixture must be named here, so it lands in the regression test or in the eval."""
    assert {mail.name for mail in load_cases()} == RULE_CASES | MODEL_CASES | {"no-postings"}
