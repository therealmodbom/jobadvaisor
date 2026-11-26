# Proposal

## Why

A mailbox run lists every entry in order, often well over a hundred, and its summary is only text. In a real run of well over a hundred entries, the few dozen that need an action (check the new ones, paste the text of the unread ones) could only be found by scrolling through all of them ([#162 (Run view: filter the entries by outcome)](https://github.com/therealmodbom/jobadvaisor/issues/162)).

Each closed or failed entry also lists every fetch attempt, up to eight nearly identical lines, which make up most of the page ([#158 (Run view: attempt list per closed or failed posting fills the page)](https://github.com/therealmodbom/jobadvaisor/issues/158)). One of those lines ends in English, „(no posting text)“, in an otherwise German view ([#160 (Run view: attempt line shows English „no posting text“)](https://github.com/therealmodbom/jobadvaisor/issues/160)). And the link of an entry, in the pick list and in the run, is plain text, so checking a „nicht beurteilbar“ entry on its page means copying the link by hand ([#120 (Alert mails: make the posting link clickable in the overview)](https://github.com/therealmodbom/jobadvaisor/issues/120)). All four change how the entries of an alert run are shown, and together they make a run of a hundred entries workable: filter to what needs action, see it compact, open its page.

The single add has the same gap one step later: its result links only the original ad, not the stored posting's page, so a „Schon gespeichert“ result cannot be checked against the posting the app matched ([#80 (Add page: link the stored posting to its internal posting page)](https://github.com/therealmodbom/jobadvaisor/issues/80)). The several-links result and the run already link there.

## What Changes

- **Filter a run by outcome.**
  - The run's summary becomes a row of filter buttons: „Alle (n)“ and one per outcome that occurs, with its count: hinzugefügt, schon gespeichert, geschlossen, nicht gelesen, nicht beurteilbar. Exactly one is active, „Alle“ at first; pressing the active one returns to „Alle“.
  - The row shows while the run computes too. Counts grow as entries end, and an entry that ends with the chosen outcome appears in the filtered list.
  - A filtered list shows only the entries with that outcome and no repeats of a link („Gleicher Link wie oben“), so the number shown matches the count. „Alle“ shows every row, repeats and entries not reached included.
  - A status line says what is shown („Zeigt 10 von 120 Anzeigen: nicht beurteilbar“) and is announced when it changes.
  - A row stored anyway from a text duplicate stays in the filtered list while it is fetched again and after, until the filter changes, so the row and the focus do not vanish under the user; the active filter stays, even at count 0.
- **Attempts behind „Details“.** A closed or failed entry shows its outcome, title, link, its explanation (closed: „Nichts gespeichert.“; „nicht beurteilbar“: why it is unclear) and its buttons. The attempts sit behind a collapsed „Details: n Versuche“, collapsed by default.
- **German attempt reasons.** Every reason an attempt can report shows in German in the attempt list; a plain HTTP code stays as it is. A reason the frontend does not know still shows as it came, instead of disappearing.
- **Clickable link.** In the pick list (pasted mail and mailbox) and in the run, an entry's link opens the posting's page in a new tab. Its accessible name names the posting and the new tab.
- **Link to the stored posting after a single add.** The result of a single add, new or „Schon gespeichert“, links to the posting's page („Anzeige ansehen“, as in the several-links result), next to „Anzeige öffnen“.

## Non-goals

- A filter for entries not started after a cancel; they stay under „Alle“.
- A more compact filter row at phone width: it wraps like the pool's filters, and a redesign of the filters is left for later.
- Setting an entry's outcome by hand ([#169 (Run view: set the outcome of a not read or not assessable entry by hand)](https://github.com/therealmodbom/jobadvaisor/issues/169)).
- A summary above a check's pick list ([#157 (Mailbox check: summary of the result above the pick list)](https://github.com/therealmodbom/jobadvaisor/issues/157)), remembering closed links ([#166 (Remember links judged closed across checks and runs)](https://github.com/therealmodbom/jobadvaisor/issues/166)), matching by title and company ([#167 (Recognise a stored posting from the mail's title and company before fetching)](https://github.com/therealmodbom/jobadvaisor/issues/167)), filtering the list import ([#92 (List import: filter the not-imported entries by reason)](https://github.com/therealmodbom/jobadvaisor/issues/92)).
- Collapsing the attempts of the single-link and several-links views: they keep their attempt lists open, and gain the German reasons through the shared attempt list.
- Any backend change: the reasons stay English on the wire.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `web-ui`:
  - Modifies „Alert mail run progress and outcome“ and „Entry that could not be judged“: the attempts are offered behind „Details“ instead of shown.
  - Adds „Run row attempts collapsed“, „Filter an alert run by outcome“, „Rows of a filtered run“, „Active filter announced“, „Filtered run while it computes“, „Row stored anyway keeps its place in a filtered run“, „Posting link in the pick list and the run“, „Attempt reasons in German“ and „Stored posting linked after a single add“.

## Impact

- **Frontend only:**
  - `components/alert-run.tsx`: the filter row and status line in `RunPanel`, the filtered rows, `RunRow` with the link and the collapsed attempts.
  - `components/posting.tsx`: `OriginalLink` names the posting for screen readers; `PickRow` (`components/alert-pick.tsx`) and `RunRow` use it. `mailbox-pick.tsx` uses `PickRow` and needs no change.
  - `components/attempts.tsx`: German reasons.
  - `views/IntakeView.tsx`: `IntakeResult` links to `#/anzeigen/<id>`.
  - Tests: `components/attempts.test.tsx`, `views/AlertMailView.test.tsx` (run view), `views/MailboxView.test.tsx` (summary), `views/IntakeView.test.tsx` (raw reasons, the link of a single add), `views/ImportView.test.tsx` (`rel`), the pick list tests, and the e2e walkthroughs `test_alert_mail_walkthrough.py` and `test_mailbox_walkthrough.py` where they read the summary or attempts.
- **Design:** approved canvas https://claude.ai/artifact/FLjijowheuanP61kDCif3c.
- **No ADR:** no decision here rejects a real alternative beyond the approved design.
- **No LLM behavior:** no eval.
