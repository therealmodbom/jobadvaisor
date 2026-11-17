# Tasks

## 0. Gate

- [ ] 0.1 The owner approves the Design artifact [Pool: Score-Bereich und Sortierung](https://claude.ai/artifact/JgVJS42vMhjcTwkAYmt76T) (desktop, desktop with range and sort, phone); verify: the approval is noted here with its date, and any change it asked for is in `design.md` and the artifact

## 1. Order and range logic

- [ ] 1.1 Test first, then add `inRange(row, range)` and the full range to `frontend/src/lib/pool-order.ts`, with docstrings; verify Vitest cases: full range keeps excluded, held and unscored rows; 7 to 9 keeps 7, 8, 9 and drops 6, 10 and null; 0 to 0 keeps 0 and drops null; „ohne Score“ to „ohne Score“ keeps `unscored` rows (rated, unrated, with a `score_problem`) and drops excluded, held and scored ones; „ohne Score“ to 5 keeps `unscored` rows and scores 0 to 5
- [ ] 1.2 Test first, then add `sortRows(rows, sort)` and the sort keys to the same module; verify Vitest cases: ranking returns the input order; score both directions with nulls last both times; rating both directions in the order strong yes, plain yes, weak yes, weak no, plain no, strong no, with unrated (no label, and a label without a verdict) last both times; added date both directions; equal values keep the input order in both directions; the input array is not changed

## 2. Pool view

- [ ] 2.1 Test first, then add the „Score“ fieldset („von“, „bis“) and the „Sortierung“ select to `PoolView.tsx` as the design shows, with a „von“ above „bis“ pulling „bis“ up and the reverse; verify `PoolView.test.tsx`: range 7 to 9 lists only those rows, combined with a state filter and the text filter; „ohne Score“ only lists the unscored fixture rows; moving „von“ above „bis“ moves „bis“; focus stays on the select after a change
- [ ] 2.2 Test first, then show the rows in `sortRows` order over the snapshot (taken at load, sort, state-filter and range change) and extend `touched` to scored rows and to the range, as `design.md` describes; verify `PoolView.test.tsx`: sorted by rating, rating an unrated row leaves it in place until the sort changes; under „ohne Score“, a row scored by its button stays listed with its score until the range changes; after a finished pass the scored rows leave „ohne Score“; a „Stichprobe“ row sorted by score sits by its score and keeps its mark
- [ ] 2.3 Test first, then make „Filter zurücksetzen“ reset the range too and keep the sort; verify a `PoolView.test.tsx` case where a range shows no row, the reset lists the open rows again, and the sort select still shows its choice
- [ ] 2.4 Test first: J, K and Enter follow the sorted order; verify a `PoolView.test.tsx` case sorted by added date, ascending, where J moves from the earliest to the second earliest row and Enter goes to the next unrated row in that order; and a case that typing in the selects triggers no shortcut
- [ ] 2.5 Verify the existing axe checks on the pool view report no violations with the new controls

## 3. End to end

- [ ] 3.1 Test first, then add one e2e test to `backend/tests/e2e/test_score_walkthrough.py` that sets „von“ and „bis“ to „ohne Score“ and sees only the unscored posting, then resets the filters; verify `env -C backend uv run pytest -m e2e` passes after `npm --prefix frontend run build`

## 4. Verification

- [ ] 4.1 Run `npm --prefix frontend test`, `npm --prefix frontend run lint`, `npm --prefix frontend run build`, `env -C backend uv run pytest -q`, `env -C backend uv run ruff check .` and the e2e suite; all pass
- [ ] 4.2 Click through the built app in Chrome with the demo persona, at desktop width and at 390 × 844: the range, „ohne Score“, each sort, the reset, J/K in a sorted list, and the selects by keyboard alone; no sideways scroll on the phone; report what the browser check cannot show
- [ ] 4.3 Name the cost of retaking `docs/images/pool.png` (one scoring pass over a fresh demo persona copy, AGENTS.md → README screenshot) and retake it after the go; verify the picture shows the new filter bar, filtered to „Noch nicht bewertet“
- [ ] 4.4 Update the „Current state“ section of `AGENTS.md` with this change and drop its oldest entry; verify the section holds the last two changes
