# Design

## Context

See `proposal.md` for the why. The state the design starts from:

- `ladder.is_gone(attempts, url)` is `any(...)` over the attempts on `url` with an outcome in `GONE_OUTCOMES` (404, 410, the closed redirect, the closed text). It decides `PostingNotFoundError.closed` in `add_from_url`, so it serves single-link intake, several links and alert runs. In `find_posting`, with `search_if_gone=False` (list import only), it also decides whether the intake loop runs.
- `fetch._download_plain` retries a 429, a 5xx or a transport error once, at once. The intake loop downloads through `download_plain` and `download_rendered` directly. `company_facts.look_up` fetches the employer's LinkedIn company page through its own `THROTTLE` (2 s). `closed_rules` and `guarded_link` are context variables that the ladder, the loop's tool threads and the lookup all see.
- `AlertRuns` runs one entry after the other on one worker thread, state in memory. It has no cancel, no dedup and no end hook.
- `MailboxChecks.finish` starts the run and marks every mail of the pick list handled under its lock, before any entry has an outcome. `offered` is compared by the exact cleaned URL.
- `preview` marks an entry stored by link through `normalize_url`, and nothing else ties entries of different mails together.

## Goals / Non-Goals

**Goals:**

- One rule decides "closed", in one function that every caller goes through.
- A mail's mark follows the outcome of its links, and nothing marks a mail before that outcome exists.
- Every request of an alert run to one host is spaced, wherever in the intake it is sent.

**Non-Goals:**

- Persisting run state: a restart still forgets a run. The marking is made safe for that instead (a mail stays unmarked).
- Spacing outside an alert run.

## Decisions

### D1. The evidence rule in `is_gone`

`is_gone(attempts, url)` becomes: the closed redirect or the closed text on `url` makes it gone outright. Otherwise a 404 or 410 on `url` makes it gone only when no attempt on `url` is disputed. A helper `disputed(outcome)` is true for `HTTP <n>` with `n` not in 200, 404, 410, and for the prefixes `connection failed` and `browser failed`. Only attempts whose `url` is the submitted link count, as today. "no posting text", a refused redirect and the login wall do not dispute. A second helper `gone_disputed(attempts, url)` says that a 404 or 410 is there but disputed, for the run's `unclear` flag.

The rule stays in `is_gone`, so `add_from_url`, `find_posting` and `imports.py` follow it without their own code. For the import this means a disputed row is no longer stopped before the intake loop, because `find_posting` gates the loop on the same function. That costs the loop's model calls for such rows, and is what a failed link gets anyway. The reason column for a disputed import row stays the last outcome on the link, as for any failed row.

Rationale and the rejected alternatives: [ADR 0018](../../../docs/decisions/0018-closed-only-on-undisputed-evidence.md).

### D2. Spacing through a context variable in `fetch`

`fetch.host_throttle: ContextVar[Throttle | None]`, default `None`. `_download_plain` waits on `throttle.wait(url_host(url))` before every `http.get`, including the retry. `download_rendered` waits once before the navigation, and the browser's own subresource requests are not counted. `look_up` uses `fetch.host_throttle.get() or THROTTLE`, so in a run the company page shares the run's throttle.

`AlertRuns` owns one `Throttle(HOST_SPACING_SECONDS)` (3 s, the constant of `availability.py`, moved to `company_facts.py` beside `Throttle` and imported by both) and sets the variable around each entry in its worker thread. The loop's tool threads see it the way they already see `closed_rules`, and a test proves that for a loop fetch.

Rejected: passing a throttle down through `add_from_url`, `find_posting`, the ladder and the loop. That touches every signature on the way for a value the context variables already carry. Rejected: a global throttle for every intake. It slows single links and imports, and the agreed scope is the run.

### D3. Dedup in the check and in the run

- **Check.** When `_read_mail` (or `read_oversized`) files a mail with entries, each entry whose `normalize_url` another mail already offers gets `offered_in: {key, sender, subject}`. Entries that keep no such field are the offered ones. `finish` builds `offered` from `normalize_url` of every entry, copies included, and compares the sent entries the same way. The frontend's `locked` adds `entry.offered_in`, and `PickRow` shows the note.
- **Run.** `AlertRuns._run` keeps `seen: dict[str, int]` from `normalize_url` to the index of the first entry. A later entry with a seen key gets the first entry's outcome fields and `same_as: <index>` and is not fetched. The first entry is always the one fetched. When the first ended unreached (a cancel), the later one is unreached too.
- One mechanism per layer: the check decides what is offered, and the run guarantees one fetch whatever it was sent (the paste route, `finish`, a raw request).

Known limit: a model-read click-redirect link shared by two different postings across two mails becomes one offer, and duplicate detection by URL treats them as one anyway. Within one mail, the ambiguity rule still applies.

### D4. Marking after the run

`AlertRuns.start(entries, on_end=None)`. `on_end(entries_state)` runs on the worker thread after the last entry, after a crash and after a cancel, outside the run's lock, before the run's status leaves `running` and before `_computing` is cleared. An exception in `on_end` is logged by type and never keeps the slot.

