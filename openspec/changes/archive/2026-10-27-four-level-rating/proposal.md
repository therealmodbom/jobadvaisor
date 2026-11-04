# Proposal

## Why

The user's rating is binary today. A posting they cannot call a clear yes or no stays unrated, so it never teaches the judge anything and never leaves the "noch nicht bewertet" filter. Adding the strength of the opinion lets them mark unclear postings, and gives the judge and the ranking more signal.

## What Changes

- A rating carries an optional `strength` (`weak` | `strong`) next to the existing `verdict`. The four levels are verdict × strength: "Ja, auf jeden Fall" (positive, strong), "Ja, vielleicht" (positive, weak), "Nein, eher nicht" (negative, weak), "Nein, auf keinen Fall" (negative, strong).
- A label without `strength` is still valid and behaves as before (a plain yes or no); no migration, no change to stored labels.
- `PUT /postings/{id}/rating` and the label JSON schema accept `strength`; the pool rows carry it.
- The rating UI offers the four levels as four buttons with the shortcuts `1` to `4` in the pool and on the posting page, and shows the stored level after a reload. The wording "Interessant" / "Nicht für mich" is replaced.
- The judge's rated examples state the strength; the agent's rating output includes it.
- Among rated-positive postings the pool ranks "auf jeden Fall" above "ja, vielleicht" and above a positive without strength.
- The correction counter, chip polarity, the "negative last" ranking group, `best_open` and the evals keep working on the direction only.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `rating-feedback`: a rating MAY carry a strength; a label without one stays valid.
- `web-ui`: the verdict control becomes four levels with shortcuts `1` to `4`, and the stored level is shown.
- `job-triage`: the judge's rated examples show the strength.
- `job-agent`: the agent's report of a stored rating includes the strength.
- `posting-pool`: ranking within the rated-positive group orders by strength (this capability exists only in the unarchived `rated-pool` change; see design).

## Non-goals

- What the score means (#27), and graded evals with strength-weighted metrics.
- Any change to labels already stored, or a migration.
- Using the strength for the correction counter, `best_open`, or chip polarity: direction alone drives them.
- A strength for imported labels or for a rating given without a verdict (a verdict derived from a chip has no strength).
- A strength-weighted eval metric: the scoring eval gets a per-level report and strength-bearing demo labels, and keeps measuring the direction. A later change owns graded evals.

## Impact

- Backend: `data/models.py` (`Label.strength`, schema), `schemas/label.schema.json`, `api/app.py`, `pool.py`, `tools/scoring.py`, `agent/__init__.py`; `data/demo_persona.py` (rating labels get a derived strength, regenerated `fixtures/demo-persona/labels/`) and `evals/scoring.py` (a `by_level` block in the report); [ADR 0008](../../../../docs/decisions/0008-rating-strength-as-a-second-label-field.md).
- Frontend: `api.ts`, `lib/rating.ts`, `components/rating.tsx`, `components/posting.tsx`, `views/PoolView.tsx`, `views/PostingPage.tsx`, the test fixtures.
- Specs: deltas for the five capabilities above. No new dependency.
