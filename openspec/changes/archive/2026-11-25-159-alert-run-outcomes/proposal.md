# Proposal

## Why

A real alert run after a mailbox check showed hundreds of entries as „Stelle geschlossen“ whose fetches were mostly rate-limited, with a single 404 among them ([#159 (Postings shown as closed after a single 404 are lost)](https://github.com/therealmodbom/jobadvaisor/issues/159)). Their mails were marked handled when the pick list was finished, so a posting that was only rate-limited is lost for good, and nobody can tell which of the closed ones are right.

The same link often sits in several mails of one check, and each copy runs the whole fetch ladder and the intake loop again, which feeds the rate limiting and can end one link in two outcomes ([#161 (Same posting link in several mails of one check)](https://github.com/therealmodbom/jobadvaisor/issues/161)). And a run over well over 100 entries cannot be stopped ([#153 (Cancel a running alert run)](https://github.com/therealmodbom/jobadvaisor/issues/153)). All three change the alert run and the finish of a mailbox check, and #153 needs the same answer as #159 to the question of what happens to mails whose entries had no reliable outcome.

## What Changes

- **One link, one fetch, one outcome.**
  - A link that several mails of one check hold, compared after `normalize_url`, is offered once, in the first mail that holds it. Its copies in later mails are shown, marked with the mail that offers it, and cannot be selected.
  - A run fetches each link once, whatever entries it was sent. A later entry with the same link takes the first entry's outcome and says so.
- **Closed only on undisputed evidence.**
  - A link counts as closed only when an attempt on the link itself answered 404 or 410, or showed a closed rule's redirect or page text, and no attempt on that link was answered by the server with anything but such a closed answer or a page: no other HTTP status (429, 5xx, 202 and the like), no connection or browser failure.
  - A link with a closed answer and such a disputed answer is reported as failed and marked „nicht beurteilbar“, with the text and PDF options of a failed entry.
  - The rule lives in one function, so it also holds for a single link and for the list import. An import row with one 404 among rate-limited answers is now reported as failed instead of skipped as gone, and the intake looks for it elsewhere first, which costs intake loop model calls.
- **Spaced requests in an alert run.** During an alert run, every request to one host waits until the last one lies at least 3 seconds back, including the immediate retry after a 429 or 5xx, the intake loop's fetches and the company lookup. A run gets slower: from about 3 seconds for a LinkedIn entry read at the first fetch to about 30 seconds for one that needs the plain fetch, its retry, the rendered fetch and six loop fetches, so up to 90 minutes for 200 entries; repeated links cost nothing.
- **A mail counts as handled once its entries have a reliable outcome.**
  - Finishing the pick list no longer marks the mails whose entries go into the run. Once the run ends, a mail counts as handled when every link of its entries that went into the run ended stored, as a duplicate or closed. A mail with a failed or unreached link stays unhandled, and the next check offers it again; its entries stored meanwhile appear as already stored.
  - Entries the user did not select do not hold a mail back, so deselecting an entry that keeps failing releases its mail. A mail with no entry in the run counts as handled when the pick list is finished, as today.
  - The pick list says which mails count as handled afterwards.
  - **Side effect the user should know:** a mail that comes back is older than the new ones, so it takes one of the „Höchstens Mails pro Prüfung“ places first. Many mails coming back delay newer mails to a later check.
- **No mailbox check while an alert run computes.** „Postfach prüfen“ is refused while an alert run computes, and the view shows that run's progress. Otherwise a check could offer mails whose run has not ended.
- **Cancel an alert run.** While a run computes, the view offers „Lauf abbrechen“, without a confirm step. The run stops after the entry it works on. Entries stored before stay stored, the report says after how many of how many entries the run was cancelled, and the entries not reached show as not started. A mailbox run's unreached entries keep their mails unhandled, so the next check offers them again. A cancel is refused for a run that has ended.

## Non-goals

- Remembering a link judged closed across runs ([#166 (Remember links judged closed across checks and runs)](https://github.com/therealmodbom/jobadvaisor/issues/166)).
- Recognising a stored posting from the title and company a mail gives, before any fetch ([#167 (Recognise a stored posting from the mail's title and company before fetching)](https://github.com/therealmodbom/jobadvaisor/issues/167)).
- Resuming a cancelled run: run state stays in memory only.
- A per-entry retry button in the run view; the way back is the next check, or pasting the mail again.
- Spacing the requests of a list import or a single link.
- Waiting for `Retry-After`, a second request to confirm a 404, or skipping the intake loop while rate-limited (options 3 to 5 of #159).
- The run-view polish of #158, #160 and #162, and the list import's outcome taxonomy (#92).
- Restoring the entries that earlier runs reported as closed: there is nothing in the app to restore them from. `design.md` names the one-off step that makes the next checks offer those mails again.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `posting-intake`:
  - Modifies „Closed page at intake“ and „Closed postings are not imported“ (the evidence rule), and „Handled mails“, „Handled mails are skipped“, „Oversized mail read on request“ and „Mailbox entries added like alert entries“ (marking after the run).
  - Adds „Disputed gone answer“, „Requests in an alert run spaced per host“, „One link offered once per check“, „One fetch per link in a run“, „Cancel an alert run“ and „No mailbox check while an alert run computes“.
- `web-ui`:
  - Modifies „Mailbox pick list grouped by mail“ (points to the new note on handled mails).
  - Adds „Note on handled mails below the pick list“, „Same link in another mail of the pick list“, „Same link in a run“, „Entry that could not be judged“, „Mails offered again after a mailbox run“, „Cancel button of an alert run“, „Result of a cancelled alert run“ and „Mailbox check refused while an alert run computes“.

## Impact

- **Backend:**
  - `intake/ladder.py`: `is_gone` becomes the evidence rule; a helper names a disputed closed answer.
  - `intake/fetch.py`: a host throttle context variable that `download_plain` (each request) and `download_rendered` wait on; `company_facts.look_up` uses it when set.
  - `intake/alert_runs.py`: one fetch per normalized link, the `unclear` flag on a failed outcome, cancel, and an end-of-run callback.
  - `intake/mailbox_checks.py`: copies of a link marked in the pick list, `finish` compares by `normalize_url` and marks after the run, `start` refused while an alert run computes.
  - `intake/imports.py`: no code change beyond what `is_gone` brings; its tests change.
  - `api/app.py`: `POST /alert-mails/runs/{id}/cancel`; `POST /mailbox/checks` answers 409 `alert run in progress`.
- **Frontend:** `components/alert-run.tsx` (cancel, cancelled report, same-link and „nicht beurteilbar“ rows), `lib/alert-run.ts`, `components/mailbox-pick.tsx` and `components/alert-pick.tsx` (copies of a link), `views/MailboxView.tsx` and `lib/mailbox-check.ts` (the refused check), `api.ts`.
- **ADRs:** 0018 (closed only on undisputed evidence) and 0019 (a mail counts as handled by the outcome of its entries).
- **No new LLM behavior:** the rule, the spacing, the dedup and the marking are deterministic and get regression tests, no eval.
