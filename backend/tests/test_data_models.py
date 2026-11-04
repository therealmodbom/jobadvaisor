import pytest
from pydantic import ValidationError

from jobadvaisor.data.models import (
    ExtractionLabels,
    Label,
    PolicyPack,
    Pool,
    Posting,
    Profile,
    Score,
)

AT = "2026-01-05T09:00:00Z"

POSTING = {
    "schema_version": "1",
    "title": "Backend Engineer",
    "company": "Example Corp",
    "location_raw": "Remote",
    "text": "We build things.",
    "source_type": "url",
    "urls": ["https://jobs.example.com/1"],
    "added_at": AT,
}
GUARD = {"flagged": False, "categories": [], "checked_by": "mistral-moderation", "checked_at": AT}
POLICY_PACK = {
    "schema_version": "1",
    "exclusion_rules": [
        {"id": "no-night", "field": "text", "operator": "contains_any", "value": ["night shift"]},
        {"id": "no-intern", "field": "title", "operator": "matches_regex", "value": "(?i)intern"},
    ],
    "reason_chips": [{"id": "too-junior", "label": "too junior"}],
    "feature_set": [
        {"id": "seniority", "description": "Seniority", "type": "categorical",
         "options": ["junior", "senior"]},
        {"id": "tech_stack", "description": "Technologies", "type": "list",
         "options": ["python", "go"]},
        {"id": "remote", "description": "Remote possible", "type": "boolean"},
    ],
}


def with_(base: dict, **changes) -> dict:
    """Return a copy of `base` with `changes` applied; a value of `...` removes the key."""
    data = {**base, **changes}
    return {key: value for key, value in data.items() if value is not ...}


def test_minimal_valid_entities_load():
    Profile.model_validate({"schema_version": "1", "summary": "Backend developer"})
    PolicyPack.model_validate(POLICY_PACK)
    Posting.model_validate(POSTING)
    Label.model_validate({"schema_version": "1", "kind": "rating", "verdict": "positive",
                          "rated_at": AT})


@pytest.mark.parametrize("field", ["schema_version", "title", "company", "location_raw", "text",
                                   "source_type", "added_at"])
def test_posting_requires_field(field):
    with pytest.raises(ValidationError, match=field):
        Posting.model_validate(with_(POSTING, **{field: ...}))


@pytest.mark.parametrize(("field", "value"), [
    ("source_type", "email"),
    ("legacy_decision", "maybe"),
    ("schema_version", "3"),
    ("status", "archived"),
])
def test_posting_rejects_value_outside_enum(field, value):
    with pytest.raises(ValidationError, match=field):
        Posting.model_validate(with_(POSTING, **{field: value}))


def test_posting_rejects_unknown_field():
    with pytest.raises(ValidationError, match="id"):
        Posting.model_validate(with_(POSTING, id="abc"))


def test_url_posting_requires_a_url():
    with pytest.raises(ValidationError, match="urls"):
        Posting.model_validate(with_(POSTING, urls=[]))


def test_guard_is_optional_and_validated_when_present():
    assert Posting.model_validate(POSTING).guard is None
    assert Posting.model_validate(with_(POSTING, guard=GUARD)).guard.flagged is False
    with pytest.raises(ValidationError, match="checked_at"):
        Posting.model_validate(with_(POSTING, guard=with_(GUARD, checked_at=...)))


def test_timestamps_need_a_timezone():
    with pytest.raises(ValidationError, match="added_at"):
        Posting.model_validate(with_(POSTING, added_at="2026-01-05T09:00:00"))


@pytest.mark.parametrize("kind", ["rating", "imported_interest", "imported_rejection"])
def test_label_kinds_with_verdict_require_it(kind):
    with pytest.raises(ValidationError, match="verdict"):
        Label.model_validate({"schema_version": "1", "kind": kind, "rated_at": AT})


def test_not_preference_label_has_no_verdict():
    Label.model_validate({"schema_version": "1", "kind": "imported_not_preference",
                          "rated_at": AT})
    with pytest.raises(ValidationError, match="verdict"):
        Label.model_validate({"schema_version": "1", "kind": "imported_not_preference",
                              "verdict": "negative", "rated_at": AT})


def test_label_without_strength_loads_as_before():
    label = Label.model_validate({"schema_version": "1", "kind": "rating",
                                  "verdict": "positive", "rated_at": AT})
    assert label.strength is None


@pytest.mark.parametrize(("verdict", "strength"), [
    ("positive", "strong"), ("positive", "weak"), ("negative", "weak"), ("negative", "strong")])
def test_label_holds_each_of_the_four_levels(verdict, strength):
    label = Label.model_validate({"schema_version": "1", "kind": "rating", "verdict": verdict,
                                  "strength": strength, "rated_at": AT})
    assert (label.verdict, label.strength) == (verdict, strength)


def test_strength_needs_a_verdict():
    with pytest.raises(ValidationError, match="strength needs a verdict"):
        Label.model_validate({"schema_version": "1", "kind": "imported_not_preference",
                              "strength": "weak", "rated_at": AT})


