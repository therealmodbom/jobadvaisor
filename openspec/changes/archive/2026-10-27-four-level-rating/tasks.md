# Tasks

Test first for every task that changes behavior: write the failing test, then the code. Backend suite: `env -C backend uv run pytest -q`; frontend: `npm --prefix frontend test` and `npm --prefix frontend run lint`. Do not run the paid evals.

## 1. Label model and schema

- [x] 1.1 Add `Label.strength` (`weak` | `strong` | null) with the check that a strength needs a verdict; `backend/tests/test_data_models.py` covers a label without strength (loads, strength None), each of the four levels, and a strength on `imported_not_preference` or without a verdict (rejected)
- [x] 1.2 Regenerate the schemas with `uv run python -m jobadvaisor.data.schemas` in `backend/`; `backend/tests/test_schemas.py` passes and `schemas/label.schema.json` lists the `strength` enum
- [x] 1.3 Confirm the writer omits an unset `strength` and the demo persona labels still load: `test_demo_persona.py` and the writer tests pass unchanged, plus one test that a label written without strength has no `strength` key in the file

## 2. API and pool

- [x] 2.1 `RatingBody.strength` and the `Label` built in `PUT /postings/{id}/rating`, with a 422 for a strength without a verdict (also when a chip would derive one) and the docstrings updated; `test_api.py` round-trips each of the four levels through `PUT` and `GET /pool` and `GET /postings/{id}`, a plain verdict after a level clears it, and the 422
- [x] 2.2 Carry `strength` in the pool row's `label` and rank strong, then no strength, then weak within the rated-positive group, without touching `_group`, `counter` or `best_open`; `test_pool.py` covers the order (the scenarios of the `posting-pool` delta), that "nein, eher nicht" stays in the negative group and is left out of `best_open`, and that the counter counts a weak negative on a score of 8 as one correction

## 3. Judge and agent

- [x] 3.1 Append the strength to the example line in `tools/scoring.py` only when set; a test asserts the line with strength (`positive (strong)`) and that a line without strength equals today's text exactly
- [x] 3.2 Add `strength` to the agent's `your_rating` and its other rating summaries in `agent/__init__.py`; tests with the existing fake model/tools assert the field is present for a label with strength and absent or null without

## 4. Frontend

- [x] 4.1 `api.ts` types (`Strength`, `Label.strength`, `RatingBody.strength`) and `lib/rating.ts`: `view` returns `strength`, `send` carries it through chip and note changes, a new `level` action sends verdict and strength together and does nothing for the level already shown; hook tests cover that a chip toggle and a note edit after a level resend the strength, and that a stored label without strength shows no chosen level
- [x] 4.2 One level table (key, label, verdict, strength) in `components/rating.tsx`; replace `VerdictButtons` by four buttons in the order "Ja, auf jeden Fall", "Ja, vielleicht", "Nein, eher nicht", "Nein, auf keinen Fall" with keys `1` to `4`, and update the `Legend`; `rating.test.tsx` (or the existing component test) asserts the labels, the pressed state per level and the shortcut legend
- [x] 4.3 `VerdictDisplay` in `components/posting.tsx` shows the stored level ("Ja" / "Nein" without strength) in place of "Interessant" / "Nicht für mich"; its test covers all four levels and the two plain ones
- [x] 4.4 Wire the four keys in `views/PoolView.tsx` (keyboard handling around the existing `1` / `2`) and the buttons in `views/PostingPage.tsx`; update `test-fixtures.ts` so the mock rating endpoint echoes `strength`; `PoolView.test.tsx` and `PostingPage.test.tsx` rate at all four levels by mouse and keys, check the level after a reload, that a chip never changes a level, and that typing `1` to `4` into the note field rates nothing

## 5. Docs, check and walkthrough

- [x] 5.1 Update `README.md` (rating levels, shortcuts, the label field) and the `rating-feedback` wording anywhere else it describes the two-button verdict; `grep` for "Interessant" and "Nicht für mich" in `frontend/src`, `README.md` and `docs/` leaves only historic text
- [x] 5.2 Run the full backend and frontend suites, `npm --prefix frontend run lint` and `npm --prefix frontend run build`, and `openspec validate four-level-rating --strict`; all pass
- [x] 5.3 Browser check from this worktree: start the backend and the Vite dev server on free ports (not 8710, the user's session), rate one posting at each level with the mouse and with `1` to `4`, reload and confirm the level, and confirm the pool ranks "auf jeden Fall" above "ja, vielleicht"; the demo persona is the data, never the user's data repository
- [x] 5.6 Review follow-up: ADR 0008 for the field-versus-wider-verdict decision with the design linking it, and the scoring eval's data and metric for the judge's new input: demo rating labels carry a derived strength, the eval report has `by_level`; `test_demo_persona.py` and `test_eval_scoring.py` cover both and the fixture still equals the generator output
- [x] 5.4 Parallel-work check again (`git worktree list`, `gh pr list`, `git diff --name-only origin/main...<branch>` per open branch) and rebase onto `origin/main` if a sibling PR touched `PoolView.tsx`, `PostingPage.tsx` or `agent/__init__.py`
- [x] 5.5 Open the PR (`create-pull-request`, description ends with its `Closes` line), then arm the follow-up monitor (`pr-monitor`, `--on comments`); do not merge, the user decides. After the PR merges, `openspec archive four-level-rating --yes` on a fresh branch from `origin/main` once `rated-pool` is archived, or independently of it (the deltas are additive)
