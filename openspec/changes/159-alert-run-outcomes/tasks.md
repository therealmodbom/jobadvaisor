# Tasks

## 1. One link, one fetch (#161, D3)

- [ ] 1.1 In `AlertRuns._run`, fetch each `normalize_url` key once; a later entry takes the first entry's outcome fields and `same_as`, test first: two entries differing only in a tracking parameter give one `add_entry` call, the same state on both and `same_as: 0` on the second; with the first unreached after a cancel (task 4.1), the second stays `waiting`
- [ ] 1.2 In `MailboxChecks`, mark an entry whose link an earlier mail of the check offers with `offered_in: {key, sender, subject}` (in `_read_mail` and in `read_oversized`), and build `offered` in `finish` from `normalize_url`, test first: the spec scenario „Same posting in three mails“ over `FakeImap` with three fictional `.eml` mails; an oversized mail read on request with a link of another mail; `finish` accepts a link sent in another tracking form of an offered one and still refuses one not offered
- [ ] 1.3 Frontend: `offered_in` in `api.ts`, `locked` in `mailbox-pick.tsx` includes it, `PickRow` (`components/alert-pick.tsx`) shows „Auch in der Mail <Absender>, „<Betreff>“. Dort auswählbar.“, and the mail head's count leaves it out; verify with a component test for the spec scenario „Posting in two mails“ and with the add button's count

## 2. Closed only on undisputed evidence (#159, D1)

- [ ] 2.1 Rewrite `ladder.is_gone` and add `disputed` and `gone_disputed`, test first with attempt lists: a plain 404 followed by a rendered 429 and a loop 429 on the link is not gone and is `gone_disputed`; 404 and „no posting text“ is gone; the closed redirect next to a 5xx is gone; 404 on the link and 429 on another URL is gone; `HTTP 202`, `HTTP 403`, `connection failed: ConnectTimeout` and `browser failed: …` dispute
- [ ] 2.2 `add_entry` sets `unclear: true` on a failed outcome whose attempts are `gone_disputed`, test first: the spec scenario „One 404 among rate-limited answers“ with fake plain and rendered fetchers and a loop model that finds nothing; verify that single-link intake (`POST /postings` with a URL) answers that link as failed, not closed
- [ ] 2.3 List import: verify, test first, the scenario „Gone answer disputed“ (the row is `failed`, the intake loop was called) and that „Link answers gone“ with 404 on every request still gives `skipped_gone` with no loop call

## 3. Spacing and marking after the run (#159, D2, D4, D5)

- [ ] 3.1 Add `fetch.host_throttle`, wait on it in `_download_plain` before each request and in `download_rendered` before the navigation, and let `look_up` prefer it over `THROTTLE`; `AlertRuns` sets one 3 s `Throttle` around each entry. Test first with a fake clock: the spec scenarios „Two entries on one host“ and „Retry after a rate limit“, a fetch from the intake loop's tool thread is spaced, a company lookup after a stored entry on the same host is spaced, and intake outside a run does not wait
- [ ] 3.2 `AlertRuns.start(entries, on_end=None)` and `current()`: `on_end` runs after the last entry, after a crash and after a cancel, before the status leaves `running` and the slot is freed, and an exception in it is logged and frees the slot; verify with tests for each of the four
- [ ] 3.3 `finish` marks at once only the mails with no link in the run, and hands the others with their link sets to `on_end`, which marks a mail handled when all its links ended `stored`, `duplicate` or `closed`; `mark_mails` takes `account=(host, user)` and marks nothing for another account. Test first: the spec scenarios „Every entry stored“, „One entry failed“, „Failing entry left out“, „Restart during the run“ (the hook never runs), „Entries added“, a copy's mail follows the offered link's outcome, and an account change during the run marks nothing
- [ ] 3.4 `MailboxChecks.start` raises `AlertRunBusyError` while `AlertRuns.current()` is set, and `POST /mailbox/checks` answers 409 `alert run in progress` with `run_id`; verify with an API test for „Check during a run“, and that a check started after the run's end sees its marks
- [ ] 3.5 Frontend: a failed row with `unclear` shows „Nicht beurteilbar“ with its sentence, a row with `same_as` says the link was fetched once, the mailbox run's summary says the next check offers the mails of failed and unreached entries again (`RunWords.again`), the pick-list footer text follows the web-ui delta, and `MailboxView` shows `BusyRun` when „Postfach prüfen“ is refused; verify with component tests for the web-ui scenarios „Same link twice“, „One 404 among rate-limited answers“, „Failed entries after a mailbox run“ and „Check during a run“

## 4. Cancel an alert run (#153, D6)

- [ ] 4.1 `AlertRuns.cancel` and `RunNotRunningError`, the flag looked at before each entry, `status: "cancelled"` and `cancel_requested` in `read`, and `POST /alert-mails/runs/{id}/cancel` (202, 404, 409 `run not running`). Test first: the spec scenarios „Cancelled after some entries“, „Cancel a run that has ended“ and „Mails of a cancelled mailbox run“ (with `on_end` from task 3.3)
- [ ] 4.2 Frontend: „Lauf abbrechen“ in the run head while running, disabled as „Wird abgebrochen …“ after the press, the cancelled note „Abgebrochen nach N von M Anzeigen“ with `RunWords.cancelled` for paste and mailbox, unreached rows as „nicht gestartet“; verify with component tests for „Cancel a run“ and „Cancelled pasted run“

## 5. Whole-change checks

- [ ] 5.1 Extend the e2e walkthrough `test_mailbox_walkthrough.py`: two fictional mails share a link, one entry's fake fetch answers 404 and then 429, the run shows one fetch for the shared link and „Nicht beurteilbar“, and the next check offers the failed entry's mail again and not the other one; verify that the walkthrough passes
- [ ] 5.2 Run `uv run --directory backend pytest`, `uv run --directory backend ruff check`, `npm --prefix frontend test`, `npm --prefix frontend run build` and oxlint through `rtk proxy`, and click through a mailbox run and a pasted run in the browser: cancel, same link, „Nicht beurteilbar“, the refused check
- [ ] 5.3 README: update the mailbox and alert-mail section for the handled rule, the cancel and the slower runs; verify that the README names no real posting or sender
