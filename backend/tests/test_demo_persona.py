import re
from datetime import timedelta
from urllib.parse import urlparse

import pytest

from jobadvaisor.data.demo_persona import (
    DEMO_FACTS,
    FIXTURE_DIRECTORY,
    _make_excluded,
    generate,
)
from jobadvaisor.data.loader import load
from jobadvaisor.data.models import company_id

HELD_OUT = 15
TRAINING_MINIMUM = 100  # the logistic-regression competitor's default (match-evaluation spec)


@pytest.fixture(scope="module")
def demo():
    return load(FIXTURE_DIRECTORY)


def test_fixture_passes_the_loader(demo):
    assert len(demo.postings) == 150


def test_every_employer_has_a_record_that_fits_the_stage_its_postings_state(demo):
    """The records give the extraction eval facts consistent with the postings' own text."""
    stages = {}
    for posting in demo.postings.values():
        if posting.company != "unknown":
            stages[posting.company] = re.search(
                r" is an? (startup|scale-up|enterprise|agency) building", posting.text)[1]
    wanted = {company_id(name) for name in stages} - {company_id("Demo Co. Lucky Spin")}
    assert wanted <= demo.companies.keys()
    for name, stage in stages.items():
        if record := demo.companies.get(company_id(name)):
            assert record.name == name
            assert (record.size_class, record.founded) == DEMO_FACTS[stage]


def test_fixture_is_the_generator_output(tmp_path):
    generate(tmp_path)
    committed = {path.relative_to(FIXTURE_DIRECTORY): path.read_text()
                 for path in FIXTURE_DIRECTORY.rglob("*.json")}
    generated = {path.relative_to(tmp_path): path.read_text() for path in tmp_path.rglob("*.json")}
    assert committed == generated


def test_every_label_kind_and_legacy_decision_is_present(demo):
    assert {label.kind for label in demo.labels.values()} == {
        "rating", "imported_interest", "imported_rejection", "imported_not_preference"}
    assert {posting.legacy_decision for posting in demo.postings.values()} == {
        None, "kept", "discarded"}


def test_rated_sample_of_discarded_postings_exists(demo):
    """The baseline eval needs `discarded` postings the user rated in the app."""
    assert any(demo.postings[pid].legacy_decision == "discarded" and label.kind == "rating"
               for pid, label in demo.labels.items())


def test_labels_span_at_least_eight_weeks(demo):
    dates = [label.rated_at for label in demo.labels.values()]
    assert max(dates) - min(dates) >= timedelta(weeks=8)


def test_training_side_reaches_the_competitor_minimum(demo):
    usable = sorted(label.rated_at for label in demo.labels.values()
                    if label.kind != "imported_not_preference")
    assert len(usable) - HELD_OUT >= TRAINING_MINIMUM


def test_ratings_carry_a_strength_and_imports_do_not(demo):
    ratings = [label for label in demo.labels.values() if label.kind == "rating"]
    levels = {(label.verdict, label.strength) for label in ratings}
    assert levels == {(verdict, strength) for verdict in ("positive", "negative")
                      for strength in ("weak", "strong")}
    assert all(label.strength is None for label in demo.labels.values()
               if label.kind != "rating")


def test_both_verdicts_and_chips_are_used(demo):
    rated = [label for label in demo.labels.values() if label.verdict]
    assert {label.verdict for label in rated} == {"positive", "negative"}
    chip_ids = {chip.id for chip in demo.policy_pack.reason_chips}
    used = {chip for label in rated for chip in label.chips}
    assert used <= chip_ids and len(used) >= len(chip_ids) - 1


def test_every_chip_has_a_polarity_and_exactly_one_rating_mixes_them(demo):
    polarity = {chip.id: chip.polarity for chip in demo.policy_pack.reason_chips}
    assert None not in polarity.values()
    mixed = [pid for pid, label in demo.labels.items()
             if {polarity[chip] for chip in label.chips} == {"positive", "negative"}]
    assert len(mixed) == 1 and demo.labels[mixed[0]].kind == "rating"
    assert all(polarity[chip] == label.verdict for pid, label in demo.labels.items()
               if pid not in mixed for chip in label.chips)


def test_unlabeled_postings_include_imported_and_presented_ones(demo):
    unlabeled = [demo.postings[pid] for pid in demo.postings.keys() - demo.labels.keys()]
    assert any(posting.legacy_decision for posting in unlabeled)
    assert any(posting.presented_at for posting in unlabeled)
    assert any(not posting.presented_at and not posting.legacy_decision for posting in unlabeled)


def test_every_posting_was_screened(demo):
    """Unscreened postings pause a run, which would stop the demo cycle."""
    assert all(posting.guard and not posting.guard.flagged for posting in demo.postings.values())


def test_some_postings_match_an_exclusion_rule(demo):
    terms = [term for rule in demo.policy_pack.exclusion_rules if rule.operator == "contains_any"
             for term in rule.value]
    assert any(term in posting.text for posting in demo.postings.values() for term in terms)


def test_every_source_type_is_present(demo):
    assert {posting.source_type for posting in demo.postings.values()} == {"url", "text", "pdf"}


@pytest.mark.parametrize("article", ["a", "an"])
def test_company_exclusion_keeps_the_posting_text(demo, article):
    posting = demo.postings["demo-050"].model_copy()
    posting.text = f"Demo Co. Elm is {article} agency building media apps."
    excluded = _make_excluded(posting, nth=2)
    assert excluded.text == f"Demo Co. Lucky Spin is {article} agency building media apps."


def test_texts_use_the_right_article(demo):
    assert [pid for pid, posting in demo.postings.items()
            if re.search(r"\ba [aeiou]", posting.text)] == []


def test_urls_use_reserved_example_domains(demo):
    hosts = {urlparse(url).hostname for posting in demo.postings.values() for url in posting.urls}
    assert hosts and all(host.endswith((".example.com", ".example.org")) for host in hosts)


def test_companies_follow_the_fictional_pattern(demo):
    companies = {posting.company for posting in demo.postings.values()} - {"unknown"}
    assert companies and all(company.startswith("Demo Co. ") for company in companies)
