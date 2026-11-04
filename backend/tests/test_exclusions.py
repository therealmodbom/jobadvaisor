import json

from conftest import POLICY_PACK, POSTING, write_json

from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import load
from jobadvaisor.data.models import ExclusionRule, Posting
from jobadvaisor.tools.exclusions import check_exclusions


def posting(**fields) -> Posting:
    return Posting.model_validate({**POSTING, **fields})


def rule(rule_id: str, field: str, operator: str, value) -> ExclusionRule:
    return ExclusionRule(id=rule_id, field=field, operator=operator, value=value)


def test_contains_any_matches_any_value_ignoring_case():
    rules = [rule("on-call", "text", "contains_any", ["night shifts", "24/7 ON-CALL"])]
    assert check_exclusions(posting(text="Includes a 24/7 on-call rotation."), rules) == ["on-call"]
    assert check_exclusions(posting(text="Office hours only."), rules) == []


def test_matches_regex_searches_the_field():
    rules = [rule("unpaid", "title", "matches_regex", r"(?i)\bunpaid\b")]
    assert check_exclusions(posting(title="Unpaid Backend Internship"), rules) == ["unpaid"]
    assert check_exclusions(posting(title="Backend Engineer"), rules) == []


def test_equals_compares_the_whole_value():
    rules = [rule("betting", "company", "equals", "Demo Co. Lucky Spin")]
    assert check_exclusions(posting(company="Demo Co. Lucky Spin"), rules) == ["betting"]
    assert check_exclusions(posting(company="Demo Co. Lucky Spin Labs"), rules) == []


def test_url_rules_match_any_url():
    urls = ["https://jobs.example.com/1", "https://careers.example.org/oak/1"]
    rules = [rule("org", "urls", "contains_any", ["example.org"]),
             rule("exact", "urls", "equals", "https://jobs.example.com/1"),
             rule("regex", "urls", "matches_regex", r"/oak/")]
    assert check_exclusions(posting(source_type="url", urls=urls), rules) == ["org", "exact",
                                                                              "regex"]


def test_every_matching_rule_is_reported_in_rule_order():
    rules = [rule("b", "title", "contains_any", ["backend"]),
             rule("a", "text", "contains_any", ["things"])]
    assert check_exclusions(posting(), rules) == ["b", "a"]


def test_same_posting_and_rules_give_the_same_result():
    rules = [rule("b", "title", "matches_regex", "Engineer$")]
    assert check_exclusions(posting(), rules) == check_exclusions(posting(), rules) == ["b"]


def test_changed_policy_pack_applies_without_code_change(data_repository):
    before = load(data_repository)
    assert check_exclusions(before.postings["p1"], before.policy_pack.exclusion_rules) == []
    write_json(data_repository / "policy-pack.json", {**POLICY_PACK, "exclusion_rules": [
        {"id": "no-backend", "field": "title", "operator": "contains_any", "value": ["backend"]}]})
    after = load(data_repository)
    assert check_exclusions(after.postings["p1"], after.policy_pack.exclusion_rules) == [
        "no-backend"]
    assert json.loads((data_repository / "postings/p1.json").read_text()) == POSTING


def test_demo_persona_excludes_the_nine_postings_built_to_match_a_rule():
    demo = load(FIXTURE_DIRECTORY)
    matches = [check_exclusions(posting, demo.policy_pack.exclusion_rules)
               for posting in demo.postings.values()]
    assert sorted(len(ids) for ids in matches if ids) == [1] * 9
