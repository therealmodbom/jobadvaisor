# Tasks

## 1. Foundation

- [ ] 1.1 Set `TZ: 'Europe/Berlin'` in `test.env` of `frontend/vite.config.ts`; verify `npm test` still passes (task 3.1 proves the setting with a run under `TZ=UTC`)
- [ ] 1.2 Test first, then add `addedLabel(iso)` with a docstring to `frontend/src/lib/german.ts`; verify unit tests for „Hinzugefügt 12.11.2026, 14:05“ from `2026-11-12T13:05:00+00:00`, for 23:30 UTC on 11 November shown as „Hinzugefügt 12.11.2026, 00:30“, and for a timestamp with microseconds (`2026-11-12T13:05:00.123456+00:00`)
- [ ] 1.3 Test first, then add the token `subtle-foreground` (light `#666D75`, dark `#8E96A0`) to `frontend/src/index.css` with its Tailwind colour, and its pairs on `background` and `card` to `TEXT` in `contrast.test.ts`; verify the contrast test passes in both themes

## 2. Views

- [ ] 2.1 Test first, then show the line (`<p>` with `<time dateTime={new Date(iso).toISOString()}>`, `text-[11px] leading-4 text-subtle-foreground`) above the title in the pool row in `frontend/src/views/PoolView.tsx`; verify a `PoolView.test.tsx` test with two rows added at `2026-11-12T08:41:00+00:00` and `2026-11-12T13:05:00+00:00` finds „Hinzugefügt 12.11.2026, 09:41“ in the first row and „Hinzugefügt 12.11.2026, 14:05“ in the second, that the line precedes the heading in the DOM, that the heading's accessible name is still the title alone, and that row order is unchanged
- [ ] 2.2 Test first, then show the same line above the `h1` in `frontend/src/views/PostingPage.tsx` from `row.added_at`; verify a `PostingPage.test.tsx` test finds „Hinzugefügt 10.10.2026, 09:12“ for the fixture (the same text the pool row shows), that the line precedes the `h1` in the DOM, and that the `h1` holds the title alone
- [ ] 2.3 Verify the existing axe checks on the pool view and the posting page (`PoolView.test.tsx`, `PostingPage.test.tsx`) report no violations with the new line
- [ ] 2.4 Test first, then open the e2e page in `backend/tests/e2e/test_score_walkthrough.py` with `browser.new_page(timezone_id="Europe/Berlin")` and assert „Hinzugefügt 05.01.2026, 10:00“ (fixture `added_at` `2026-01-05T09:00:00Z`) in the rated posting's pool row and on its posting page; verify `uv run pytest -m e2e` passes after `npm run build`

## 3. Verification

- [ ] 3.1 Run in `frontend/` `npm run lint`, `npm test`, `env TZ=UTC npm test`, `npm run build`, and in `backend/` `uv run pytest -m e2e` against the build; all pass
- [ ] 3.2 Click through the built app in Chrome at desktop width and at 390 × 844 with the demo persona: the line shows above the title in the pool and on a posting page, same text in both, company and place unchanged, and the dark theme keeps it legible; report what the browser check cannot show
- [ ] 3.3 Retake `docs/images/pool.png` per AGENTS.md (README screenshot): a fresh copy of `fixtures/demo-persona`, one scoring pass, 1280 × 800 viewport, light mode, filter „Noch nicht bewertet“. The scoring pass is paid (a few cents) and starts only on its own go; verify the new screenshot shows the line in each visible row
