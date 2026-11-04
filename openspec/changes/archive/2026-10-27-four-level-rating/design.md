# Design

## Context

See proposal.md for motivation. Today a `Label` holds `verdict` (`positive` | `negative`, absent only for `imported_not_preference`), chips, a note and `rated_at`. `PUT /postings/{id}/rating` replaces the whole label on every call, and the frontend resends the full rating (`send` in `lib/rating.ts`) on each chip or note change. Everything that counts, ranks or evaluates reads `label.verdict` (`pool.py`, `evals/*`, `agent`), so the direction must stay the only input there.

`posting-pool` exists only as a delta in the unarchived `rated-pool` change (two tasks open: 7.2, 7.4). This change adds requirements to it instead of modifying `rated-pool`'s text, so the two do not collide in either archive order.

## Goals / Non-Goals

**Goals:**
- Strength is additive: a file without it loads and behaves as before, and no code path needs a migration.
- One place defines the rank order of strengths, and the UI, the judge line and the agent all read the same stored field.

**Non-Goals:**
- Anything on the proposal's non-goals list.
- A rule that derives a strength (from the score, a chip or a previous label).

## Decisions

**`strength` is a second optional field on `Label`, not a four-value `verdict`.** The rationale and the rejected alternatives are in [ADR 0008](../../../../docs/decisions/0008-rating-strength-as-a-second-label-field.md).

**Validation: `strength` requires a verdict.** `Label.verdict_fits_kind` already ties `verdict` to `kind`; a second check rejects a strength when the verdict is absent, which covers `imported_not_preference`. The generated JSON schema (`schemas/label.schema.json`) gains the enum from the model; regenerate it the way the repo does rather than hand-editing, and keep the existing `if/then/else` block. The API enforces the same rule before the verdict is resolved: a body with `strength` and no `verdict` is a 422, even when a chip would derive a verdict. `resolve_verdict` stays as it is, since a derived verdict has no strength.

**The API stores what it is given.** `RatingBody.strength` is optional and goes straight into the `Label`. Because the `PUT` replaces the whole label, a request that omits `strength` clears it; this is what makes "plain verdict after a level" work and needs no extra rule.

**The client keeps the strength in the rating it resends.** `lib/rating.ts` `view` returns `strength` next to `verdict`, and `send` carries it through chip and note changes; only choosing a level changes it. Otherwise a chip toggle would silently turn "ja, auf jeden Fall" into a plain yes. A new `level` action sends verdict and strength together.

**One level table on the client.** The four levels (key, label, verdict, strength) live in one constant used by the buttons, the legend, the keyboard handler and the display, so the order and the wording are defined once. A stored label without strength shows as "Ja" / "Nein" and marks no button. Choosing the level already shown sends nothing.

**Rank within the rated-positive group.** In `pool.rank` the positive group already sorts by score and then `rated_at`; a strength key is applied as the outermost sort: strong, then no strength, then weak. Python's sort is stable, so the order within a level is the one the group has today. The group an entry belongs to stays decided by the verdict alone (`_group`), so a strength never moves a posting out of its group; `counter` and `best_open` are not touched. The pool row's `label` gains `strength` (null when absent).

**Positive without strength ranks between strong and weak.** It is a plain yes: it says neither "auf jeden Fall" nor "vielleicht". Alternative: rank it with weak. Rejected: an old yes would then rank with a new "vielleicht", which says less than it did. Ranking it with strong would hide the new emphasis. The middle slot leaves the order of files without any strength exactly as it is today, which is the compatibility promise made.

**Judge and agent show the strength as plain words.** `tools/scoring._example` appends it after the verdict only when set (`positive (strong)`, `negative (weak)`), so a line for a label without strength is byte-identical to today's. The agent's `your_rating` and its rating summaries carry `strength` the same way. `similar` retrieval and the example choice do not use the strength.

**Eval.** The judge line is the only LLM-facing change, and the scoring eval (`python -m jobadvaisor.evals`) covers it. Data: the demo persona's rating labels now carry a strength derived from the utility margin to the threshold (`STRONG_MARGIN`, no random draws, so the rest of the fixture is unchanged), which puts strength-bearing examples into the judge's prompts. Metrics: precision@k on the held-out labels, which must not drop against the run before this change, and a new `by_level` block in the report with the count and mean score per verdict/strength, so a run shows whether the judge separates "auf jeden Fall" from "vielleicht". The paid suite runs only on an explicit decision; none is run in this change. A strength-weighted metric is a separate, later issue.

**ADR.** [ADR 0008](../../../../docs/decisions/0008-rating-strength-as-a-second-label-field.md) holds the field-versus-wider-verdict decision.

## Risks / Trade-offs

- [A client that omits `strength` on a later call clears it] → the hook carries it through every action, and a frontend test covers a chip toggle and a note edit after a level.
- [Two meanings of "no strength" (legacy yes vs. explicitly plain)] → they are the same stored state by design; the UI shows "Ja" / "Nein" for it.
- [The weak levels reach the judge as a new word in the prompt] → the model may read "weak" as noise; the direction still carries the score, and a later strength-weighted metric can measure the effect.
- [Archive order with `rated-pool`] → this change only adds requirements, so it archives cleanly before or after `rated-pool`; `posting-pool`'s delta carries its Purpose in case it creates the capability.