@pytest.mark.parametrize(("field", "value"), [
    ("kind", "liked"), ("verdict", "neutral"), ("strength", "medium")])
def test_label_rejects_value_outside_enum(field, value):
    data = {"schema_version": "1", "kind": "rating", "verdict": "positive", "rated_at": AT}
    with pytest.raises(ValidationError, match=field):
        Label.model_validate(with_(data, **{field: value}))


def test_profile_rejects_unknown_remote_value():
    with pytest.raises(ValidationError, match="remote"):
        Profile.model_validate({"schema_version": "1", "summary": "x", "remote": "sometimes"})


@pytest.mark.parametrize("feature_type", ["categorical", "list"])
def test_option_features_require_options(feature_type):
    feature = {"id": "f", "description": "d", "type": feature_type}
    with pytest.raises(ValidationError, match="options"):
        PolicyPack.model_validate(with_(POLICY_PACK, feature_set=[feature]))


@pytest.mark.parametrize(("operator", "value"), [
    ("contains_any", "night shift"),
    ("equals", ["a", "b"]),
    ("matches_regex", "(unclosed"),
])
def test_exclusion_rule_value_must_fit_operator(operator, value):
    rule = {"id": "r", "field": "text", "operator": operator, "value": value}
    with pytest.raises(ValidationError, match="value"):
        PolicyPack.model_validate(with_(POLICY_PACK, exclusion_rules=[rule]))


def test_exclusion_rule_rejects_unknown_field():
    rule = {"id": "r", "field": "salary", "operator": "equals", "value": "x"}
    with pytest.raises(ValidationError, match="field"):
        PolicyPack.model_validate(with_(POLICY_PACK, exclusion_rules=[rule]))


def test_a_chip_may_name_the_verdict_it_belongs_to():
    chips = [{"id": "great-stack", "label": "toller Tech-Stack", "polarity": "positive"},
             {"id": "too-junior", "label": "zu junior", "polarity": "negative"},
             {"id": "location", "label": "Standort"}]
    pack = PolicyPack.model_validate(with_(POLICY_PACK, reason_chips=chips))
    assert [chip.polarity for chip in pack.reason_chips] == ["positive", "negative", None]
    with pytest.raises(ValidationError):
        PolicyPack.model_validate(with_(POLICY_PACK, reason_chips=[
            {"id": "x", "label": "x", "polarity": "neutral"}]))


def test_policy_pack_rejects_duplicate_chip_ids():
    chips = [{"id": "a", "label": "one"}, {"id": "a", "label": "two"}]
    with pytest.raises(ValidationError, match="duplicate"):
        PolicyPack.model_validate(with_(POLICY_PACK, reason_chips=chips))


def test_version_1_posting_reads_as_open_without_origin():
    posting = Posting.model_validate(POSTING)
    assert (posting.status, posting.origin) == ("open", None)


def test_version_2_posting_round_trips():
    data = with_(POSTING, schema_version="2", status="applied",
                 origin={"table": "High", "fit": "8", "status": "applied"})
    posting = Posting.model_validate(data)
    assert Posting.model_validate_json(posting.model_dump_json()) == posting
    assert posting.origin.fit == "8"


def test_label_stays_at_version_1():
    with pytest.raises(ValidationError, match="schema_version"):
        Label.model_validate({"schema_version": "2", "kind": "rating", "verdict": "positive",
                              "rated_at": AT})


@pytest.mark.parametrize("value", [-1, 11])
def test_score_is_bounded_0_to_10(value):
    with pytest.raises(ValidationError, match="score"):
        Score.model_validate({"schema_version": "1", "score": value, "reasoning": "r",
                              "example_ids": [], "scored_at": AT})


def test_pool_defaults_and_pass_history():
    pool = Pool.model_validate({"schema_version": "1"})
    assert (pool.settings.correction_threshold, pool.settings.correction_rate) == (10, 0.3)
    assert pool.passes == []
    entry = {"finished_at": AT, "scored": 5, "corrections": 1, "rated": 12, "rate": 0.1}
    assert Pool.model_validate({"schema_version": "1", "passes": [entry]}).passes[0].scored == 5


def test_extraction_labels_hold_values_per_posting_and_feature():
    labels = ExtractionLabels.model_validate({
        "schema_version": "1", "min_accuracy": 0.8,
        "labels": {"p1": {"seniority": "senior", "tech_stack": ["python"], "remote": True}}})
    assert labels.min_accuracy == 0.8
    assert labels.labels["p1"]["tech_stack"] == ["python"]
    assert labels.labels["p1"]["remote"] is True


def test_extraction_labels_default_to_no_minimum_and_no_labels():
    labels = ExtractionLabels.model_validate({"schema_version": "1"})
    assert (labels.min_accuracy, labels.labels) == (None, {})


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_extraction_labels_reject_a_minimum_outside_0_to_1(value):
    with pytest.raises(ValidationError, match="min_accuracy"):
        ExtractionLabels.model_validate({"schema_version": "1", "min_accuracy": value})
