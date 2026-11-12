# Design

## Context

`GET /pool` rows carry `added_at` as an ISO timestamp with offset (`pool.py`, the `PoolRow` type in `api.ts`), and `GET /postings/{id}` returns the posting's pool `row` with the same field. The frontend has no date formatter yet. The approved design (link in proposal.md) puts the line above the title in both places, at 11 px in a grey lighter than `muted-foreground`. Colours are theme tokens in `frontend/src/index.css`; `contrast.test.ts` checks named token pairs in both themes, because jsdom applies no stylesheet and axe cannot measure contrast there.

## Goals / Non-Goals

**Goals:**
- One formatter used by both places, so pool row and posting page cannot drift apart.
- Deterministic tests regardless of the machine's time zone.

**Non-Goals:**
- No shared `PostingHeader` component: the two places differ in heading level and layout, and the shared part is one line.

## Decisions

- **Formatter in `lib/german.ts`:** `addedLabel(iso, timeZone?)` returns „Hinzugefügt 12.11.2026, 14:05“ from `Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeStyle: 'short', timeZone })`. `german.ts` already holds the app's German wording; a new `lib/date.ts` for one function would add a file without need. `timeZone` is undefined in the app (browser zone) and set only in its own unit test. Alternative: a hand-built `DD.MM.YYYY, HH:mm` string from `Date` getters; rejected because `Intl` already gives the German form with zero padding.
- **Markup:** a `<p>` holding `<time dateTime={iso}>`, placed before the `h3` in the pool row and before the `h1` on the posting page. `<time>` keeps the machine-readable value; screen readers read the visible text. A `p` before the heading keeps the heading's text the title alone, which the existing tests and the shortcuts' row lookup by `title-<id>` rely on.
- **New token `subtle-foreground`:** light `#666D75` (4.7:1 on `background`, 5.2:1 on `card`), dark `#8E96A0` (darker than dark `muted-foreground`, so it reads lighter in weight; about 5.3:1 on dark `card`). Exposed as the Tailwind colour `text-subtle-foreground`. Its pairs on `background` and `card` join `TEXT` in `contrast.test.ts`; if a computed value misses 4.5:1, the value moves, not the threshold. Alternative: reuse `muted-foreground`; rejected in the design review because the line then weighs as much as company and place.
- **Size:** `text-[11px] leading-4`, the approved size. Tailwind's `text-xs` is 12 px, which the design review found too large.
- **Test time zone:** `vite.config.ts` sets `TZ: 'Europe/Berlin'` in `test.env`, so component tests see the fixture `2026-10-10T07:12:00+00:00` as „10.10.2026, 09:12“ on every machine and in CI.

## Risks / Trade-offs

- [11 px is small on a phone] → the design review chose it knowingly; the contrast stays at AA, and the browser check at phone width confirms it is legible.
- [`Intl` output differs between engines (for example a narrow space before the time)] → `de-DE` `medium`/`short` gives „12.11.2026, 14:05“ in Node and Chromium; the unit test pins the exact string, and the e2e check reads it in Chromium.
- [Overlap with PR #95 (Back up the data repository on a button press), which appends requirements to `openspec/specs/web-ui/spec.md`] → rebase after it merges and keep both appended blocks.
