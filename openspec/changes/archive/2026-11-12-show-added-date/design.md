# Design

## Context

`GET /pool` rows carry `added_at` as an ISO timestamp with offset (`pool.py`, the `PoolRow` type in `api.ts`); real postings carry microseconds (`datetime.now(UTC)` at intake). `GET /postings/{id}` returns the posting's pool `row` with the same field. The frontend has no date formatter yet. The approved design puts the line above the title in the pool row and on the posting page, at 11 px in a grey with lower contrast than `muted-foreground`, and leaves company and place unchanged. Colours are theme tokens in `frontend/src/index.css`; `contrast.test.ts` checks named token pairs in both themes, because jsdom applies no stylesheet and axe cannot measure contrast there.

## Goals / Non-Goals

**Goals:**
- One formatter used by both places, so pool row and posting page cannot drift apart.
- Deterministic tests regardless of the machine's time zone, in vitest and in the e2e browser.

**Non-Goals:**
- No shared `PostingHeader` component: the two places differ in heading level and layout, and the shared part is one line.

## Decisions

- **Formatter in `lib/german.ts`:** `addedLabel(iso)` returns „Hinzugefügt 12.11.2026, 14:05“ from `Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeStyle: 'short' })`, in the runtime's time zone, which in the app is the browser's. `german.ts` already holds the app's German wording; a new `lib/date.ts` for one function would add a file without need. Alternative: a hand-built `DD.MM.YYYY, HH:mm` string from `Date` getters; rejected because `Intl` already gives the German form with zero padding.
- **Markup:** a `<p>` holding `<time dateTime={new Date(iso).toISOString()}>`, placed before the `h3` in the pool row and before the `h1` on the posting page. `toISOString()` gives a valid HTML datetime (at most three fraction digits) from the microsecond timestamps. A `p` before the heading keeps the heading's accessible name the title alone, which the component tests' and the e2e walkthrough's heading-name lookups rely on.
- **New token `subtle-foreground`:** light `#666D75` (4.7:1 on `background`, 5.2:1 on `card`), dark `#8E96A0` (6.0:1 on dark `background`, 5.3:1 on dark `card`). Both are below `muted-foreground`'s contrast (7.3:1 and 7.2:1 on `card`), so the line recedes in both themes. Exposed as the Tailwind colour `text-subtle-foreground`. Its pairs on `background` and `card` join `TEXT` in `contrast.test.ts`; if a computed value misses 4.5:1, the value moves, not the threshold. Alternative: reuse `muted-foreground`; rejected because the line would then weigh as much as company and place.
- **Size:** `text-[11px] leading-4`. Tailwind's `text-xs` is 12 px, larger than the approved design.
- **Test time zone:** `vite.config.ts` sets `TZ: 'Europe/Berlin'` in `test.env` (a spike with vitest 5.0.3 confirmed it takes effect and wins over a shell `TZ`), so the fixture `2026-10-10T07:12:00+00:00` reads „10.10.2026, 09:12“ on every machine and in CI. The e2e walkthrough opens its page with Playwright's `timezone_id="Europe/Berlin"`, which checks the browser-zone behaviour in Chromium.

## Risks / Trade-offs

- [11 px is small on a phone] → contrast stays at AA, and the browser check at 390 × 844 confirms it is legible.
- [`Intl` output differs between engines (for example a narrow space before the time)] → `de-DE` `medium`/`short` gives „12.11.2026, 14:05“ with plain spaces in Node 22; the unit test pins the exact string in Node, and the e2e assertion pins it in Chromium.
- [Overlap with PR #95 (Back up the data repository on a button press), which appends requirements to `openspec/specs/web-ui/spec.md`] → rebase after it merges and keep both appended blocks.
