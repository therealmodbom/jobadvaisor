## 1. Backend: shared scoring step and single score

- [ ] 1.1 Extract the pass's per-posting scoring (examples without the posting itself, then the judge) from the `score` node in `triage/graph.py` into one function both paths call; the node keeps its single index sync. Existing `test_triage_graph.py` stays green unchanged.
- [ ] 1.2 Add the single score in `triage/graph.py`: exclusion rules (`excluded` refusal with the rules), guard ruling (`held` / `unscreened` refusal, checking an unchecked posting when a classifier is configured, a checked one not again), index sync, shared step, `write_score` with `scored_at` now; no extraction, no pass appended. Tests: rated posting without a score gets one and its own ID is not in `example_ids`; an existing score is replaced; `pool.json` passes unchanged; excluded, held and unscreened refusals; a checked posting's guard is not called.
- [ ] 1.3 `Runs` (`triage/runs.py`): a method that runs the single score synchronously in the pass's `_computing` slot. Tests: single score during a computing pass raises `RunBusyError`; a pass started during a single score raises it; the slot is free again after a failing single score.

## 2. Backend: API

- [ ] 2.1 `POST /postings/{id}/score` in `api/app.py`: 200 with the `GET /postings/{id}` body plus `counter` and `next_pass`; 404 unknown; 409 `scoring in progress`, `excluded`, `held`, `unscreened`; 502 `scoring failed`. Tests in `test_api.py` with a fake judge, including the counter rising for a rated posting whose new score contradicts its rating (spec: "Probing a rated posting").
- [ ] 2.2 Pool rows gain `unscreened` (posting has no guard result; `pool._row`, `test_pool.py`), and `GET /pool` and `GET /postings/{id}` gain `screening` (classifier configured). Tests in `test_api.py` for both values.
- [ ] 2.3 Correct the `start_pass` docstring: unrated postings, not rated ones, are rescored after a correction.

## 3. Frontend

- [ ] 3.1 `api.ts`: the answer type, `unscreened` on `PoolRow`, `screening` on `Pool` and `PostingPageData`, and a `postScore(postingId)` helper.
- [ ] 3.2 `components/posting.tsx`: the call-state hook and the score button (label "Score berechnen" / "Neu berechnen", cost line, computing state, German message per error code with retry, disabled for `excluded`, `held` and unscreened-without-screening rows, with a visible, focusable info icon whose popover shows the reason on hover and focus). Component tests for each state and error code, each disabled reason, and the reason reachable via `aria-describedby`.
- [ ] 3.3 `PostingPage.tsx`: button in the score section; old score marked "wird neu berechnet" while computing; new score and reasoning from the answer; the hint for a rated posting without a score. Update `PostingPage.test.tsx:58` and add tests for the rated hint, re-score display and error.
- [ ] 3.4 `PoolView.tsx`: button on every row, disabled with the info icon in the three blocked cases; the answer replaces the row (keeping its `exploration` flag) and updates counter and next-pass figures. `PoolView.test.tsx`: row button updates score and counter; a "Stichprobe" row keeps its mark; excluded and held rows show it disabled with the info icon; 409 message on the row.

## 4. End to end and docs

- [ ] 4.1 e2e walkthrough in `backend/tests/e2e/` (real app over a temporary data repository, fake models, as `test_import_walkthrough.py`): score a rated posting without a score from its page, then see the score in the pool; re-score from a pool row.
- [ ] 4.2 Full suite (`env -C backend uv run pytest -q`, `ruff check .`, frontend tests and build, `pytest -m e2e`) and a click test in the browser on both views.
- [ ] 4.3 README pool workflow: name the button and its cost. Retake `docs/images/pool.png` per AGENTS.md (fresh demo copy, one paid pass, 1280 by 800, light mode).
- [ ] 4.4 `openspec validate score-posting-on-demand --strict` (sync again after any delta edit) and update the "Current state" section of AGENTS.md.
