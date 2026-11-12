# Tasks

## 1. Foundation

- [ ] 1.1 Set `TZ: 'Europe/Berlin'` in `test.env` of `frontend/vite.config.ts`; verify `npm test` still passes and a throwaway check of `new Date('2026-10-10T07:12:00+00:00').getHours()` inside a test gives 9
- [ ] 1.2 Test first, then add `addedLabel(iso, timeZone?)` with a docstring to `frontend/src/lib/german.ts`; verify unit tests for „Hinzugefügt 12.11.2026, 14:05“, two times on one day, and 23:30 UTC on 11 November shown as „Hinzugefügt 12.11.2026, 00:30“ in Europe/Berlin
- [ ] 1.3 Test first, then add the token `subtle-foreground` (light `#666D75`, dark `#8E96A0`) to `frontend/src/index.css` with its Tailwind colour, and its pairs on `background` and `card` to `TEXT` in `contrast.test.ts`; verify the contrast test passes in both themes

## 2. Views

- [ ] 2.1 Test first, then show the line (`<p>` with `<time dateTime>`, `text-[11px] leading-4 text-subtle-foreground`) above the title in the pool row in `frontend/src/views/PoolView.tsx`; verify a `PoolView.test.tsx` test finds „Hinzugefügt 10.10.2026, 09:12“ in the fixture row, that the title link's accessible name is still the title alone, and that row order is unchanged
- [ ] 2.2 Test first, then show the same line above the `h1` in `frontend/src/views/PostingPage.tsx` from `row.added_at`; verify a `PostingPage.test.tsx` test finds the same text as the pool row for the fixture, and the `h1` holds the title alone
- [ ] 2.3 Verify the existing axe checks (`test-axe.ts`) on the pool view and the posting page report no violations with the new line

## 3. Verification

- [ ] 3.1 Run in `frontend/` `npm run lint`, `npm test`, `npm run build`, and in `backend/` `uv run pytest -m e2e` against the build; all pass
- [ ] 3.2 Click through the built app in Chrome at desktop width and at 390 × 844 with the demo persona: the line shows above the title in the pool and on a posting page, same text in both, nothing in the row wraps differently from before, and the dark theme keeps it legible; report what the browser check cannot show
- [ ] 3.3 Decide whether `docs/images/pool.png` needs retaking (the row gains one small line); retake it with the demo persona only if the difference is visible at the screenshot's size, and record the outcome here