`finish`, under the check's lock as today:

1. Refuse and validate as today, with D3's `offered`.
2. Per mail of the pick list, the set of `normalize_url` of its entries that are in the run (copies included). A mail with an empty set, and not `read_failed`, is marked at once as today (handled, or waiting when `_waits`).
3. Start the run with an `on_end` that holds the refs and their link sets. When the run ends, it marks handled each mail whose links all ended `stored`, `duplicate` or `closed`, and leaves the others unmarked.

The end hook takes no lock of `MailboxChecks`. It holds the refs it was given and calls `mark_mails`, which takes the write gate. `finish` calls `AlertRuns.start` while it holds the check's lock, and the hook never takes that lock, so the order stays one way.

Account change during a run: `mark_mails(..., account=(host, user))` marks nothing when the stored account is another one, checked inside the gated read-modify-write. The new account's record stays fresh, and no refusal is needed.

Rationale and the rejected alternatives: [ADR 0019](../../../docs/decisions/0019-a-mail-counts-as-handled-by-the-outcome-of-its-entries.md).

### D5. No check while a run computes

`AlertRuns.current()` answers the computing run's ID. `MailboxChecks.start` raises `AlertRunBusyError` when it is set. The route answers 409 `{error: "alert run in progress", run_id}`, like `finish`. The frontend's `startCheck` treats it like the finish refusal: `MailboxView` shows `BusyRun` and offers the check again when that run ends. Because `on_end` marks before the slot is freed, a check started after the refusal ends sees every mark of the run.

Rejected: letting the check run and skipping the in-flight mails through a temporary skip record. That is more code for a state nobody needs, since a pick list finished during a run is refused anyway.

### D6. Cancel

Cancel mirrors `MailboxChecks.cancel`, not ADR 0013's hooks: there is no graph here, only a loop. `cancel(run_id)` sets `cancel_requested`, answers `None` for an unknown run, and raises `RunNotRunningError` for an ended one. `_run` looks at the flag before each entry, and ends `cancelled` with the rest left `waiting`. `read` adds `cancel_requested`, and `status` gains `cancelled`. The route is `POST /alert-mails/runs/{id}/cancel`: 202 `{run_id}`, 404, or 409 `run not running`.

Frontend readers of the run's status (`lib/alert-run.ts` `running`, `BusyRun`, `RunPanel`) treat everything but `running` as ended, so `cancelled` needs a new branch only in `RunPanel` (the note and the words), and the type in `api.ts`.

### D7. The run view

- `AlertRunEntry` gains `unclear?: boolean`, `same_as?: number` and, in the pick list, `offered_in?`.
- `RunRow`:
  - A failed row with `unclear` shows „Nicht beurteilbar“ and its sentence.
  - A row with `same_as` shows the outcome label and „Gleicher Link wie oben, nur einmal abgerufen.“ Its stored or duplicate link points to the same posting.
- `RunWords` gains `cancelled` (the paste and the mailbox wording) and `again` (mailbox only: „Die nächste Prüfung bietet die Mails dieser Anzeigen wieder an.“), shown in the summary when entries failed or were not reached.
- The cancel button sits in the run head while `status === 'running'`, „Lauf abbrechen“, then disabled as „Wird abgebrochen …“ once `cancel_requested`.
- The pick list footer text changes per the web-ui delta.

### D8. Evaluation

No LLM-backed behavior changes. The prompts, the finder and the intake loop stay as they are. The import now reaches the loop for disputed rows, which is the loop's existing behavior on a failed link. The rule, the spacing, the dedup, the marking and the cancel are deterministic and get regression tests in the default `pytest` and the frontend tests. No eval is added.

## Risks / Trade-offs

- [Truly closed postings behind a rate limit now end "nicht beurteilbar"] → The spacing makes clean 404 series more likely, the mail comes back, and the next check tries again. Each retry costs the run's time, not a model call, unless the loop runs.
- [Mails that keep failing return in every check and take `max_mails` places] → Deselecting the entry releases the mail; the proposal names the side effect. A later change can count returns if it matters.
- [Runs are slower: about 3 s per request on one host] → Dedup removes repeated links, and the cancel lets the user stop a long run.
- [A crash in `on_end` leaves the mails unmarked] → They come again, which is the safe direction; the log names the exception type.
- [`look_up` shares the run's throttle only through the context variable] → A test asserts the spacing between a posting fetch and its company lookup on the same host.

## Migration Plan

- No data migration. `mailbox.json` keeps its schema, and the API only adds fields and a route.
- **Rollout, once:** the entries that earlier runs reported closed cannot be recovered from the app. After the deploy, clearing the `handled` record in the data repository's `mailbox.json` (a commit on the data repository's `main`) makes the next checks offer those mails again. Their stored entries show as already stored, and only the closed and failed ones are fetched again under the new rule. Mails deselected earlier come back too, and with 200 mails per check this can take several checks.
- Rollback: the previous release reads the same files. Mails that a newer run left unmarked are offered once more there, and nothing is lost.
