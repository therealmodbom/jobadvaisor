# Proposal

## Why

A running scoring pass cannot be stopped, and its progress stands still until it ends. On `main` the pool view shows „Scoren läuft: 0 von 288“ for the whole pass, because `extract` and `score` each loop over the batch inside one graph node and the pass state is written only when the node ends (#18). Excluded and held postings count as done from the first step, so the count also jumps early and then stops (#81, step 3). The user has raised this three times. Each time the pass ran for minutes over a large pool, with no sign of where it stood and no way out except restarting the server.

## What Changes

- While a pass runs, `GET /pool/passes/{id}` reports its phase: checking, extracting features, scoring or storing. It also reports a separate count for extraction and for scoring, updated after every posting. Excluded and held postings are in neither count.
- The pool view shows the phase and the counts in place of the single „x von y“, for example „Merkmale lesen 12 von 80 · Scoren 0 von 80“.
- A cancel button sits beside the progress while a pass computes. Pressing it stops the pass after the posting it is working on, with no confirm step. The scores computed so far are stored. No thread is killed: the pass checks a flag between postings.
- `POST /pool/passes/{id}/cancel` asks a running pass to stop. While the pass finishes its current posting, `GET` reports that a cancel was requested. When the pass has stopped it reports the new status `cancelled`.
- A cancelled pass that scored at least one posting is recorded in `pool.json` like any pass, with what it scored, and marked as cancelled. Only a complete „Alle Anzeigen neu scoren“ pass restarts the counter window. A cancelled one leaves the window where it was.
- **BREAKING (internal API):** `GET /pool/passes/{id}` replaces `total` and `done` with `progress` (the phase and the two counts), and adds `cancel_requested` and `scored`. The web UI is the only client.
- The look and position of the progress line and the cancel button are settled in a Design artifact on the JobAdvAIsor design system and linked from `design.md`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `posting-pool`: modifies „Correction counter and hints“ (only a pass over all postings that is not cancelled restarts the counter) and „Counter window“ (a cancelled pass leaves the window alone). Adds „Pass progress per posting“, „Progress counts only postings a model sees“, „Cancel a running pass“, „Cancel only a running pass“ and „Record of a cancelled pass“.
- `web-ui`: modifies „Pool view“ (its „Start a pass“ scenario names the progress line and the cancel button). Adds „Pass progress line“, „Cancel button of a pass“, „No cancel while storing“ and „Result of a cancelled pass“.

## Impact

- Backend:
  - `triage/graph.py`: a cancel check and a progress report after each posting in `exclude`, `extract` and `score`; `store_scores` records a cancelled pass.
  - `triage/runs.py`: cancel flag, progress in memory, the status `cancelled`.
  - `api/app.py`: `read_pass` shape and the new cancel endpoint.
  - `data/models.py`: `PoolPass.cancelled`, plus the generated `schemas/pool.schema.json`.
  - `pool.py`: `counter` skips cancelled passes.
- Frontend:
  - `api.ts` (`PassState`).
  - `views/PoolView.tsx`: progress line, cancel button, handling of `cancelled`.
  - `test-fixtures.ts` and the view tests.
- Tests: `test_triage_graph.py`, a new `test_runs_pass.py`, `test_api.py`, `test_pool.py`, e2e `test_score_walkthrough.py`.
- Data format: `pool.json` gains an optional field. Existing files stay valid.
- Docs: the README pool paragraph and the AGENTS.md "Current state" section; an ADR for how progress and cancel reach the pass.

## Non-goals

- Bounded concurrency of the model calls and the time measurement (#81 (Scoring pass: phases and progress, and bounded concurrency after measuring), steps 1 and 2).
- A progress indicator on every page (#90 (Global progress indicator for running background jobs)). It will read the shape this change gives `GET /pool/passes/{id}`.
- Resuming a pass after a server restart. A restart still ends a running pass as `failed`.
- Cancelling a single score (`POST /postings/{id}/score`). It is one judge call and stays as it is.
- Changes to LLM-backed behaviour. The extractor and the judge get the same input as before, so no eval runs.
