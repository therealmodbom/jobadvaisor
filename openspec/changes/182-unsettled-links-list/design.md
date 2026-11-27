# Design

## Context

See proposal.md (Why). Today `MailboxChecks.finish` (`intake/mailbox_checks.py`) marks the mails with no link in the run at once and hands the others to `_marks_at_end`, the `on_end` hook of `AlertRuns.start` (`intake/alert_runs.py`), which marks a mail only when all its links ended `ENDED_WELL`. Run state lives in memory only. A pasted mail's run (`POST /alert-mails/runs`) starts without a hook. `mailbox.json` is read with `_read_entity` and written with `update_mailbox` under `write_gate` (`data/writer.py`); the backup holds `write_gate` from `git add` to the end of the commit.

Why the mail lets go of its links and the list is persisted in the data repository: [ADR 0020](../../../docs/decisions/0020-unsettled-links-kept-apart-from-their-mail.md).

## Goals / Non-Goals

**Goals:**
- Every link an alert run takes is in the list before any mail of its pick list is marked, and its row reflects the entry's outcome as soon as the entry ends.
- One owner of the list's upkeep for both sources, so a pasted run and a mailbox run keep it the same way.
- Leave room for #169 (Unsettled links, step 2: set a link's outcome by hand), #183 (Unsettled links, step 3: try a link again) and #166 (Unsettled links, step 4: remember links a run judged closed) without a format change: more states and fields can be added to a row.

**Non-Goals:**
- A row for a link settled another way: single add, text or PDF from a failed row, list import.
- A store interface or a second backend for the list.

## Decisions

### D1 The file and its row

`unsettled-links.json` in the data repository, model `UnsettledLinks` in `data/models.py`, one more entry in `ENTITIES` of `data/schemas.py`, schema regenerated. A missing file reads as an empty list. A JSON file like the other entities, not SQLite: ADR 0001 covers that (diffable, readable by hand and by agents, no binary in git).

```
UnsettledLinks: schema_version, links: list[UnsettledLink]
UnsettledLink:
  url            the cleaned link the run was given
  title          the entry's title (from the finder), at most 300 characters, cut
  source         "mailbox" | "paste"
  state          "waiting" | "unread" | "unclear" | "not_reached"
  tries          int >= 0
  added_at       aware datetime, when the row was created
  last_tried_at  aware datetime | null, when an entry with this link last ended
  attempts       [{step, outcome}] of the last try, empty when none
  reason         str | null, the last try's reason when no attempt was made, at most 200 characters, cut
```

