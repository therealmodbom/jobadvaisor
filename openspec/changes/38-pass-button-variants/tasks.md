# Tasks

## 0. Gate

- [x] 0.1 The user chooses a variant in the Design artifact [Pass-Button (#38, #75)](https://claude.ai/artifact/E8m3ddpZwF4XKBMhEDhJra); verify: the choice is noted here with its date and is in `design.md`. Variant B (split button) chosen on 2026-11-18; the same day the user decided that only a pass over all postings restarts the counter window.

## 1. Backend

- [ ] 1.1 Test first, then add `PoolPass.variant` (`"unscored" | "all" | None`, default `None`) and regenerate `schemas/pool.schema.json`; verify `test_schemas.py` passes and a `pool.json` without the field still loads
- [ ] 1.2 Test first, then make `counter` start its window at the last pass whose variant is `"all"` or `None`, and update its docstring; verify `test_pool.py` cases: a later `"unscored"` pass leaves the 4 corrections counted, an `"all"` pass resets them, a record without a variant resets them, no pass counts every rating
- [ ] 1.3 Test first, then make `store_scores` record `"all"` for a pass with `rescore` and `"unscored"` without it; verify `test_triage_graph.py` reads the variant from `pool.json` after both kinds of pass, and its quality measure equals the counter before the pass
- [ ] 1.4 Test first, then change `next_pass` to `{default, unscored, all}` with the default from the hint; verify `test_pool.py` cases: one correction below the threshold gives `default: "unscored"`, the threshold gives `"all"`, the rate gives `"all"`, both counts leave out excluded and held postings; replace the case that pins `> 0` (`test_next_pass_excludes_excluded_and_held_and_follows_corrections`)
- [ ] 1.5 Test first, then give `POST /pool/passes` the required body `{"variant"}` and drop its repository read. In `test_api.py`: give `ApiHarness.start` a `variant` parameter (default `"unscored"`) that it posts; rewrite `test_a_rating_counts_for_the_probe_only_after_the_last_pass_started` so its pass is `"all"`; replace the tests that pin `started == [False, True]` with the new rule. Verify `test_api.py` cases: `"unscored"` and `"all"` start passes with `rescore` false and true whatever the corrections, a missing or unknown variant answers 422 and starts nothing, a busy pass still answers 409, and the three `next_pass` answers (`GET /pool`, rating, single score) have the new shape
- [ ] 1.6 Update every remaining backend reference that `grep -rn --exclude=".env*" -e next_pass -e "/pool/passes" -e "rescore" backend` finds outside the agent tool `rescore_postings`, including the docstrings that state the old rule (`triage/graph.py` `start_run`, `triage/runs.py` `Runs.start`, `api/app.py` `start_pass`); verify `env -C backend uv run pytest -q` and `env -C backend uv run ruff check .` pass

## 2. Pass button

- [ ] 2.1 Change `NextPass` in `frontend/src/api.ts` to the new shape with its docstring, make `PoolView.tsx` read `next_pass[next_pass.default]` as an interim count, and change `test-fixtures.ts` to the new shape, with a `next_pass` parameter on `ratingAnswer`; verify `npm --prefix frontend run build` type-checks and `npm --prefix frontend test` passes
- [ ] 2.2 Test first, then build the split button in `PoolView.tsx` as `design.md` describes (main part, trigger, Radix menu with two radio items, cost line), with the jsdom stubs Radix needs in the Vitest setup; verify `PoolView.test.tsx` cases: below the thresholds the main part reads „Anzeigen ohne Score scoren (N)“ with „N Anzeigen ohne Score, je zwei Modellaufrufe.“; with hint `rescore` it reads „Alle Anzeigen neu scoren (M)“ with the replace note; „1 Anzeige“ for one; the menu, opened by keyboard, lists both with counts and costs and marks the shown one; choosing an entry switches the main part and sends no request; the main part sends `{"variant"}` of the shown variant
- [ ] 2.3 Test first, then clear a hand-picked variant on every pool load and when `next_pass.default` changes; verify `PoolView.test.tsx` cases: a pick survives a rating that leaves the default as it is; it is dropped when rating answers change the default and change it back; a picked „Alle“ is dropped when its pass ends and the pool reloads
- [ ] 2.4 Test first: disabled states; verify `PoolView.test.tsx` cases: count 0 for `unscored` disables the main part with „Es gibt keine Anzeigen ohne Score.“, count 0 for `all` with „Es gibt nichts zu scoren: …“, each linked by `aria-describedby`, while the trigger stays enabled; during a pass both parts are disabled; the existing axe checks report no violations

## 3. Wording

- [ ] 3.1 Change every text in the wording table of `design.md` in `PoolView.tsx`, `IntakeView.tsx`, `PostingPage.tsx` and `ChatView.tsx`, and the tests that name them; verify `npm --prefix frontend test` passes and `grep -rni --exclude=".env*" --exclude="*.test.tsx" bewert frontend/src` lists only the texts the table keeps
- [x] 3.2 Update the Design artifact boards to the counter label „Korrekturen seit dem letzten Neu-Scoren aller Anzeigen“ and the cost line with two model calls per posting; verify the artifact shows both on the B boards. Done 2026-11-18 in the spec phase

## 4. End to end

- [ ] 4.1 Test first, then update `backend/tests/e2e/test_score_walkthrough.py`: the existing pass test presses „Anzeigen ohne Score scoren (2)“. A new test sets `harness.judge` to a fixed score, opens the menu, chooses „Alle Anzeigen neu scoren“, checks that no pass started, presses the main part, and asserts that every posting neither excluded nor held now has the fixed score. It then chooses „Alle“ again, reloads the page with `page.reload()` and sees „Anzeigen ohne Score scoren“. Repeat the button check at 390 px width with no sideways scroll (`scrollWidth` not above `clientWidth`). Verify `env -C backend uv run pytest -m e2e` passes after `npm --prefix frontend run build`

## 5. Docs and verification

- [ ] 5.1 Update the pool paragraph in `README.md` (the two variants, the default from the hint, the counter window); verify no „Neue Anzeigen bewerten“ is left in `README.md` or `docs/`
- [ ] 5.2 Retake the README images with `uv run --directory backend python ../scripts/readme_images.py`; verify `docs/images/pool.png` shows the split button and the script exits 0
- [ ] 5.3 Run `npm --prefix frontend test`, `npm --prefix frontend run lint`, `npm --prefix frontend run build`, `env -C backend uv run pytest -q`, `env -C backend uv run ruff check .` and the e2e suite; all pass
- [ ] 5.4 Click through the built app in Chrome on a demo copy, at desktop width and at 390 × 844: both variants, the menu by keyboard and pointer, a pick dropped by a reload, the disabled main part with nothing to score; report what the browser check cannot show; never start a real pass against a configured model
- [ ] 5.5 Update the „Current state“ section of `AGENTS.md` with this change and drop its oldest entry; verify the section holds the last two changes
