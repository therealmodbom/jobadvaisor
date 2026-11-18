# Proposal

## Why

On `main`, the pass button „Neue Anzeigen bewerten (N)“ switches to a full rescore as soon as one correction is counted, while the hint beside it uses the user's thresholds and still says „Ranking passt gut“ (#38). The user saw 399 postings announced where only 36 had no score. There is also no way to rescore every posting on purpose, for example after a profile or model change, and several texts say „bewerten“ for the AI's scoring although „bewerten“ is the user's own rating (#75).

## What Changes

- The pass button becomes a split button. The main part runs the shown variant, and a menu beside it picks the other one. The two variants are „Anzeigen ohne Score scoren“ and „Alle Anzeigen neu scoren“. Picking a menu entry only switches the main part and never starts a pass.
- The default variant follows the hint. Below the thresholds it is „ohne Score“, and at or above them (hint „neu scoren sinnvoll“) it is „Alle“. A single correction no longer changes the default or the count. Both variants can be picked at any time.
- The default is computed again on every load of the pool. A variant picked by hand holds until the pool loads again (a page reload, or the reload after a pass) or the default itself changes.
- Each variant shows its own count, and below the button how many postings the shown variant scores at two model calls each, and whether it replaces existing scores.
- #38 (Pass-Button zählt nach einer Korrektur alles) wins where #75 (Alle neu scoren auf Wunsch) still says otherwise. #75's second acceptance criterion and its open question 2 assume a pass that rescores everything after corrections. Under #38, corrections change a pass only through the default.
- **BREAKING (internal API):** `next_pass` in `GET /pool`, in the rating answer and in the single-score answer changes from `{count, rescore}` to `{default, unscored, all}`. `POST /pool/passes` takes a required body `{"variant": "unscored" | "all"}`. The web UI is the only client.
- The correction counter keeps its window across passes over postings without a score, and only a pass over all postings starts it again. Every recorded pass in `pool.json` stores its variant, and older entries without one count as passes over all postings.
- UI texts that say „bewerten“ for the AI's scoring say „scoren“ or „Score“. Texts about the user's own rating keep „bewerten“.
- Look and position are settled in a Design artifact on the JobAdvAIsor design system, linked from `design.md`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `posting-pool`: modifies „Scoring pass on request“ (two variants), „Correction counter and hints“ (counter window, hint text „neu scoren sinnvoll“), „Quality measure per pass“ (records the variant), „Scoring one posting on request“ and „Single score counts like any score“ (both now say counter window); adds „Default pass variant“ and „Counter window“.
- `web-ui`: modifies „Pool view“ and „Score button progress and result“ (both name the pass button); adds „Pass button“, „Pass variant menu“ and „Scoring wording“.

## Impact

- Backend: `backend/jobadvaisor/pool.py` (`counter` window, `next_pass`), `api/app.py` (`POST /pool/passes` body, three `next_pass` answers), `triage/graph.py` (`store_scores` records the variant), `data/models.py` (`PoolPass.variant`) and the generated `schemas/pool.schema.json`.
- Frontend: `frontend/src/api.ts` (`NextPass`), `views/PoolView.tsx` (split button, menu, wording), `views/IntakeView.tsx`, `views/PostingPage.tsx` and `views/ChatView.tsx` (wording), `test-fixtures.ts` and the view tests. The menu uses the installed `radix-ui`; no new dependency.
- Tests: `test_pool.py`, `test_api.py`, `test_triage_graph.py` (the pass record), e2e `test_score_walkthrough.py`.
- README: the pool paragraph names the new button; `docs/images/pool.png` and `docs/images/posting.png` are retaken with `scripts/readme_images.py`.
- Data format: `pool.json` gains an optional field. Existing files stay valid.

## Non-goals

- Scoring right after a posting is added: #36 (Score a posting right after it is added).
- Starting a pass automatically or on a schedule.
- The agent tool `rescore_postings`, which keeps its behaviour.
- A measure of agreement between score and rating over all rated postings (#75, open question 3). It is a separate topic.
- Keeping a hand-picked variant across a reload.
- No LLM-backed behaviour changes, so no eval.
