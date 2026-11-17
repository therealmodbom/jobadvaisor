# Design

## Context

The pool view filters client-side. `FILTERS` in `frontend/src/views/PoolView.tsx` keeps rows of `pool.rows`, which arrive in the server's rank order, and the text filter narrows them further. A rating or a score from a row button replaces that row in `pool.rows` in place, so no row moves until the pool loads again. The `touched` set keeps rows rated in the view inside „Noch nicht bewertet“ until the state filter changes. Every `PoolRow` carries what this change needs: `score` (integer 0-10 or null), `state` (`scored`, `unscored`, `excluded`, `held`), `label` (verdict and strength, or null) and `added_at`. An unreadable score file shows as `unscored` with a `score_problem`, and the pass scores it again (`triage/graph.py`). The keyboard handler (J, K, Enter) already walks `shown`, the list as rendered, and ignores keys while a `select` has focus.

Look and position are drawn in the Design artifact [Pool: Score-Bereich und Sortierung](https://claude.ai/artifact/JgVJS42vMhjcTwkAYmt76T): desktop by default, desktop with the range at 7 to 9 and sorted by score, and the phone at 390 × 844 with only „ohne Score“. Its approval is task 0.1, before any code.

An excluded or held row can carry a stored score: `pool.py` sets `state` from the rules as they are now and returns the stored score whatever the state, and `ScoreText` then shows the reason instead of the number.

## Goals / Non-Goals

**Goals:**
- Filter and order logic is pure, so Vitest can cover range, „ohne Score“, missing values and ties without rendering the view.
- A row the user is working on does not jump or vanish under their hand.

**Non-Goals:**
- No change to `GET /pool` or to the server's ranking.
- No new component library or dependency.

## Decisions

- **Native selects for the range and the sort.** „Score“ is a `fieldset` with two selects, „von“ and „bis“, each offering „ohne Score“, then 0 to 10. A third select, „Sortierung“, offers „Rangfolge“, „Score: höchster zuerst“, „Score: niedrigster zuerst“, „Deine Bewertung: beste zuerst“, „Deine Bewertung: schlechteste zuerst“, „Hinzugefügt: neueste zuerst“, „Hinzugefügt: älteste zuerst“. All three sit in one wrapping row with the text field, above the state buttons, and stack at phone width. Selects are keyboard-operable, open the system picker on a phone, and the existing `StatusControl` select gives their look. Alternative: a slider with two handles. Rejected, because the platform has no two-handle slider, and a hand-built one needs its own keyboard and ARIA handling and is hard to hit on a phone. Alternative: a key select plus a direction toggle. Rejected for now, because one select is one control and one decision. #11 (Pool: sort by several keys in a chosen priority) replaces it with a chain of keys anyway.
- **The range is a pair of steps.** „ohne Score“ is step −1 and the scores are 0 to 10. A row passes when the range is full (−1 to 10), or when it is `scored` and its score lies within the range, or when the range starts at −1 and the row is `unscored`. Only `state === 'scored'` counts as a score, for the range and the sort alike, so an excluded row with a stored 8 never lands in 7 to 9 or among the 8s, where the view would show its reason and no number. A „von“ above „bis“ moves „bis“ up to it, and a „bis“ below „von“ moves „von“ down, so the range is never empty by accident. Alternative: refuse the choice with a message. Rejected, because it costs a step and says nothing the moved value does not show.
- **Pure functions in `frontend/src/lib/pool-order.ts`.** `inRange(row, range)` and `sortRows(rows, sort)`, with the sort keys and the full range as constants. `sortRows` sorts a copy with the stable `Array.prototype.sort` and a comparator that puts missing values last in both directions, so ties keep the input's rank order. A row's score is its value only when it is `scored`. The rating's order is a fixed table: strong yes, plain yes, weak yes, weak no, plain no, strong no. A label without a verdict counts as missing. Alternative: keep everything inside `PoolView.tsx`. Rejected, because the view already holds about 570 lines and the comparator needs its own tests.
- **The order is computed from a snapshot.** The view keeps the rows as they were at the last load, sort change, state-filter change or range change, and sorts that snapshot. It then shows the current version of each row in the snapshot's order. A rating or a score in the view therefore changes the row but not its place. Under „Rangfolge“ this is today's behaviour. Alternative: sort `pool.rows` live. Rejected, because a row rated while sorted by rating would jump away while its reasons have focus.
- **`touched` also covers the range.** A row rated or scored in the view joins `touched`. It bypasses the range until the range or the state filter changes, and the text filter still applies to it, as it does today. The state-filter rule stays as it is: only „Noch nicht bewertet“, and only while the row is open. A status change still removes a row from views it no longer fits, with its announcement. A finished pass reloads the pool. Rows it scored then leave „ohne Score“, unless they are in `touched`.
- **Reset and reload.** „Filter zurücksetzen“ also sets the range back to full and leaves the sort as it is. Range and sort are plain component state, so a reload starts from the full range and „Rangfolge“.

## Risks / Trade-offs

- [The snapshot can show a stale order after a rating, for example a newly rated row sorted among the unrated ones] → intended, and stated in the spec. Changing the sort or a filter, or the next load, puts it in place.
- [„ohne Score“ and every numeric range hide excluded and held postings, which count as having no score] → they keep their own marks and stay visible under the full range. The spec states it.
- [Overlap with other open work on `PoolView.tsx` or `posting-pool/spec.md`] → before opening the PR, check `git worktree list` and `gh pr list`, and bring `origin/main` in with `git merge`.
- [The README screenshot shows the old filter bar] → not retaken here; #79 (Retake the README screenshots with a cheap script instead of a full scoring pass) retakes it.
