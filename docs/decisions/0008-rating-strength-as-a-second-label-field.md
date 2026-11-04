# 0008. Rating strength as a second label field, not a wider verdict

## Status

Accepted, 2026-10-27.

## Context

A rating is binary today: `verdict` is `positive` or `negative`. Four levels are wanted ("ja, auf jeden Fall", "ja, vielleicht", "nein, eher nicht", "nein, auf keinen Fall") so an unclear posting can be rated instead of left out. Label files are the user's data and are validated against a committed schema ([ADR 0006](0006-pydantic-models-as-schema-source.md)). The correction counter, the pool's ranking groups, `best_open`, chip polarity and every eval read `label.verdict` as a direction.

## Decision

The label keeps `verdict` as the direction and gains an optional `strength` (`weak` | `strong`). The four levels are verdict × strength. A label without `strength` is a plain yes or no and stays valid; a `strength` without a verdict is rejected. Only the places that care about intensity read the strength: the pool's order within the rated-positive group, the judge's example line, the agent's rating output and the UI.

## Alternatives considered

- **Widen `verdict` to four values.** Every reader of `verdict` would need a mapping from four values back to a direction, and every stored label would need a migration or a compatibility rule. A reader that is missed silently drops the new levels from the counter or from precision@k.
- **A numeric rating (for example 1 to 4 or -2 to 2).** It invites arithmetic on the scale, such as averaging or thresholds, that the user did not ask for, and it also needs a mapping from the number back to a direction in every reader.

## Consequences

- No migration: existing label files load and behave exactly as before, and a label written without a strength has no `strength` key.
- The direction readers stay untouched, so every rating keeps a direction and none falls out of the counter or precision@k.
- The intensity travels in a second field, so every writer of a whole label has to carry it along. The `PUT` replaces the label as a whole, which is why the rating client resends the strength on every chip or note change.
- An old yes without a strength is a third state next to "strong" and "weak". The pool ranks it between the two so the order of existing labels does not change.
- Evals stay on the direction; weighting by strength belongs to graded evals, tracked as a separate issue.