- **Row key:** `normalize_url(url)`, computed, never stored. The writer keeps at most one row per key; a repeat in the file (a hand edit) keeps the first.
- **No address but the link:** a ladder attempt's `url` can be a redirect hop the link cleaning never saw, so it may carry a tracking token. The row keeps `step` and `outcome` only. An outcome with a variable tail (`connection failed: …`, `browser failed: …`, `fetch failed: …`; the browser's message names the navigated address) is cut to its prefix, the same prefixes `REASON_PREFIXES` in `components/attempts.tsx` already shows without the tail. The run view still shows the hop while the run is in memory. Rejected: storing the hop's URL or the full message for #173 (Failed entry: show why, retry it, and tell a model or budget problem apart). The prefix says why the link failed, the hop does not.
- **Bounded free text:** `title` comes from the request body and `reason` from an exception's text, so both are cut (300 and 200 characters) before they are stored. A longer value never refuses the run.
- **States:**
  - `unread` is a `failed` entry without `unclear`, also one with only a `reason`, which the run view already shows as „Nicht gelesen“.
  - `unclear` is a `failed` entry with `unclear: true`.
  - `not_reached` is a link the run never ended.
  - Later steps add states (#169: set by hand) without touching these.
- **A link taken again:** a run that takes a listed link again sets `state: waiting` and overwrites `title` (the latest mail names the posting best). It keeps `url`, `source`, `tries`, `added_at`, `last_tried_at`, `attempts` and `reason`, so a row that ends not reached again still shows its last real try. `source` stays the first one: a store-anyway run from a mailbox run's row goes through the paste route, and must not relabel the row.

### D2 Writer functions

`read_unsettled_links(root)` and `update_unsettled_links(root, change)` in `data/writer.py`, the `read_mailbox`/`update_mailbox` pattern: `change(current)` runs under `write_gate`, the result is validated again and swapped in by rename. Every mutation below is one `change` function, so a run's writes, a removal and a backup never interleave.

### D3 `AlertRuns` owns the upkeep

`AlertRuns` gets the data repository root from its `intake` and keeps the list itself. That way a mailbox run and a pasted run cannot drift apart. `start(entries, *, source)` takes the source as a required keyword (`"mailbox"` from `MailboxChecks.finish`, the body's `source` from the route), so no caller forgets it.

- **`start`:**
  1. Claims the slot under its lock, as today.
  2. Releases the lock and writes the list in one `change`. Every row still `waiting` (left by a run lost in a restart) turns `not_reached`. Then every distinct link of `entries` is upserted as `waiting`: a new row with `tries: 0` and `added_at: now`, or an existing row changed as D1 says for a link taken again.
  3. If that write raises, frees the slot, drops the state and re-raises (`DataRepositoryError` for an unreadable or invalid file), so nothing starts.
  4. Submits the worker.

  The write runs outside the lock because a backup can hold `write_gate` for seconds, and `read` (polled by the run view) must not wait for it.
- **After each fetched entry:** the worker applies the outcome in one `change`. `stored`, `duplicate` and `closed` drop the row. `failed` sets the state, `tries + 1`, `last_tried_at: now`, `attempts` and `reason`, and creates the row when it is missing (a hand edit or a pull removed it). An entry with `same_as` writes nothing: the fetched entry already counted. A write that raises is logged by its type, its link is kept in an in-memory set of the run, and the run goes on.
- **End of the run** (after the last entry, a cancel or a crash, in the worker's `finally`, before the slot is freed, like today's hook): one `change` over this run's links only. A link in the set of failed writes gets its outcome applied now. Every other link of the run still `waiting` turns `not_reached`. A link whose write failed twice stays `waiting` and reads as not reached (D4). A failure is logged. Running before the slot is freed keeps a new run's `waiting` rows out of reach, and limiting it to the run's links keeps it from touching rows no run holds.
- **`on_end` goes:** its only caller, `_marks_at_end`, goes with D5.
- **Lock order:** the `AlertRuns` lock is never held while `write_gate` is taken, and `current()` takes only that lock. So a `change` may call `current()` under `write_gate` (D6) without a cycle. `finish` holds the `MailboxChecks` lock while it calls `start`, which takes `write_gate` after releasing its own lock: `MailboxChecks` lock, then `write_gate`, as today.

### D4 Reading the list

`AlertRuns.unsettled()` answers the rows as the API serves them, so the rule about runs lives next to the runs.

- A row `waiting` while `current()` is `None` reads as `not_reached`, which covers a process that died mid-run. The start sweep (D3) covers a new run after such a restart.
- Each row carries `in_run: true` when it is `waiting` and a run computes.
- Order: most recent activity first (`last_tried_at`, else `added_at`).

Rejected: rewriting `waiting` rows at app startup. It needs a startup hook in the app factory for what one comparison at read time gives.

### D5 Marking in `finish`

`finish` keeps its checks and its order: validate, start the run (which writes the list), then mark.

- Every mail of the pick list that is not `read_failed` is marked at once: `handled`, or `waiting` when no model read it.
- `later`, `_marks_at_end`, `ENDED_WELL` and the `account` guard of `mark_mails` go. The guard was needed only because the marks landed at the end of the run, outside `MailboxChecks`'s lock. Now they land under it, where an account change also waits (`credentials()`).
- A `mark_mails` failure after the run started keeps today's handling: the pick list is closed, and the mails come again in the next check. Their links are in the list already. The next run then reports them as duplicates or tries them again.

### D6 Removal

`AlertRuns.remove(url)` drops the row with the same key in one `change`.

- It raises `LinkInRunError` when the row is `waiting` and `current()` is set, decided inside that `change`, so a run that starts meanwhile cannot interleave.
- It raises `KeyError` without a row.

### D7 API

- `GET /unsettled-links` answers `{links: [{url, title, source, state, tries, added_at, last_tried_at, attempts, reason, in_run}]}`. The client counts the badge from `links`.
- `DELETE /unsettled-links` with the body `{url}` answers `{links}` (the list after the removal). Errors: 404 `not found`, 409 `link in run`. The link goes in the body because a URL as a path segment needs double encoding and a body keeps it whole.
- `POST /alert-mails/runs` takes an optional `source` in its body (`"paste"` by default). The run view sends `"mailbox"` when it stores a row of a mailbox run anyway. `MailboxChecks.finish` passes `"mailbox"`.
- **An unreadable or invalid `unsettled-links.json`** (a hand edit, a bad merge): `GET` and `DELETE /unsettled-links`, `POST /alert-mails/runs` and the finish of a pick list answer 503 `unsettled links unreadable` with the loader's one-line problem as `detail`. Nothing starts and no mail is marked. The frontend shows „Die Liste der offenen Links (unsettled-links.json) ist nicht lesbar. Es wurde nichts hinzugefügt.“ for a run, the same first sentence in the tab, and no badge.

### D8 Frontend

The view is designed first as a Design artifact on the JobAdvAIsor Design System, before any UI code: the tab, a row in every state, the badge on the tab and on the navigation item, the empty list, and a phone's width. The design review confirms that the navigation item carries a badge, and decides the word for a not reached link („Nicht erreicht“, or the run view's „nicht gestartet“).

- **Route:** `#/offene-links` opens „Anzeige hinzufügen“ with the source „Offene Links“ chosen, like `#/importieren` opens „Liste“. So a run report can link there, and a reload keeps the tab.
- **View:** a new `UnsettledLinksView`, mounted by `IntakeView` like `MailboxView`.
  - Rows reuse `OriginalLink` (`components/posting.tsx`), `AttemptList` (`components/attempts.tsx`), `AttemptDetails` (`components/alert-run.tsx`, exported for it) and the outcome words of `RunRow` where they match.
  - „Entfernen“ removes at once and announces through a `role="status"` line.
  - The focus moves to the next row's „Entfernen“, else to the list's heading.
  - A row with `in_run` shows an info icon with the reason instead of the button.
- **Count and freshness:** `useUnsettledLinks()` in `lib/unsettled-links.ts` reads `GET /unsettled-links` on mount, when the tab „Offene Links“ becomes the shown source, and whenever the window event `unsettled-links-changed` fires.
  - `App` and `IntakeView` show the count from it, and `UnsettledLinksView` its rows.
  - The run hook (`useAlertRun`) dispatches the event when a run starts, each time a poll shows more ended entries (`done` grew), and when the run leaves `running`. The view dispatches it after a removal. So the badge falls during a run, and `in_run` rows lose that mark once their entry ends.
  - Another device reads afresh when its app loads or the tab is opened. A device left open on the tab sees another device's run only on its next read; polling for that was rejected as cost for a single user.
  - Badge: a small pill after the label, hidden at 0. The accessible name reads „Anzeige hinzufügen, 12 offene Links“ (visually hidden text, not `aria-label`, so the visible label stays the name's start).
  - A shared hook or context in the app tree was rejected: the counter sits in `App` while the run hook sits deep inside `IntakeView`, and an event avoids threading a callback through both.
- **Texts** (`lib/alert.ts`):
  - `RunWords` stay strings. `RunPanel` renders one link „Offene Links“ to `#/offene-links` after the `again`, `lost` or `crash` text it shows, so the words name the list and the panel owns the link.
  - `MAILBOX_WORDS.again` and `PASTE_WORDS.again` say that the links not added are kept under „Offene Links“.
  - `MAILBOX_WORDS.lost` and `crash` stop promising that the next check offers the mails again.
  - `PASTE_WORDS.lost`, `crash` and `cancelled` keep the paste-again way and add the list.
  - The note below the pick list (`components/mailbox-pick.tsx`) changes per the spec.
  - `RunWords`' doc comment and `MAILBOX_WORDS`' comment follow.

## Risks / Trade-offs

- **One file write per ended entry.** A run of 100 entries writes the file about 100 times, and each write waits for a backup that holds `write_gate`. Each write is small and the fetches take seconds, so it is negligible. → No batching.
- **The badge counts waiting links.** During a run of 100 entries it shows 100 and falls as links settle. → Accepted: they are open until they end. The design review can choose to count only ended rows.
- **A link settled elsewhere stays listed** (single add, text or PDF from a failed row). → The user removes it. #169 and #166 add the ways to settle it from the list.
- **A per-entry write that fails** is retried once at the end of the run (D3). Only when that fails too does the row stay `waiting`, read as not reached, with the try not counted. → Logged. The link is not lost.
- **An invalid file after a hand edit blocks every run** until it is fixed (D7). → Accepted: the same holds for `mailbox.json`, and the error names the file and the problem.
- **The existing live data:** mails that today come back for failed links are unmarked and hold no row. → The first check after the deploy offers them once more. Finishing that pick list marks them handled, and their failing links land in the list. No migration step.

## Migration Plan

- Deploy as usual. The file appears with the first run after the deploy. There is no data migration: a missing file is an empty list, and `mailbox.json` keeps its format.
- Rollback: an older release ignores `unsettled-links.json`. Mails marked under the new rule stay handled, so their unsettled links then exist only in that file until the release returns.

## Evaluation

No LLM-backed behavior changes, so no eval. Regression tests only: the writer, `AlertRuns` (start, per entry, end, the read rule, removal), `MailboxChecks.finish`, the routes, the frontend view, badge and texts, and the e2e walkthrough.
