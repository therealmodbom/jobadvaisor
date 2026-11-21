# Design

## Context

See `proposal.md` → Why. The code this change builds on:

- **Data repository.** A posting's records are `postings/<id>.json`, `labels/<id>.json`, `scores/<id>.json` and its key in `extraction-labels.json`.
  - `load` (`data/loader.py`) fails the whole repository for a label without its posting and for an extraction-label entry without its posting. A delete must therefore remove all of them, or the next load fails.
  - `pool.json` and the company records hold no posting IDs.
  - Other scores name rated postings in `example_ids`. `GET /postings/{id}` already lists only examples that still exist (`api/app.py`, `posting_page`).
- **Writes and backups.** Every public write in `data/writer.py` holds `write_gate`, and each swaps a single file by rename. Reads (`load`, `read_scores`) do not take the gate. The backup holds the same gate from `git add -A` to the end of `git commit` (ADR 0010), so it commits removals too, and `commit_message` counts them by kind like any other change. `_posting_path` and `_safe_id` check an ID against `POSTING_ID_PATTERN`.
- **Duplicates and indexes.** Duplicates are found by `duplicate_of` over `intake.postings()`, which loads the repository fresh on every call. There is no separate duplicate index. `LabelIndex.sync` and `PostingIndex.sync` (`index.py`) drop every ID no longer in the repository. Scoring and the agent's tools sync before they read.
- **Runs.** `Runs` (`triage/runs.py`) holds one slot (`_claim`/`_release`) for a computing pass or a single score.
  - A pass waiting for its answer about unscreened postings does not hold the slot. When it resumes, the `score` node works from a context built fresh at that moment.
  - The `score` node calls `_guard_ruling`, which indexes `repository.postings[posting_id]`, before its `read_posting`. A posting deleted while the pass waited would therefore end as `failed`.
  - `AvailabilityChecks` (`availability.py`) keeps `_computing` for the one running check. `write_availability` already writes nothing for a posting deleted meanwhile.
- **Frontend.**
  - `PoolView` knows its pass state (`usePass().busy` covers running and waiting for the answer) and its check state.
  - The posting page knows neither.
  - The pool's shortcut guard skips targets inside `[role="dialog"]`, not inside `[role="alertdialog"]`.
  - `WhyDisabled` (`components/why.tsx`) is the info icon beside a disabled control.
  - `radix-ui` is installed, and its `AlertDialog` traps focus, restores it on close and renders `role="alertdialog"`.

## Goals / Non-Goals

**Goals:**

- One gated function removes every record of a posting, so a backup never commits half a delete and the repository always loads.
- A delete never interleaves with a computing pass or a single score.

**Non-Goals:**

- Cleaning `example_ids` in other scores. They record what the judge saw (decided 2026-11-21).
- Waiting for a pass that is paused over its question. It skips the deleted posting instead (D3).

## Decisions

### D1 A hard delete, with git history as the way back

`delete_posting(root, posting_id)` in `data/writer.py`, under `write_gate`:

1. It checks the ID like `_posting_path`. An unknown ID raises `KeyError`.
2. It removes `labels/<id>.json` and `scores/<id>.json` if they exist.
3. It drops the key from `extraction-labels.json`, written by rename like `merge_extraction_labels`.
4. It removes `postings/<id>.json` last.

A crash between steps leaves records whose posting still exists, so the repository still loads and a second delete finishes the job. There is no trash. Why: [ADR 0015](../../../docs/decisions/0015-hard-delete-with-git-history-as-the-way-back.md).

Rejected: running `load` after the delete to verify it, as `merge_extraction_labels` does. A delete only removes records keyed by the ID, which cannot make another file invalid. A full load per delete would cost the time of a pool load for nothing.

**Readers see a delete whole or not at all.** Every write so far swaps one file by rename, so a reader never caught one half done. A delete removes up to four records one after another. A `load` that globs `labels/` before the delete and reads after it finds a file missing, or a label whose posting is gone, and fails the whole load: `GET /pool` would answer 500 for the moment of the delete.

