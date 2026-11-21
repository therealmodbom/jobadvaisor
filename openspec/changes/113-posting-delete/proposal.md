# Proposal

## Why

A stored posting can be rated, closed or set to „erledigt“, but it can never be removed. Some records should never have existed: a job-board list page stored by mistake, a test entry, or a duplicate in the wrong form. Such a record stays in the pool, the ranking and every scoring pass, and its score and rating stay with it. The user acts only through the web app, so a script that deletes files is no answer ([#113 (Delete a posting permanently from the web app)](https://github.com/therealmodbom/jobadvaisor/issues/113)).

## What Changes

- The user deletes a posting from its pool row and from its page.
  - Both places show a button with a trash icon and no text.
  - On the pool row the button sits right of „Bewerbungsstatus“.
  - On the posting page it sits in the head row after „Verfügbarkeit“. On that row, „Bearbeiten“, both selects and the trash button share one height.
- Every delete asks first, in a dialog „Anzeige löschen?“.
  - The dialog names the posting's title and company.
  - For a rated posting it also names the rating, and says that the rating stops counting as a scoring example.
  - „Abbrechen“ has the focus. „Endgültig löschen“ deletes.
- The delete is permanent, with no trash step. Removed from the data repository:
  - the posting file;
  - its label (the rating);
  - its score;
  - its entry in `extraction-labels.json`.

  The backup commits the removal like any other change. The data repository's git history keeps the old files.
- After a delete:
  - the posting is gone from the pool, the ranking, the filters, the scoring passes, the availability check, the agent's tools and the scoring examples;
  - adding the same link again stores a fresh posting instead of reporting a duplicate;
  - on the pool page the row disappears without a page reload;
  - on the posting page the app returns to the pool.
- Deleting an unknown posting answers 404, so a second click does no harm.
- While a scoring pass or an availability check runs, the trash button is disabled, and an info icon beside it gives the reason. The server also refuses a delete while a pass, a single score or a check computes. A pass paused over its question about unscreened postings skips a posting deleted meanwhile.
- Other scores whose `example_ids` name a deleted posting keep that ID as history. The posting page already lists only examples that still exist.
- The pool view's keyboard shortcuts stay off while the dialog is open.
- A Design artifact on the JobAdvAIsor design system settles the look. It is linked from `design.md`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `posting-pool`: adds „Delete a posting“, „A deleted posting is gone everywhere“, „No delete while scoring or a check runs“, „A paused pass skips a deleted posting“ and „Scores keep naming a deleted example“.
- `data-repository`: adds „Deletion leaves the repository valid“.
- `posting-intake`: adds „A deleted posting is no duplicate“.
- `web-ui`: adds „Delete button in a pool row“, „Delete button on the posting page“, „Delete confirmation“, „Keys and focus in the delete dialog“, „Delete disabled while a pass or a check runs“ and „Delete refused or failed“.

## Impact

- Backend:
  - `data/writer.py`: `delete_posting(root, posting_id)` under `write_gate`.
  - `api/app.py`: `DELETE /postings/{id}`, and `delete_blocked` in `GET /postings/{id}`.
  - `triage/graph.py`: the `score` node skips a posting whose file is gone.
  - `triage/runs.py` and `availability.py`: a read of whether a run or a check computes.
- Frontend:
  - `api.ts`, plus a new trash button and confirmation component;
  - `views/PoolView.tsx`: the row button, the reload after a delete, and the shortcut guard for `[role="alertdialog"]`;
  - `views/PostingPage.tsx`: the head-row button, one height for the whole row, and the return to the pool;
  - their tests and an e2e walkthrough.
- Data format: unchanged. Files are only removed.
- Docs:
  - ADR 0015 on a hard delete without a trash;
  - the README pool workflow section and both README images, since the pool row and the posting page change visibly;
  - the AGENTS.md „Current state“ section.

## Non-goals

- A trash or undo step. The data repository's git history is the way back.
- Deleting several postings at once.
- Marking a posting as no longer open. That is the availability of [#40 (Track whether a posting is still open)](https://github.com/therealmodbom/jobadvaisor/issues/40).
- Removing a deleted posting's ID from other scores' `example_ids`.
- A delete through the agent. Its tools stay read-only apart from rescoring.
- A new eval. No model input changes. The delete and its effects get regression tests in the default `pytest`.
