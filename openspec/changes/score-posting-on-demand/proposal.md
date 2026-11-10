# Proposal

## Why

A score comes only from a pass, and a pass takes only postings without a verdict. A posting rated before any pass scored it therefore never gets a score, yet its posting page says "Noch kein Score – starte in der Liste „Neue Anzeigen bewerten“", which promises what the pass will never do. New postings also keep arriving, and the user wants to score one directly, or check what the scoring makes of a posting, without starting a pass over the whole batch.

## What Changes

- A button "Score berechnen" on the posting page and on every row of the pool list scores this one posting now: rated or not, with or without a score. It names its cost per click (one judge call).
- The score is computed the way a pass scores (content guard ruling, synced label index, the posting's most similar rated postings as examples, the judge) and stored as `scores/<id>.json`, replacing an earlier score, so pool, posting page and agent show it.
- `POST /postings/{id}/score` answers synchronously with what the posting page shows, plus the counter and next-pass figures.
- One scoring at a time: the button is refused while a pass or another single score computes, and a pass is refused while a single score computes.
- A posting an exclusion rule matches, the content guard holds, or the guard never checked while no classifier is configured, is not scored. Its button is disabled before any click, with a visible info icon that gives the reason.
- The posting page keeps the old score visible, marked as being recomputed, until the new one arrives.
- A rated posting without a score gets its own hint, naming that it was rated before a pass scored it and offering the button.
- A score computed this way counts toward the correction counter like any other score; it is no pass, so it does not reset the counter.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `posting-pool`: new requirements for scoring one posting on request (its gates, its place in the counter, one scoring at a time); the pass requirement's "Nothing starts by itself" scenario names the single score.
- `web-ui`: new requirements for the hint on a rated posting without a score and for the score button (disabled cases, progress and result) on posting page and pool rows.

## Non-goals

- Scoring on intake or import (a later change).
- Changing what a pass scores or how the judge scores; the prompt and its inputs stay as they are.
- A background run model for single scores; it stays synchronous until that proves too slow.
- Scoring several selected postings at once.
- A provenance field on the stored score; the data schema does not change.

## Impact

- Backend: `triage/graph.py` (a single-posting scoring function reusing `_guard_ruling`), `triage/runs.py` (one slot shared by passes and single scores), `pool.py` (rows gain `unscreened`), `api/app.py` (new endpoint, `screening` on `GET /pool` and `GET /postings/{id}`, corrected `start_pass` docstring).
- API wire: two added fields and one new route; nothing removed or renamed.
- Frontend: `api.ts` (answer type, new fields), `test-fixtures.ts`, `components/posting` (score button with info icon), `views/PostingPage.tsx`, `views/PoolView.tsx`, with their tests.
- Tests: `test_api.py`, `test_triage_graph.py` or a new runs test, component tests, one e2e test.
- README pool workflow text; `docs/images/pool.png` is retaken, since each row gains a button.
