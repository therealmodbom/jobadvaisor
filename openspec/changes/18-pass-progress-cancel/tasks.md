# Tasks

## 0. Look

- [ ] 0.1 Draw the progress line (checking, reading features, scoring, storing), the cancel button, the state after a cancel request and the result notice in a Design artifact on the „JobAdvAIsor Design System“, for desktop and phone. Link it in `design.md` → Context, with the owner's choice recorded. Verified when the link is in `design.md` and the owner has chosen.

## 1. Backend: the pass reports and stops

- [ ] 1.1 `TriageContext` gets the hooks `progress` and `cancelled` with defaults that report nothing and never cancel. Verify that `test_triage_graph.py`, `test_runs_score.py` and `test_eval_graph_vs_agent.py` pass unchanged.
- [ ] 1.2 `load`, `exclude`, `extract`, `score` and `store_scores` report the phase. `extract` and `score` report both counts after every posting, as `design.md` → The progress shape defines them. Verify with a test in `test_triage_graph.py` that records every report over a batch with one excluded, one held and one failed extraction, and checks the counts after each posting (spec: Pass progress per posting, Progress counts only postings a model sees).
- [ ] 1.3 `exclude`, `extract` and `score` ask `cancelled()` before every posting, stop with `cancelled: True` in the state, and route as `design.md` → Cancel describes. `store_scores` records the pass with `cancelled` and never asks the flag. Verify with graph tests where a recording fake sets the flag on the n-th call: a cancel in scoring stores the scores so far and records a cancelled pass; a cancel in reading features or checking stores nothing and records nothing; a cancel requested while storing ends as a complete pass.
- [ ] 1.4 `PoolPass.cancelled: Literal[True] | None`, and `counter` skips cancelled passes for the window. Regenerate `schemas/pool.schema.json`. Verify with `test_pool.py` (spec: Counter window, „Cancelled pass over all postings keeps the window“), a check that a pass that was not cancelled writes no `cancelled` key, and `test_schemas.py`.
- [ ] 1.5 `Runs`: `cancel(run_id)`, both hooks wrapped into the context for `start` and `answer_unscreened`, progress kept under the lock, `cancel_requested` and status `cancelled` in `read()`. Verify in the new `test_runs_pass.py` with a fake model that blocks on a `threading.Event`: progress readable mid-pass, cancel → `cancel_requested` → `cancelled`, `KeyError` for an unknown run, and `RunStateError` while awaiting the answer and after the end.
- [ ] 1.6 `read_pass` returns the new shape, and `POST /pool/passes/{id}/cancel` answers 202, 404 or 409. Verify with `test_api.py` through `ApiHarness`, including `score:<id>` → 404 and `scored` after a cancelled pass.

## 2. Frontend: the view shows and cancels

- [ ] 2.1 `PassState` in `api.ts` and `test-fixtures.ts` follow the new shape. Verify with `npm --prefix frontend run build` (type check).
- [ ] 2.2 The progress line shows the phase and both counts, as in the Design artifact. Verify with `PoolView.test.tsx`: the counts move between two polls, and checking shows no count (spec: Pass progress line).
- [ ] 2.3 The cancel button shows while the pass computes, not while it awaits the unscreened answer. It sends one request, then shows the pass stopping after the current posting. A 409 shows no error, and Enter on the focused button does not move the row selection. Verify with `PoolView.test.tsx` (spec: Cancel button of a pass).
- [ ] 2.4 `cancelled` clears the stored pass, reloads the pool and shows the notice with the scored count. Verify with `PoolView.test.tsx` for 30, 1 and 0 scored (spec: Result of a cancelled pass).

## 3. End to end and docs

- [ ] 3.1 The e2e walkthrough in `test_score_walkthrough.py` (scripted models) starts a pass, sees the counts move, cancels it, and sees the notice and the new scores in the ranking. Verify with `env -C backend uv run pytest -m e2e -q` after `npm --prefix frontend run build`.
- [ ] 3.2 Click test in Chromium on the built app with a demo copy and the e2e harness's scripted models: start, watch, cancel. Verify by screenshots attached to the PR description.
- [ ] 3.3 Update the README pool paragraph and the AGENTS.md "Current state" section. Retake `docs/images/pool.png` with `scripts/readme_images.py` only if the screenshot shows the change. Verify that the README describes cancel and phases, and that `git status` shows the images only if they changed.
- [ ] 3.4 Run every check: `env -C backend uv run pytest -q`, `env -C backend uv run ruff check .`, `npm --prefix frontend test`, `npm --prefix frontend run lint` and `npm --prefix frontend run build`. Verified when all of them pass.
