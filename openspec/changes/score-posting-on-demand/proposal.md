# Proposal

## Why

A pass scores only postings without a verdict, and rescores only those. A rated posting therefore keeps the score from before its rating, and one rated before any pass scored it never gets a score at all; its page still promises that the pass will give it one. Yet seeing the AI score beside the user's own rating, for every posting, is what the app is for, and the comparison of the two is the measure of whether the scoring improves. New postings also keep arriving, and the user wants to score one directly, or check what the scoring makes of a posting, without starting a pass over the whole batch.

## What Changes

- A pass "Neue Anzeigen bewerten" scores every posting without a score, rated or not, and after corrections rescores every posting, rated or not. A rating given while a pass computes no longer keeps the old score.
- A pass's stored quality measure is taken against the scores from before the pass, so rescoring rated postings does not change it.
- A button "Score berechnen" on the posting page and on every row of the pool list scores this one posting now, rated or not, with or without a score. It names its cost per click (one judge call).
- The single score uses the pass's own steps (content guard ruling, synced label index, the posting's most similar rated postings as examples, the judge) and stores `scores/<id>.json`, replacing an earlier score, so pool, posting page and agent show it.
- `POST /postings/{id}/score` answers synchronously with what the posting page shows, plus the counter and next-pass figures.
- One scoring at a time: the button is refused while a pass or another single score computes, and a pass is refused while a single score computes.
- A posting an exclusion rule matches, the content guard holds, or the guard never checked while no classifier is configured, is not scored. Its button is disabled before any click, with a visible info icon that gives the reason.
- The posting page keeps the old score visible, marked as being recomputed, until the new one arrives.
- A score computed this way counts toward the correction counter like any other score; it is no pass, so it does not reset the counter.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `posting-pool`: the pass scores and rescores rated postings too, its quality measure uses the scores from before it, and new requirements cover scoring one posting on request (its gates, its place in the counter, one scoring at a time).
- `web-ui`: new requirements for the score button (disabled cases, progress and result) on posting page and pool rows.
- `job-agent`: a single score is a second way the pool's stored score changes, beside a pass.

## Non-goals

- A pass that rescores every posting on request, without corrections, and renaming the UI texts that say "bewerten" for scoring (a later change).
- An agreement measure of score against rating over all rated postings (a later change).
- Scoring on intake or import (a later change, which reuses this change's single-score function).
- Changing how the judge scores; the prompt and its inputs stay as they are.
- A background run model for single scores; it stays synchronous until that proves too slow.
- Scoring several selected postings at once.
- A provenance field on the stored score; the data schema does not change.

## Impact

- Backend:
  - `pool.py`: `pass_batch` takes rated postings, and `rescore_unrated` becomes `rescore`; rows gain `unscreened`.
  - `triage/graph.py`: `load` takes an explicit batch when given. `store_scores` drops the rated skip and measures against the scores from before. A single-posting scoring function reuses `_guard_ruling` and `pool._blocked`.
  - `triage/runs.py`: one slot shared by passes and single scores.
  - `api/app.py`: new endpoint, `screening` on `GET /pool` and `GET /postings/{id}`, corrected `start_pass` docstring.
  - `evals/graph_vs_agent.py`: passes its held-out batch explicitly.
- API wire: `next_pass.rescore_unrated` is renamed `rescore`; two fields and one route are added.
- Frontend: `api.ts` (answer type, new and renamed fields), `test-fixtures.ts`, `components/posting` (score button with info icon), `views/PostingPage.tsx`, `views/PoolView.tsx`, with their tests.
- Tests: `test_triage_graph.py`, `test_cold_start.py`, `test_pool.py`, `test_api.py`, component tests, one e2e test.
- README pool workflow text; `docs/images/pool.png` is retaken, since each row gains a button.
