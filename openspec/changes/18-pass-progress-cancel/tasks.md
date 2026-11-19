# Tasks

## 0. Look

- [x] 0.1 The owner picks variant A or B in the Design artifact linked in `design.md` → Context, and the choice and its texts are recorded there. Verified when `design.md` names the chosen variant.

## 1. Backend: the pass reports and stops

- [ ] 1.1 `TriageContext` gets the hooks `progress` and `cancelled` with defaults that report nothing and never cancel. Verify that `test_triage_graph.py`, `test_runs_score.py` and `test_eval_graph_vs_agent.py` pass unchanged.
- [ ] 1.2 `load`, `exclude`, `extract`, `score` and `store_scores` report the phase. `extract` and `score` report both counts after every posting, as `design.md` → The progress shape defines them. Verify with a test in `test_triage_graph.py` that records every report over a batch with one excluded, one held and one failed extraction, and checks the counts after each posting (spec: Pass progress per posting, Progress counts only postings a model sees).
- [ ] 1.3 `TriageState` gains `cancelled: bool`. `exclude`, `extract` and `score` ask `cancelled()` before every posting, a cancelled node stops with `cancelled: True` and routes as `design.md` → Cancel describes, and `confirm_unscreened` turns the answer `"cancel"` into `cancelled: True` and `END`. `store_scores` records the pass with `cancelled` and never asks the flag. Verify with graph tests where a recording fake sets the flag on the n-th call:
  - a cancel in scoring stores the scores so far and records a cancelled pass;
  - a cancel in reading features or checking stores nothing and records nothing;
  - a cancel during checking over an unscreened posting ends as cancelled without the question;
  - a cancel during the last scored posting, or while storing, ends as a complete pass.
- [ ] 1.4 `PoolPass.cancelled: Literal[True] | None`, and `counter` skips cancelled passes for the window. Regenerate `schemas/pool.schema.json`. Verify with `test_pool.py` (spec: Counter window, „Cancelled pass over all postings keeps the window“), a check that a pass that was not cancelled writes no `cancelled` key, and `test_schemas.py`.
- [ ] 1.5 `Runs`: `cancel(run_id)` for every known pass ID and never for `score:<id>`, with check and add in one lock section. Both hooks are wrapped into the context for `start` and `answer_unscreened`. A step that ends paused at the question with a cancel pending is resumed with `"cancel"` before the slot is freed. The ID is cleared after that and at every step start. Progress is kept under the lock, and `read()` reports `cancel_requested` and the status `cancelled`. Verify in the new `test_runs_pass.py` with a fake model that blocks on a `threading.Event`:
  - progress readable mid-pass;
  - cancel → `cancel_requested` → `cancelled`;
  - a cancel accepted after `exclude`'s last check, with a hook that blocks until the cancel is in, ends `cancelled` without `awaiting_answer`;
  - a cancel sent while `_run`'s end section holds the lock (a saver wrapper whose `get_state` there starts the cancel thread and waits until it blocks on the lock) gets `RunStateError` once the section has freed the slot, and leaves no ID in the set, while the pass shows `awaiting_answer`;
  - `KeyError` for an unknown run and for `score:<id>` while a single score blocks;
  - `RunStateError` while awaiting the answer and after the end, also in a fresh `Runs` over the same saver;
  - a pass resumed with „Trotzdem scoren“ is not cancelled by an earlier request;
  - `progress` is `null` in a fresh `Runs` over the same saver.
- [ ] 1.6 `read_pass` returns the new shape, and `POST /pool/passes/{id}/cancel` answers 202, 404 or 409. Verify with `test_api.py` through `ApiHarness`, including `score:<id>` → 404 while that score blocks, and `scored` after a cancelled pass.

## 2. Frontend: the view shows and cancels

- [ ] 2.1 `PassState` in `api.ts` and the `pass()` fixture in `PoolView.test.tsx` follow the new shape. Verify with `npm --prefix frontend run build` (type check).
- [ ] 2.2 The progress line shows the phase and both counts, as in the Design artifact. Verify with `PoolView.test.tsx`: the counts move between two polls; checking and a `null` progress show no count; the running state has no axe violations (spec: Pass progress line).
- [ ] 2.3 The cancel button shows while the pass computes, not while it awaits the unscreened answer and not while it stores (spec: No cancel while storing). A press sends one request, and the button is disabled from the 202 on and says the pass stops after the current posting. A 409 shows no error, another failure shows its text, and Enter on the focused button does not move the row selection. Verify with `PoolView.test.tsx`, including an axe check of the cancel-requested state (spec: Cancel button of a pass).
- [ ] 2.4 `cancelled` clears the stored pass, reloads the pool and shows the result in the status region with the scored count, cleared when the next pass starts. Verify with `PoolView.test.tsx` for 30, 1 and 0 scored (spec: Result of a cancelled pass).

## 3. End to end and docs

- [ ] 3.1 The e2e walkthrough in `test_score_walkthrough.py` starts a pass, sees the counts move, cancels it, and sees the notice and the new scores in the ranking. Its scripted callable waits on a `threading.Event` the test releases, so the steps do not race the 1 s poll. Verify with `env -C backend uv run pytest -m e2e -q` after `npm --prefix frontend run build`.
- [ ] 3.2 Click test in Chromium on the built app with a demo copy and the e2e harness's scripted models: start, watch, cancel. Verify by screenshots attached to the PR description, and by the band's measured height, which is the same in checking, reading features, scoring, after a cancel request and while storing (spec: Pass progress line, „Same size in every phase“).
- [ ] 3.3 Update the README pool paragraph and the AGENTS.md "Current state" section. Retake `docs/images/pool.png` with `scripts/readme_images.py` only if the screenshot shows the change. Verify that the README describes cancel and phases, and that `git status` shows the images only if they changed.
- [ ] 3.4 Run every check: `env -C backend uv run pytest -q`, `env -C backend uv run ruff check .`, `npm --prefix frontend test`, `npm --prefix frontend run lint` and `npm --prefix frontend run build`. Verified when all of them pass.
