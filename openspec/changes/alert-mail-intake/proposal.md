# Proposal

## Why

Job boards and career sites send job alert mails that list several new postings each, and today every posting has to be copied into the intake view link by link. Pasting the whole mail should be enough: the app finds the postings it lists, shows them before anything is fetched, and adds the chosen ones through the existing intake. A plain paste into a text field keeps no link targets: the clipboard's plain-text part of a rendered mail holds no URL, so the view has to read the clipboard's HTML part.

## What Changes

- The intake view gains a fourth input, "Alert-Mail", next to link(s), text and PDF. Pasting a mail keeps its links by reading the clipboard's HTML part. A paste without HTML still works when the text prints the URLs.
- A finder returns the postings a mail lists as title and link, without fetching any page:
  - Fixed patterns read the link shapes of known senders: the LinkedIn job alert, the Bundesagentur für Arbeit job search alert, and the alert of a career-site platform many employers use. StepStone, named in #56 (find postings in an alert mail), is left for a later rule, since no sample mail was at hand.
  - A model reads every other mail, once the content guard has screened it. It sees the mail's visible text and the links' hosts and paths, never a query, and answers with link numbers, never with URLs. With screening off, only the fixed patterns read mails.
  - Only public http(s) links are offered. Footer, unsubscribe, settings, search, profile and "view in browser" links are not returned.
- Links taken from a mail lose their personal parameters (login and tracking tokens) before they are fetched, stored, logged or shown to a model. A pattern rebuilds the posting's URL from its ID. Any other link keeps only query parameters that name a posting. Two postings whose cleaned links coincide are marked, not merged.
- A pick list shows the found postings. New ones are preselected. Ones already stored are marked, linked to the stored posting and not selected, and so are ones on login-walled hosts. A LinkedIn job link is recognised as a stored posting by its job ID before any fetch, also in plain link intake.
- The pick list and the per-entry report are built for the mail. #57 (pasted alert text with pick list) proposed reusing the several-links input's list, but that input runs inside one long request and shows no progress, so a background run takes its place.
- The chosen entries are added in a background run, one after the other, through the existing intake (fetch ladder, intake loop, duplicate check, content guard, field filling). The view shows each entry's progress and outcome. A failed entry keeps the text and PDF options and does not stop the others.
- The content guard screens the mail text before the model sees it. A flagged mail reaches no model, and the view says the content guard held it. A failing classifier stops the reading, with a retry.
- The finder records, per mail, which pattern read it, or that the model did, with the hosts of its links. This is the groundwork for #109.
- A new eval reports postings found and links correct, per pattern and for the model fallback, on fictional alert mails.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `posting-intake`:
  - the input forms gain the alert mail;
  - new requirements cover the finder, the links it offers, the record of how a mail was read, the removal of personal link parameters, links that do not tell postings apart and the background run of the chosen entries;
  - duplicate detection recognises a LinkedIn job by its ID;
  - the content guard covers the mail text.
- `web-ui`: the intake view gains the alert-mail input; new requirements cover the paste that keeps links, the pick list, a held or failed reading, the progress and outcome of each entry, and a refused or lost run.
- `match-evaluation`: the list of LLM-backed behaviors that need an eval gains the finder's model fallback, and a new requirement names the finder's eval.

## Non-goals

- Reading alert mails from a mailbox (#58), and uploading a mail as an `.eml` file, which #58 can add.
- Moving the several-links input of the link source onto the background run; it keeps `POST /postings/batch`.
- Keeping a run across a server restart; its state lives in memory, like the list import's (#91).
- New sources for hosts that block automated access (#93), filtering the import report (#92), a global progress indicator (#90) and the date a portal published a posting (#96).
- Learning or proposing new sender patterns (#109). This change only records which pattern read a mail.
- Using the alert's title, company or place as the posting's fields. The fetched page supplies them, as for any link.
- Retrying a failed entry from the run's report. The user pastes the text, uploads a PDF, or pastes the mail again, where stored entries now show as duplicates.

## Impact

- Backend:
  - new `intake/alert_mail.py`: link extraction from HTML or plain text, patterns, link cleaning, model fallback and the finder's record;
  - new `intake/alert_runs.py`: the background run, on the pattern of `Imports`;
  - `intake/duplicates.py`: LinkedIn job ID key, which also applies to plain link intake and the list import;
  - `intake/postings.py`: a redirect target in `posting_urls` stored for mail entries only when cleaning would not change it;
  - `api/app.py`: `POST /alert-mails/preview`, `POST /alert-mails/runs`, `GET /alert-mails/runs/{id}`;
  - `evals/alert_mail.py` and its entry in `evals/__main__.py`.
- Fixtures: fictional alert mails as pasted HTML and plain text under `fixtures/intake/alert-mails/`, with expected entries.
- Frontend:
  - `views/IntakeView.tsx` gains the source;
  - a new `views/AlertMailView.tsx` holds the paste, the pick list and the run;
  - `api.ts` types and component tests.
- Tests: finder, cleaning, duplicates, run and API tests; one e2e walkthrough.
- README intake section; the stale LinkedIn question in #56 is updated.
- No data schema change, and no new dependency (stdlib `html.parser`).
