# Proposal

## Why

The pool and the posting page do not show when a posting entered the app, so the user cannot tell which of several postings is the newest (#46). Each posting already carries `added_at` and both `GET /pool` rows and `GET /postings/{id}` return it; the frontend never renders it. A list import adds many postings on one day, so a date alone does not answer the question.

## What Changes

- Each pool row shows a small line above its title: „Hinzugefügt 12.11.2026, 14:05“, date and time in the browser's time zone.
- The posting page shows the same line above its title.
- The line uses a new secondary text colour (`subtle-foreground`) at 11 px, with lower contrast than company and place, so it reads as additional information. It still meets WCAG AA contrast in both themes.
- The app has no date display yet, so this format („TT.MM.JJJJ, HH:MM“) becomes the app's date convention, which #46 asks the date to match.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `web-ui`: adds four requirements: the added-date line in the pool rows and on the posting page, its German form, its time zone, and its look as secondary information.

## Impact

- Frontend: `frontend/src/lib/german.ts` (formatter), `frontend/src/views/PoolView.tsx`, `frontend/src/views/PostingPage.tsx`, `frontend/src/index.css` (new colour token), `frontend/src/contrast.test.ts`, `frontend/vite.config.ts` (test time zone), and the view tests.
- e2e: `backend/tests/e2e/test_score_walkthrough.py`.
- No backend code change, no API change, no data format change, no new dependency.

## Non-goals

- No change to sorting or filtering; the pool keeps its ranking.
- No relative form („vor 2 Stunden“): the text would change while the page is open.
- No publication date from the portal; that is #96 (Store the date a portal published a posting), and the line leaves room for it.
- No retake of `docs/images/pool.png` in this change, as an exception to the README screenshot rule in AGENTS.md: a retake needs a full scoring pass over the demo persona (about 32 minutes, cost unmeasured) for one small line. The picture is retaken with the script from #79 (Retake the README screenshots with a cheap script instead of a full scoring pass).
- No LLM-backed behavior, so no eval.
