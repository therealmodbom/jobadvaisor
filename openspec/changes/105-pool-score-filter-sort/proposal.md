# Proposal

## Why

The pool shows several hundred postings in the server's ranking, filterable only by state and text (#105). The user cannot narrow it to a score band ("everything scored 7 to 9"), cannot list the postings the AI has not scored yet (merged from #116), and cannot reorder it to see their best-rated or newest postings. Every pool row already carries `score`, `state`, `label` and `added_at`, so this needs no backend change.

## What Changes

- The pool gets a score range from „ohne Score“ through 0 to 10. „ohne Score“ is a step below 0 and selects the postings a scoring pass would still score. „0 bis 0“ means score 0. A range that starts at 0 or higher hides every posting without a score. The full range hides nothing.
- The pool gets a sort choice: the server ranking (default), score, the user's own rating and the added date, each ascending and descending. Postings without a value for the key come last in both directions. Ties keep the server ranking.
- The range and the sort combine with the state filters and the text search. „Filter zurücksetzen“ also resets the range, but not the sort.
- A posting rated or scored in the view keeps its place and stays listed until the user changes the state filter or the range. A finished pass reloads the pool, so scored postings leave „ohne Score“ then.
- Under a sort other than the ranking, „Stichprobe“ postings keep their mark but lose their fixed places.
- J, K and Enter follow the shown order. The controls work on a phone and by keyboard.
- Look and position are settled in a Design artifact on the JobAdvAIsor design system, linked from `design.md`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `posting-pool`: adds requirements for the score range, the sort choice and the place of changed postings, and modifies „Filters“ and „Exploration mark“ so they account for both.
- `web-ui`: adds a requirement that the range and sort controls sit with the filters, work on a phone and by keyboard, and that the keyboard follows the shown order.

## Impact

- Frontend: `frontend/src/views/PoolView.tsx` (filter, order, controls), a small pure module for the range and the sort with its own Vitest, `PoolView.test.tsx`, `test-fixtures.ts`.
- e2e: one click through the range control in the existing pool walkthrough.
- `docs/images/pool.png` is retaken if the filter bar changes visibly (paid scoring pass, a few cents; asked before it runs).
- No backend code change, no API change, no data format change, no new dependency.

## Non-goals

- Sorting by several keys in a chosen priority, and sorting by company or title: #11 (Pool: sort by several keys in a chosen priority).
- Sorting by the date of the last rating change: #102 (Show when a rating was last changed). The sort choice leaves room for it.
- Counts on the filter buttons: #73 (Pool filters show how many postings match each filter).
- Keeping the range or the sort across a reload. Neither survives one, like the existing filters.
- No LLM-backed behavior, so no eval.
