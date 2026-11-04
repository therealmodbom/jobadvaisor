"""Hard exclusions: deterministic predicates over raw posting fields, no model call."""

import re

from jobadvaisor.data.models import ExclusionRule, Posting


def check_exclusions(posting: Posting, rules: list[ExclusionRule]) -> list[str]:
    """IDs of every rule in `rules` that `posting` matches, in rule order; empty means not excluded.

    `contains_any` matches a case-insensitive substring, `matches_regex` a `re.search` hit,
    `equals` the whole value. A rule over `urls` matches when any URL does.
    """
    return [rule.id for rule in rules if any(_matches(rule, value) for value in _values(posting,
                                                                                         rule))]


def _values(posting: Posting, rule: ExclusionRule) -> list[str]:
    value = getattr(posting, rule.field)
    return value if isinstance(value, list) else [value]


def _matches(rule: ExclusionRule, value: str) -> bool:
    match rule.operator:
        case "contains_any":
            return any(needle.casefold() in value.casefold() for needle in rule.value)
        case "matches_regex":
            return re.search(rule.value, value) is not None
        case "equals":
            return value == rule.value
