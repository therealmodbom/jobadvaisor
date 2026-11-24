"""Regression test of the alert-mail finder's rules (`design.md` → Regression test): every fixture
mail the rules read, and the one without postings, must give exactly its expected links and
titles. The code is deterministic, so this runs in the default `pytest` and needs no model; it
is not an eval (`AGENTS.md` → Evaluation)."""

import json

import pytest
from conftest import write_json
from test_alert_mail import NoGuard, Untouchable
from test_triage_graph import POLICY_PACK

from jobadvaisor.evals.alert_mail import CASES, load_cases
from jobadvaisor.intake.alert_mail import find_postings, preview
from jobadvaisor.intake.mailbox import mail_parts, parse_mail
from jobadvaisor.intake.postings import Intake
from jobadvaisor.tools.guard import ContentGuard

MIME_RULE_CASES = ["linkedin-mime", "ba-mime", "career-site-mime"]
RULE_CASES = {"linkedin-digest", "linkedin-single", "ba-list", "ba-plain", "career-site-a",
              "career-site-b"}
MODEL_CASES = {"unknown-jobid", "unknown-redirect", "injection"}


class NoStoredPostings(Intake):
    """An intake over an empty repository: no stored posting marks a duplicate."""

    def postings(self):
        return {}


@pytest.mark.parametrize("case", MIME_RULE_CASES)
def test_mime_rule_mails_give_their_entries_through_preview(case, tmp_path):
    """A mail read as MIME (`mail_parts`) goes through `preview` with a model and a content guard
    that fail the test when called. The expected titles hold umlauts and a sharp s that the mail
    carries as quoted-printable, base64 or ISO-8859-1, and one link that the mail splits over
    several lines, so they show that charset and transfer encoding are decoded. The attachment of
    `career-site-mime` names a posting that must not appear."""
    write_json(tmp_path / "policy-pack.json", POLICY_PACK)
    intake = NoStoredPostings(tmp_path, Untouchable(), NoGuard())
    html, text = mail_parts(parse_mail((CASES / f"{case}.eml").read_bytes()))
    answer = preview(intake, html, text, tmp_path / "alert-mails.jsonl")
    expected = json.loads((CASES / f"{case}.json").read_text())
    assert [{"url": e["url"], "title": e["title"]} for e in answer["entries"]] == expected
    assert answer["held"] is False and answer["model_skipped"] is None
    assert len(answer["read_by"]) == 1 and answer["read_by"] != ["model"]


@pytest.mark.parametrize("case", sorted(RULE_CASES | {"no-postings"}))
def test_rule_cases_match_their_fixture(case):
    """A rule regression or a changed expected title fails CI."""
    mail = next(mail for mail in load_cases() if mail.name == case)
    found = find_postings(mail.html, mail.text, model=None, guard=ContentGuard(None, {}))
    assert [{"url": e.url, "title": e.title} for e in found.entries] == mail.expected


def test_every_fixture_is_a_rule_case_or_a_model_case():
    """A new fixture must be named here, so it lands in the regression test or in the eval."""
    assert {mail.name for mail in load_cases()} == RULE_CASES | MODEL_CASES | {"no-postings"}
