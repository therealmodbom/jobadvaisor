# 0015. Hard delete, with git history as the way back

## Status

Accepted, 2026-11-21.

## Context

Issue [#113 (Delete a posting permanently from the web app)](https://github.com/therealmodbom/jobadvaisor/issues/113) lets the user delete a stored posting. The records to delete are those that should never have existed: a job-board list page stored by mistake, a test entry, a duplicate in the wrong form.

The data repository is a git repository. The app writes files, and the backup commits and pushes them (ADR 0010). A file removed from it stays in every earlier commit.

A posting's records are its file, its label, its score and its key in `extraction-labels.json`. The loader rejects a label or an extraction-label entry whose posting file is missing.

## Decision

A delete removes every record of the posting from the working tree, behind one confirmation that names the posting and its rating. There is no trash and no undo in the app. The git history of the data repository is the way back.

## Alternatives considered

- **A trash: mark the posting as deleted and keep its files.**
  - Every reader of the repository would have to leave marked postings out: the pool, the passes, the check, the agent's tools, duplicate detection and both indexes.
  - Intake would need a rule for a link that matches a deleted posting.
  - A view would be needed to restore or empty the trash.
  - All of that would serve records that should never have existed, which the user rarely wants back.
- **Move the files to a `deleted/` folder in the data repository.** The loader would have to ignore that folder, the backup would commit it, and the folder would grow without an end. It adds nothing over git history, which keeps the old files anyway.
- **An undo in the app shortly after a delete.** The files would have to be held in memory or in a temporary folder until the undo expires. That is a trash with a timer, and it brings the same reader problem for its duration.

## Consequences

- A deleted posting comes back only through git, by hand, and only after a backup has committed its files. A delete before the first backup is lost.
- Readers need no deleted state. Every reader that loads the repository afresh is correct at once.
- The confirmation dialog carries the safety. It names the posting and, for a rated posting, the rating that stops counting as a scoring example.
