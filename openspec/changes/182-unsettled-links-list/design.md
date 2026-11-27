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
  title          the entry's title (from the finder)
  source         "mailbox" | "paste"
  state          "waiting" | "unread" | "unclear" | "not_reached"
  tries          int >= 0
  added_at       aware datetime, when the row was created
  last_tried_at  aware datetime | null, when an entry with this link last ended
  attempts       [{step, outcome}] of the last try, empty when none
  reason         str | null, the last try's reason when no attempt was made
```

- **Row key:** `normalize_url(url)`, computed, never stored. The writer keeps at most one row per key; a repeat in the file (a hand edit) keeps the first.
- **Attempts without their URL:** a ladder attempt's `url` can be a redirect hop the link cleaning never saw, so it may carry a tracking token. The row keeps `step` and `outcome` only. The run view still shows the hop while the run is in memory. Rejected: storing the hop's URL for #173 (Failed entry: show why, retry it, and tell a model or budget problem apart). The outcome says why the link failed, the hop does not.
- **States:**
  - `unread` is a `failed` entry without `unclear`, also one with only a `reason`, which the run view already shows as „Nicht gelesen“.
  - `unclear` is a `failed` entry with `unclear: true`.
  - `not_reached` is a link the run never ended.
  - Later steps add states (#169: set by hand) without touching these.
- **Title and source on a later run:** a run that takes a listed link again overwrites `title` and `source` with its own and keeps `added_at`. The latest mail names the posting best.

### D2 Writer functions

`read_unsettled_links(root)` and `update_unsettled_links(root, change)` in `data/writer.py`, the `read_mailbox`/`update_mailbox` pattern: `change(current)` runs under `write_gate`, the result is validated again and swapped in by rename. Every mutation below is one `change` function, so a run's writes, a removal and a backup never interleave.

### D3 `AlertRuns` owns the upkeep

`AlertRuns` gets the data repository root from its `intake` and keeps the list itself. That way a mailbox run and a pasted run cannot drift apart. `start(entries, source)` takes the source as a required keyword (`"mailbox"` from `MailboxChecks.finish`, `"paste"` from the route), so no caller forgets it.

- **`start`:**
  1. Claims the slot under its lock, as today.
  2. Releases the lock and writes the list in one `change`. Every row still `waiting` (left by a run lost in a restart) turns `not_reached`. Then every distinct link of `entries` is upserted as `waiting`: a new row with `tries: 0` and `added_at: now`, or an existing row with its `tries` and `added_at` kept.
  3. If that write raises, frees the slot, drops the state and re-raises, so nothing starts.
  4. Submits the worker.

  The write runs outside the lock because a backup can hold `write_gate` for seconds, and `read` (polled by the run view) must not wait for it.
- **After each fetched entry:** the worker applies the outcome in one `change`. `stored`, `duplicate` and `closed` drop the row. `failed` sets the state, `tries + 1`, `last_tried_at: now`, `attempts` and `reason`. An entry with `same_as` writes nothing: the fetched entry already counted. A write that raises is logged by its type and does not stop the run. The row stays `waiting` and reads as not reached afterwards (D4).
- **End of the run** (after the last entry, a cancel or a crash, in the worker's `finally`): every row still `waiting` turns `not_reached`. One run computes at a time, so these are this run's links. A failure there is logged, like the per-entry write.
- **`on_end` goes:** its only caller, `_marks_at_end`, goes with D5.
- **Lock order** stays `MailboxChecks` lock, then `AlertRuns` lock, then `write_gate`. `start` takes `write_gate` only after releasing its own lock, and `finish` already holds the `MailboxChecks` lock while it calls `start`.

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
- `POST /alert-mails/runs` passes `source="paste"`, and `MailboxChecks.finish` passes `"mailbox"`.

### D8 Frontend

The view is designed first as a Design artifact on the JobAdvAIsor Design System, before any UI code: the tab, a row in every state, the badge on the tab and on the navigation item, the empty list, and a phone's width. The design review confirms that the navigation item carries a badge, and decides the word for a not reached link („Nicht erreicht“, or the run view's „nicht gestartet“).

- **Route:** `#/offene-links` opens „Anzeige hinzufügen“ with the source „Offene Links“ chosen, like `#/importieren` opens „Liste“. So a run report can link there, and a reload keeps the tab.
- **View:** a new `UnsettledLinksView`, mounted by `IntakeView` like `MailboxView`.
  - Rows reuse `OriginalLink`, `AttemptList`/`AttemptDetails` (`components/attempts.tsx`) and the outcome words of `RunRow` where they match.
  - „Entfernen“ removes at once and announces through a `role="status"` line.
  - The focus moves to the next row's „Entfernen“, else to the list's heading.
  - A row with `in_run` shows an info icon with the reason instead of the button.
- **Count:** `useUnsettledLinks()` in `lib/unsettled-links.ts` reads `GET /unsettled-links` on mount and whenever the window event `unsettled-links-changed` fires.
  - `App` and `IntakeView` show the count from it.
  - The run hook (`useAlertRun`) dispatches the event when a run leaves `running`, and the view dispatches it after a removal.
  - Badge: a small pill after the label, hidden at 0. The accessible name reads „Anzeige hinzufügen, 27 offene Links“ (visually hidden text, not `aria-label`, so the visible label stays the name's start).
  - A shared hook or context in the app tree was rejected: the counter sits in `App` while the run hook sits deep inside `IntakeView`, and an event avoids threading a callback through both.
- **Texts** (`lib/alert.ts`):
  - `MAILBOX_WORDS.again` and `PASTE_WORDS.again` name „Offene Links“ and link to `#/offene-links`.
  - `MAILBOX_WORDS.lost` and `crash` stop promising that the next check offers the mails again.
  - `PASTE_WORDS.lost`, `crash` and `cancelled` keep the paste-again way and add the list.
  - The note below the pick list (`components/mailbox-pick.tsx`) changes per the spec.
  - `RunWords`' doc comment and `MAILBOX_WORDS`' comment follow.

## Risks / Trade-offs

- **One file write per ended entry.** A run of 128 entries writes the file about 130 times, and each write waits for a backup that holds `write_gate`. Each write is small and the fetches take seconds, so it is negligible. → No batching.
- **The badge counts waiting links.** During a run of 128 entries it shows 128 and falls as links settle. → Accepted: they are open until they end. The design review can choose to count only ended rows.
- **A link settled elsewhere stays listed** (single add, text or PDF from a failed row). → The user removes it. #169 and #166 add the ways to settle it from the list.
- **A per-entry write that fails leaves the row `waiting`**, read as not reached, with the try not counted. → Logged. The link is not lost.
- **The existing live data:** mails that today come back for failed links are unmarked and hold no row. → The first check after the deploy offers them once more. Finishing that pick list marks them handled, and their failing links land in the list. No migration step.

## Migration Plan

- Deploy as usual. The file appears with the first run after the deploy. There is no data migration: a missing file is an empty list, and `mailbox.json` keeps its format.
- Rollback: an older release ignores `unsettled-links.json`. Mails marked under the new rule stay handled, so their unsettled links then exist only in that file until the release returns.

## Evaluation

No LLM-backed behavior changes, so no eval. Regression tests only: the writer, `AlertRuns` (start, per entry, end, the read rule, removal), `MailboxChecks.finish`, the routes, the frontend view, badge and texts, and the e2e walkthrough.
