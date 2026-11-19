# Proposal

## Why

A running scoring pass cannot be stopped, and its progress stands still until it ends. On `main` the pool view shows „Scoren läuft: 0 von 288“ for the whole pass, because `extract` and `score` each loop over the batch inside one graph node and the pass state is written only when the node ends (#18). Excluded and held postings count as done from the first step, so the count also jumps early and then stops (#81, step 3). The user has raised this three times. Each time the pass ran for minutes over a large pool, with no sign of where it stood and no way out except restarting the server.

The pass also pays for a model call per posting that changes nothing. `extract` reads the features of every posting, but the judge does not receive them and `scores/<id>.json` does not hold them, so they are dropped when the pass ends. A failed reading even keeps a posting from being scored. A cancel during that phase would store nothing, although every call was paid. Storing features once per posting, for the readers that need them, is #126 (Extract features once per posting and store them).

## What Changes

- A pass no longer reads features. It checks the postings, scores each one that a model may see with one judge call, and stores the scores.
- While a pass runs, `GET /pool/passes/{id}` reports its phase: checking, scoring or storing. While it scores it also reports how many postings are done out of how many, updated after every posting. Excluded and held postings are not counted.
- The pool view shows the progress in the row of the pass button. While a pass computes, the pass button turns into a cancel button of the same width, and beside it a block names the phase, shows the count with a bar, and holds one hint line. Pressing the cancel button stops the pass after the posting it is working on, with no confirm step. The scores computed so far are stored. No thread is killed: the pass checks a flag between postings. After every swap the button ignores presses for about one second, so a double press neither cancels a pass it just started nor starts a pass that just ended.
- `POST /pool/passes/{id}/cancel` asks a running pass to stop. While the pass finishes its current posting, `GET` reports that a cancel was requested. When the pass has stopped it reports the new status `cancelled`.
- A cancelled pass that scored at least one posting is recorded in `pool.json` like any pass, with what it scored, and marked as cancelled. Only a complete „Alle Anzeigen neu scoren“ pass restarts the counter window. A cancelled one leaves the window where it was.
- **BREAKING (internal API):** `GET /pool/passes/{id}` replaces `total` and `done` with `progress` (the phase and the count), and adds `cancel_requested` and `scored`. The web UI is the only client.
- The look and position of the progress and the cancel button are settled in a Design artifact on the JobAdvAIsor design system and linked from `design.md`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `job-triage`: modifies „Fixed triage order“ (a pass makes no extraction call) and „Configurable feature extraction“ (extraction is available to the agent and the evals, not part of a pass).
- `job-agent`: modifies „Shared capabilities“ (the triage pipeline no longer uses extraction).
- `posting-pool`: modifies „Correction counter and hints“ (only a pass over all postings that is not cancelled restarts the counter) and „Counter window“ (a cancelled pass leaves the window alone). Adds „Pass progress per posting“, „Progress counts only postings a model sees“, „Cancel a running pass“, „Cancel only a running pass“ and „Record of a cancelled pass“.
- `web-ui`: modifies „Pool view“ (its „Start a pass“ scenario names the progress and the cancel button) and „Pass button“ (one model call per posting). Adds „Pass progress beside the pass button“, „Cancel button of a pass“, „No double press on the pass button“, „Focus stays in the pass button“, „No cancel while storing“ and „Result of a cancelled pass“.

## Impact

- Backend:
  - `triage/graph.py`: the node `extract` goes; `score` takes over its second guard ruling. A cancel check and a progress report after each posting in `exclude` and `score`; `store_scores` records a cancelled pass. `TriageContext` loses `extractor`.
  - `triage/runs.py`: cancel flag, progress in memory, the status `cancelled`.
  - `api/app.py`: `read_pass` shape, the new cancel endpoint, no extractor model for a pass.
  - `data/models.py`: `PoolPass.cancelled`, plus the generated `schemas/pool.schema.json`.
  - `pool.py`: `counter` skips cancelled passes.
- Frontend:
  - `api.ts` (`PassState`).
  - `views/PoolView.tsx`: the pass button's cancel state, the progress block, handling of `cancelled`, the cost line („je ein Modellaufruf“).
  - `views/PoolView.test.tsx` (its `pass()` fixture and the view tests).
- Tests: `test_triage_graph.py`, a new `test_runs_pass.py`, `test_api.py`, `test_pool.py`, e2e `test_score_walkthrough.py`.
- Data format: `pool.json` gains an optional field. Existing files stay valid.
- Docs: the README triage bullet and pool paragraph, and the AGENTS.md "Current state" section; an ADR for how progress and cancel reach the pass.

## Non-goals

- Storing features, or reading them anywhere a pass runs (#126 (Extract features once per posting and store them)).
- Bounded concurrency of the model calls and the time measurement (#81 (Scoring pass: phases and progress, and bounded concurrency after measuring), steps 1 and 2).
- A progress indicator on every page (#90 (Global progress indicator for running background jobs)). It will read the shape this change gives `GET /pool/passes/{id}`.
- Resuming a pass after a server restart. A restart still ends a running pass as `failed`.
- Cancelling a single score (`POST /postings/{id}/score`). It is one judge call and stays as it is.
- A new eval. The judge gets the same input as before. The extractor's input is unchanged too, and its evals still run it directly.
