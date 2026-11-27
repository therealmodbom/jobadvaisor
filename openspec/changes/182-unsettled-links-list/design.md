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
- Each row carries `in_run: true` when it is `waiting` and a run computes, and the answer names that run (`run_id`).
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

- `GET /unsettled-links` answers `{links: [{url, title, source, state, tries, added_at, last_tried_at, attempts, reason, in_run}], run_id}`, `run_id` the computing alert run or null. The client counts the badge from `links` without `in_run` rows, and disables the retry buttons while `run_id` is set.
- **A retry is a run:** „Erneut versuchen“ and „Alle erneut versuchen“ post the rows' links to `POST /alert-mails/runs` without `source`. Every link is in the list already, so D1 keeps each row's source and first date. No retry route of its own: the run, its cancel, its throttle and its list upkeep are the ones every alert run has. 409 `alert run in progress` names the computing run, as today, and the tab then shows that run's progress (the hook attaches to it), the pattern of „Mailbox check refused while an alert run computes“.
- **The entry cap of a run body** (`AlertRunBody`, today `alert_mail.MAX_ENTRIES` = 100, the finder's cap for one mail) would refuse „Alle erneut versuchen“ over 100 links with 422, while a mailbox finish has no cap. The body gets its own bound, `MAX_RUN_ENTRIES` = 1000, which still bounds the input at the trust boundary. Rejected: sending the retry in batches of 100 (a second run cannot start while the first computes) and a „first 100“ label (the user would have to press again for each hundred).
- `DELETE /unsettled-links` with the body `{url}` answers `{links}` (the list after the removal). Errors: 404 `not found`, 409 `link in run`. The link goes in the body because a URL as a path segment needs double encoding and a body keeps it whole.
- `POST /alert-mails/runs` takes an optional `source` in its body (`"paste"` by default). The run view sends `"mailbox"` when it stores a row of a mailbox run anyway. `MailboxChecks.finish` passes `"mailbox"`.
- **An unreadable or invalid `unsettled-links.json`** (a hand edit, a bad merge): `GET` and `DELETE /unsettled-links`, `POST /alert-mails/runs` and the finish of a pick list answer 503 `unsettled links unreadable` with the loader's one-line problem as `detail`. Nothing starts and no mail is marked. The frontend shows „Die Liste der offenen Links (unsettled-links.json) ist nicht lesbar. Es wurde nichts hinzugefügt.“ for a run, the same first sentence in the tab, and no badge.

### D8 Frontend

The approved design is the canvas [Offene Links (#182)](https://claude.ai/artifact/LA6KDXpz7UePRYrn5Ccjod), screenshots of the real app with a prototype in the components and fictional demo data. Its rules, as approved on 2026-11-27:

- **Rows:** neutral, with only the outcome word in colour, unlike the red rows of failed entries in the run view. The outcome comes first, then the title, the link and one muted meta line: source · „in n Läufen abgerufen“ (or „noch in keinem Lauf abgerufen“) · „offen seit <date>“ · „zuletzt <date>“. „Details: n Versuche“ keeps the run view's word for the attempts of the last try. A link not reached reads „Nicht gestartet“, the run view's word, capitalised like every outcome word of the list („Wartet“ too), while the run view keeps its lower-case state words.
- **Buttons:** „Alle erneut versuchen (n)“ in the list head, the only filled button; n is the number of links the press sends: every row of the list, at most the first 1000 (`MAX_RUN_ENTRIES`), since one run body takes no more. Each row has „Erneut versuchen“ and „Entfernen“ as outline buttons, stacked on the right, and at a phone's width below the text at full width. While an alert run computes, the retry buttons and the „Entfernen“ of waiting rows are disabled, each row with one info icon that gives the reason.
- **Badge:** a filled pill after the label of the tab and of the navigation item „Anzeige hinzufügen“. It counts the rows that need attention (no `in_run`), with no pill at 0.
- **A retry's run** replaces the list in the tab with the run view (`AlertRunView` with `RETRY_WORDS`, own run store), whose „Zurück zu den offenen Links“ returns to the list.

- **Route:** `#/offene-links` opens „Anzeige hinzufügen“ with the source „Offene Links“ chosen, like `#/importieren` opens „Liste“. So a run report can link there, and a reload keeps the tab.
- **View:** a new `UnsettledLinksView`, mounted by `IntakeView` like `MailboxView`.
  - Rows reuse `OriginalLink` (`components/posting.tsx`), `AttemptList` (`components/attempts.tsx`), `AttemptDetails` (`components/alert-run.tsx`, exported for it) and the outcome words of `RunRow` where they match.
  - „Entfernen“ removes at once and announces through a `role="status"` line.
  - The focus moves to the next row's „Entfernen“, else to the list's heading.
  - Disabled buttons pair with `WhyDisabled` (`components/why.tsx`), as elsewhere in the app.
  - The retry run uses `useAlertRun(runStore('jobadvaisor.retry-run', …))`, so a reload keeps it, like the mailbox run.
- **Count and freshness:** `useUnsettledLinks()` in `lib/unsettled-links.ts` reads `GET /unsettled-links` on mount, when the tab „Offene Links“ becomes the shown source, and whenever the window event `unsettled-links-changed` fires.
  - `App` and `IntakeView` show the count from it, and `UnsettledLinksView` its rows.
  - The run hook (`useAlertRun`) dispatches the event when its `runId` changes (a start or an `attach`, as a mailbox run enters), each time a poll shows more ended entries (`done` grew), and when the run leaves `running`. The view dispatches it after a removal. So the badge rises during a run as links fail, and `in_run` rows lose that mark once their entry ends.
  - Another device reads afresh when its app loads or the tab is opened. A device left open on the tab sees another device's run only on its next read; polling for that was rejected as cost for a single user.
  - Badge: a small pill after the label, hidden at 0. The accessible name reads „Anzeige hinzufügen, 12 offene Links“ (visually hidden text, not `aria-label`, so the visible label stays the name's start).
  - A shared hook or context in the app tree was rejected: the counter sits in `App` while the run hook sits deep inside `IntakeView`, and an event avoids threading a callback through both.
- **Texts** (`lib/alert.ts`):
  - `RunWords` stay strings and gain `listLink: boolean`. With it, `RunPanel` renders one link „Offene Links ansehen“ to `#/offene-links` after the `again` or `crash` text it shows, and `AlertRunView` renders the same link in the notice of a run the server no longer knows (`lost`). `MAILBOX_WORDS` and `PASTE_WORDS` set it; `RETRY_WORDS` does not, since its run shows in that tab already.
  - `MAILBOX_WORDS.again` and `PASTE_WORDS.again` say that the links not added are kept under „Offene Links“. `RETRY_WORDS.again` says that the links not added stay in the list, with no „again“ in it, since an attached run of another source may hold new links.
  - `MAILBOX_WORDS.lost` and `crash` stop promising that the next check offers the mails again.
  - `PASTE_WORDS.lost`, `crash` and `cancelled` keep the paste-again way and add the list.
  - The note below the pick list (`components/mailbox-pick.tsx`) changes per the spec.
  - `RunWords`' doc comment and `MAILBOX_WORDS`' comment follow.

## Risks / Trade-offs

- **One file write per ended entry.** A run of 100 entries writes the file about 100 times, and each write waits for a backup that holds `write_gate`. Each write is small and the fetches take seconds, so it is negligible. → No batching.
- **The retry buttons know only of alert runs**, not of a mailbox check reading mails: a retry during a check is fine, and a pick list finished meanwhile is refused with 409 as today. The canvas's info text says „ein Lauf oder eine Postfachprüfung“; the built text names only the run.
- **A link settled elsewhere stays listed** (single add, text or PDF from a failed row). → The user removes it. #169 and #166 add the ways to settle it from the list.
- **A row removed between the list read and the retry press** (another device, a hand edit) comes back as a new row with source `paste` and a new first date, since the retry posts without `source`. → Accepted: the link is not lost, only relabelled.
- **A per-entry write that fails** is retried once at the end of the run (D3). Only when that fails too does the row stay `waiting`, read as not reached, with the try not counted. → Logged. The link is not lost.
- **An invalid file after a hand edit blocks every run** until it is fixed (D7). → Accepted: the same holds for `mailbox.json`, and the error names the file and the problem.
- **The existing live data:** mails that today come back for failed links are unmarked and hold no row. → The first check after the deploy offers them once more. Finishing that pick list marks them handled, and their failing links land in the list. No migration step.

## Migration Plan

- Deploy as usual. The file appears with the first run after the deploy. There is no data migration: a missing file is an empty list, and `mailbox.json` keeps its format.
- Rollback: an older release ignores `unsettled-links.json`. Mails marked under the new rule stay handled, so their unsettled links then exist only in that file until the release returns.

## Evaluation

No LLM-backed behavior changes, so no eval. Regression tests only: the writer, `AlertRuns` (start, per entry, end, the read rule, removal), `MailboxChecks.finish`, the routes, the frontend view, badge and texts, and the e2e walkthrough.
