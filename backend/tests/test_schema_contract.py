"""The published schemas and the models agree: what one accepts, the other accepts."""

import json

import pytest
from conftest import AT, LABEL, POLICY_PACK, POSTING
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.schemas import ENTITIES, SCHEMA_DIRECTORY


def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((SCHEMA_DIRECTORY / f"{name}.schema.json").read_text()))


def entity_name(path) -> str:
    return {"postings": "posting", "labels": "label", "companies": "company"}.get(
        path.parent.name, path.stem)


def test_demo_fixture_conforms_to_the_published_schemas():
    for path in FIXTURE_DIRECTORY.rglob("*.json"):
        errors = list(validator(entity_name(path)).iter_errors(json.loads(path.read_text())))
        assert errors == [], path


RULE = {"id": "r", "field": "text", "operator": "equals", "value": "x"}
FEATURE = {"id": "f", "description": "d", "type": "boolean"}
COMPANY = {"schema_version": "1", "name": "Acme", "size_class": "51-200", "founded": 2019,
           "source": "linkedin", "source_url": "https://www.linkedin.com/company/acme",
           "fetched_at": AT}

REJECTED = [
    ("label", {**LABEL, "verdict": None}),
    ("label", {key: value for key, value in LABEL.items() if key != "verdict"}),
    ("label", {"schema_version": "1", "kind": "imported_not_preference", "verdict": "negative",
               "rated_at": AT}),
    ("posting", {**POSTING, "source_type": "url"}),
    ("posting", {**POSTING, "source_type": "url", "urls": []}),
    ("policy-pack", {**POLICY_PACK, "feature_set": [{**FEATURE, "type": "categorical"}]}),
    ("policy-pack", {**POLICY_PACK, "feature_set": [{**FEATURE, "options": ["a"]}]}),
    ("policy-pack", {**POLICY_PACK, "feature_set": [{**FEATURE, "options": []}]}),
    ("policy-pack", {**POLICY_PACK, "feature_set": [{**FEATURE, "type": "text",
                                                     "options": ["a"]}]}),
    ("policy-pack", {**POLICY_PACK, "exclusion_rules": [{**RULE, "operator": "contains_any"}]}),
    ("policy-pack", {**POLICY_PACK, "exclusion_rules": [{**RULE, "value": ["x"]}]}),
    ("extraction-labels", {"schema_version": "1", "min_accuracy": 1.5}),
    ("extraction-labels", {"schema_version": "1", "min_accuracy": -0.1}),
    ("company", {**COMPANY, "founded": 19}),
    ("company", {**COMPANY, "founded": 20190}),
    ("company", {**COMPANY, "size_class": "51-200 employees"}),
    ("company", {**COMPANY, "source": "crunchbase"}),
]


@pytest.mark.parametrize(("name", "data"), REJECTED)
def test_schema_and_model_both_reject(name, data):
    assert list(validator(name).iter_errors(data)) != []
    with pytest.raises(ValidationError):
        ENTITIES[name].model_validate(data)


ACCEPTED = [
    ("label", LABEL),
    ("label", {"schema_version": "1", "kind": "imported_not_preference", "rated_at": AT}),
    ("label", {"schema_version": "1", "kind": "imported_not_preference", "verdict": None,
               "rated_at": AT}),
    ("posting", {**POSTING, "source_type": "url", "urls": ["https://jobs.example.com/1"]}),
    ("policy-pack", {**POLICY_PACK, "feature_set": [
        FEATURE, {**FEATURE, "id": "g", "options": None}, {**FEATURE, "id": "h", "type": "text"}]}),
    ("policy-pack", {**POLICY_PACK, "exclusion_rules": [
        RULE, {**RULE, "id": "r2", "operator": "contains_any", "value": ["x"]}]}),
    ("extraction-labels", {"schema_version": "1", "min_accuracy": 0.9,
                           "labels": {"p1": {"a": "x", "b": ["y"], "c": True, "d": 3}}}),
    ("extraction-labels", {"schema_version": "1"}),
    ("company", COMPANY),
    ("company", {key: value for key, value in COMPANY.items()
                 if key not in ("size_class", "founded")}),
    ("company", {**COMPANY, "size_class": "10,001+"}),
]


@pytest.mark.parametrize(("name", "data"), ACCEPTED)
def test_schema_and_model_both_accept(name, data):
    assert list(validator(name).iter_errors(data)) == []
    ENTITIES[name].model_validate(data)