- `write_gate` moves to `data/loader.py`, and `writer.py` imports it from there, since `writer` already imports `loader`.
- `load` and `read_scores` hold it while they read.
- `pool_state` (`api/app.py`) holds it across its `load`, `read_scores` and `read_pool`, so one request sees one state.
- The gate is reentrant, so `merge_extraction_labels`, which loads inside it, keeps working.

**Writes keyed by the ID see it gone, not broken.** A request that checks the posting and then writes can lose it to a delete in between. Examples are `PATCH /postings/{id}` (`read_posting`, then `amend_posting`) and `PUT /postings/{id}/rating` (a load, then `write_label`). Today both raise a bare `ValueError` from `_posting_path`, and the request answers 500.

- `_posting_path` raises `PostingNotFound`, a `ValueError` subclass, for a missing file. Every write keyed by an ID (`write_label`, `write_score`, `update_posting`, `write_guard`) passes it on.
- `create_app` maps `PostingNotFound` to 404 `not found` in one exception handler, so no endpoint needs its own catch.
- `amend_posting` reads the guard and writes the update in one section under `write_gate`, so its `read_posting` for a release cannot meet a half-done delete. The gate is reentrant, so the nested `update_posting` takes it again.
- Intake writes (an import's origin mark on a stored duplicate) fail that one entry with the same error, as `Risks` says.

Rejected: a catch per endpoint. The next endpoint that writes by ID would miss it, and the handler costs one place.

Rejected: a loader that tolerates the race by skipping a file that vanished between glob and read and by checking orphans against the stems seen at the start. Each reader that combines files (`load`, `read_scores`, `pool_state`) would need its own version of that care. The gate is one mechanism for all of them.

### D2 Delete takes the scoring slot

`Runs.exclusive(name)` is a context manager over `_claim`/`_release`, the slot a single score already takes. The delete endpoint runs `delete_posting` inside `runs.exclusive(f"delete:{id}")`. A computing pass or score therefore raises `RunBusyError`, which answers 409 `scoring in progress`, and no pass can start while the files are removed.

- The check gets the same exclusion. `AvailabilityChecks.exclusive()` is a context manager that holds the checks' lock for the whole delete. It raises `CheckBusyError` while a check computes, which answers 409 `check in progress`.
  - `start` claims `_computing` before it loads its batch, not after as today, and frees it if the load fails.
  - A check started during a delete therefore waits on the lock and then takes its batch from the repository without the posting.
- `AvailabilityChecks.running()` returns the running check's ID or `None`, for `delete_blocked` (D4) only.
- Rejected: only reading whether a pass or a check computes before deleting (`running()` as the guard). One can start between that read and the delete. A pass could then judge a posting whose files vanish, and a check could report a posting that no longer exists.
- Rejected: letting the delete wait for the slot. A pass can run for minutes, and the request would hang.

### D3 A paused pass skips a deleted posting

In the `score` node, a queued posting that is not in the fresh context's `repository.postings` gets `{"status": "deleted"}`, before the guard ruling. It costs no model call and leaves the total, as a ruling does. `store_scores` writes only `scored` results, so nothing else changes.

Rejected: refusing a delete while any pass waits for its answer. `Runs` would have to scan the checkpoints for paused runs. A paused pass can also wait for hours, while the skip costs one membership test. The UI still disables the button while the pool's own pass is paused (`busy`), so the backend case covers a paused pass that another tab or an old session left.

### D4 API

- `DELETE /postings/{id}` answers:
  - 204 with no body;
  - 404 `not found` for an unknown or unsafe ID;
  - 409 `scoring in progress` (detail: the run's ID);
  - 409 `check in progress` (detail: the check's ID).

  The delete runs inside `checks.exclusive()`, then inside `runs.exclusive(…)`, and looks up the ID inside both. Both locks are held only for the milliseconds of the delete.
- `GET /postings/{id}` adds `delete_blocked: "scoring" | "check" | null`. It is `"scoring"` while the slot is held and `"check"` while a check runs. A paused pass does not count (D3).
- `GET /pool` is unchanged. The pool view derives the blocked state from its own pass and check state.

### D5 Web UI

The look follows the Design artifact https://claude.ai/artifact/TauRa8AUApTexoFiSt8d2H, approved 2026-11-21. Its boards are screenshots of the running app over the demo persona.

- **`DeleteButton`** in `components/posting.tsx`:
  - an outline icon button `size-11` with `Trash2` in `text-danger` and the `aria-label` „Anzeige löschen“;
  - when blocked, `disabled` with `WhyDisabled` beside it and one of the two reason texts in the spec;
  - clicking it opens `DeleteDialog`.
- **`DeleteDialog`**, a Radix `AlertDialog`:
  - title „Anzeige löschen?“;
  - text „**Titel** (Firma) wird endgültig gelöscht, mit ihrem Score.“;
  - for a rated posting with a strength, „Du hast sie mit **„<level label>“** bewertet. Die Bewertung geht mit verloren und zählt danach nicht mehr als Beispiel fürs Scoren.“ The label comes from `LEVELS`. A verdict without a strength (an imported label) reads „Ja“ or „Nein“. A label without a verdict (`imported_not_preference`) adds no rating line.
  - buttons „Abbrechen“ (outline, initial focus via `onOpenAutoFocus`) and „Endgültig löschen“ (filled `danger`, with the trash icon).

  While the request runs, „Endgültig löschen“ is `aria-disabled` and a ref blocks a second send.
  - A 409 shows the matching reason in a `role="alert"` line in the dialog. The dialog stays open.
  - Any other failure shows „Löschen hat nicht geklappt. Versuch es noch einmal.“, and the button stays usable.
  - A 404 counts as success.
- **Pool row:** the button sits after `StatusControl`, with `mt-6` so it lines up with the select (the select has a label above it). On success `PoolView` reloads `GET /pool` (counter, `next_pass` and `next_check` change too) and keeps its filters, sort and scroll position. If the deleted row was selected, the selection moves to the next row, as it does after a rating.
- **Posting page:** the button sits after `AvailabilityControl`, with `mt-6`. „Bearbeiten“ grows from `size="sm"` (32 px) to the default height (44 px, `h-11`), like the selects (`min-h-11`). Widths stay as they are. On success the page sets `location.hash = '#/pool'`. The pool view reloads when it becomes active.
- **Shortcut guard:** `PoolView`'s key handler also skips targets inside `[role="alertdialog"]`. The Radix dialog renders in a portal outside the row, so the guard must match on the dialog role, not on the row.

## Risks / Trade-offs

- [A delete by mistake] → The confirmation names the posting and its rating. The data repository's git history holds the files once a backup ran. A delete before the first backup is lost, and the dialog says „endgültig“.
- [Reads now wait for `write_gate`, also while a backup holds it from `git add` to the end of `git commit`, and concurrent reads queue behind each other] → The backup's commit and each write take milliseconds to about a second. The app serves one user. A slow backup shows as a slower pool load, not as an error.
- [A pass paused in another tab resumes after a delete] → D3 skips the posting. Its progress total drops by one, as for a ruling.
- [A stale posting page sends a delete after a pass started] → 409, and the dialog says why (spec „Delete refused or failed“).
- [An import or alert run writes to a posting deleted at the same moment] → `update_posting` raises `PostingNotFound`, and that one entry fails. This is rare and not worth a lock across intake.
- [#40's archive and this change both touch `posting-pool` and `web-ui`] → This change only adds requirements, so a merge keeps both sides without editing a shared requirement.

## Migration Plan

None. The data format is unchanged, and a rollback leaves a valid repository: an older release only sees fewer postings.

## Evaluation

No LLM behaviour changes. The judge sees fewer examples after a rated posting is deleted, through the existing index sync. That is data, not a change to the prompt or the model input format. Regression tests in the default `pytest` cover:

- the records removed;
- the repository loading after a delete;
- the 404, 409 and 204 answers;
- the skip in the `score` node;
- a fresh posting after the same link is submitted again;
- the index no longer returning the deleted posting.
