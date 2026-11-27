# Proposal

## Why

Since #159 (Postings shown as closed after a single 404 are lost), a mail of a mailbox run counts as handled only when every link of it in the run ended stored, as a duplicate or closed. A link that ends „Nicht gelesen“ or „Nicht beurteilbar“, often a rate-limited LinkedIn link, keeps its mail open, so every check offers the whole mail again, fetches the same link again and spends one of its `max_mails` places on it ([#175 (Unsettled links: a list of their own, so their mail counts as handled)](https://github.com/therealmodbom/jobadvaisor/issues/175)). The way out, leaving the entry unticked in the next pick list, does not work: by then the user cannot tell which entry failed.

Marking the mail handled at once is only safe when the unsettled links are kept elsewhere. This change is [#182 (Unsettled links, step 1: a stored list, and the mail counts as handled)](https://github.com/therealmodbom/jobadvaisor/issues/182), the first step of #175: a stored list of the links a run could not settle, so their mail can let go of them.

## What Changes

- **A mail counts as handled once its entries went into a run.** Finishing the pick list marks every mail of it handled (or waiting, when no model read it because screening is off) as soon as the run has started, whatever its links' outcomes. A mail no longer comes back for a link that failed or was not reached. A mail whose read on request failed stays unmarked, as today.
- **A list of unsettled links in the data repository.** A new file `unsettled-links.json`, with its own JSON Schema, holds one row per link (compared after `normalize_url`): the link, the posting title the entry carried, the source (mailbox or pasted mail), its state, the number of tries, when it first entered the list and when it was last tried, and the last try's outcome detail (the ladder's attempts or a reason). It holds no sender, subject or mail text.
- **Every alert run keeps the list, from a mailbox or a pasted mail.**
  - When a run starts, each of its links enters the list as waiting, before any mail is marked, so a restart or crash cannot lose a link whose mail already counts as handled.
  - When an entry ends, its link leaves the list if it ended stored, as a duplicate or closed, and stays with its outcome otherwise: „Nicht gelesen“ (attempts, or a reason such as a refused model call) or „Nicht beurteilbar“.
  - A link the run did not reach (a cancel, a crash, a restart) shows as „Nicht gestartet“, the run view's word.
  - A link chosen again in a later run updates its row and counts one more try.
- **„Offene Links“ in the app.** A new source tab next to „Postfach“ under „Anzeige hinzufügen“ lists the unsettled links with outcome, title, link, source, runs, first and last try. The user can try one or all of them again, which starts a normal alert run shown in the tab, or remove a link. A count badge on the tab and on the navigation item „Anzeige hinzufügen“ shows how many links need attention. The approved design is the canvas [Offene Links (#182)](https://claude.ai/artifact/LA6KDXpz7UePRYrn5Ccjod).
- **Run and pick-list texts.** The run view of a mailbox run no longer says that the next check offers the mails again; it points to „Offene Links“, and so does a pasted run with unsettled entries. The note below the mailbox pick list says that every mail counts as handled once the run starts, and that links not read stay under „Offene Links“.

## Non-goals

- Setting a link's outcome by hand ([#169 (Unsettled links, step 2: set a link's outcome by hand)](https://github.com/therealmodbom/jobadvaisor/issues/169)), trying links again on their own, without a press ([#183 (Unsettled links, step 3: try a link again)](https://github.com/therealmodbom/jobadvaisor/issues/183), whose retry by hand moved here), remembering links judged closed ([#166 (Unsettled links, step 4: remember links a run judged closed)](https://github.com/therealmodbom/jobadvaisor/issues/166)) and the model verdict on an unknown page state ([#176 (Page state no rule knows: a model gives a verdict, the user confirms)](https://github.com/therealmodbom/jobadvaisor/issues/176)). The row shape leaves room for them.
- Settling a listed link through another route (a single link, pasted text or a PDF from the failed row, the list import): the row stays until the user removes it, or a later alert run settles it.
- Showing a listed link as such in a later pick list: it is offered like any new entry until #166.
- Metadata beyond title, source and dates (company, mail date): added once operation shows a gap.
- Clearing the list on a change of the mailbox account: the list is not tied to an account, since pasted links join it too.
- Persisting or resuming a run: run state stays in memory; only the list is persisted.
- Lifting the refusal of a mailbox check while an alert run computes: a finish could not start a second run anyway.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `data-repository`: modifies „Documented schema per entity“ (names the new entity); adds „Unsettled links stored in the data repository“ and „Unsettled links stored without mail text“.
- `posting-intake`:
  - Modifies „Handled mails“, „Mailbox entries added like alert entries“ and „Cancel an alert run“ (a mail counts as handled once the run has started).
  - Adds „Unsettled links kept in a list“, „Links a run did not reach“, „Tries of an unsettled link“, „No run while the list is unreadable“, „Unsettled link removed“ and „Unsettled links tried again by hand“.
- `web-ui`:
  - Modifies „Note on handled mails below the pick list“.
  - Removes „Mails offered again after a mailbox run“, replaced by „Unsettled links named after a run“.
  - Adds „Unsettled links tab“, „Row of an unsettled link“, „Unsettled links tab address and empty states“, „Count of unsettled links“, „Remove an unsettled link“ and „Try unsettled links again“.

## Impact

- **Data repository:** a new file `unsettled-links.json` and `schemas/unsettled-links.schema.json`. A missing file means an empty list. A backup counts it under other files.
- **Backend:**
  - `data/models.py`: `UnsettledLinks` and its row model. `data/schemas.py`: one more entity.
  - `data/writer.py`: read and update functions under `write_gate`, like `read_mailbox` and `update_mailbox`.
  - `intake/alert_runs.py`: `start` takes the source and writes the waiting rows before the worker starts; each ended entry updates its row; the end of the run and a later start turn leftover waiting rows into not reached.
  - `intake/mailbox_checks.py`: `finish` marks every mail of the pick list after the run started; `_marks_at_end` and `ENDED_WELL` go.
  - `api/app.py`: `GET /unsettled-links` (with the computing run's ID) and `DELETE /unsettled-links` (one link); a retry uses `POST /alert-mails/runs`; the run routes pass their source (`POST /alert-mails/runs` takes it as an optional body field); an unreadable list answers 503.
- **Frontend:** the tab and its list in `views/IntakeView.tsx` plus a new view with the retry buttons and its own run view, the badge in `App.tsx`, the texts in `lib/alert.ts` (`MAILBOX_WORDS`, `PASTE_WORDS`) and `components/mailbox-pick.tsx`.
- **Docs:** ADR 0020 supersedes the first two decisions of ADR 0019; `AGENTS.md` (Current state) and the README where the mailbox workflow is described.
- **Tests:** backend tests for the writer, runs and checks; frontend tests for the tab, badge and texts; the e2e walkthrough `test_mailbox_walkthrough.py`, whose disputed link no longer brings its mail back but lands in the list. If the navigation markup changes, the README images are retaken.
