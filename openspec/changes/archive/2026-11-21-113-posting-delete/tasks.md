# Tasks

## 0. Look

- [x] 0.1 Draw a Design artifact on the „JobAdvAIsor Design System“. It covers:
  - the trash button in a pool row and on the posting page;
  - the posting page's head row at one height;
  - the disabled state with the info icon, during a pass and during a check;
  - the confirmation for an unrated and for a rated posting, on desktop and phone.

  Verified when `design.md` → D5 links the artifact (approved 2026-11-21) and names the chosen texts.

## 1. Backend

- [x] 1.1 Add `delete_posting(root, posting_id)` to `data/writer.py` (D1), gated. Verify with tests in `test_label_writer.py`:
  - posting, label, score and extraction-label entry are gone, and every other posting's records and entries stay;
  - `load` succeeds afterwards;
  - a posting without a label, a score or an extraction-label entry deletes cleanly;
  - an unknown ID raises `KeyError`, and an unsafe ID raises `ValueError`;
  - a backup's `commit_message` over the removed paths names 1 rating, 1 score and 1 posting (spec: Deletion leaves the repository valid).
- [x] 1.2 Move `write_gate` to `data/loader.py`, and take it in `load`, in `read_scores` and across `pool_state` (D1, Readers see a delete whole). Verify with tests:
  - while another thread holds `write_gate`, `load` and `read_scores` block until it is released;
  - `merge_extraction_labels` still works inside the gate;
  - the whole default `pytest` suite still passes.
- [x] 1.3 Run `GET /postings/{id}`, `PUT …/rating`, `PATCH /postings/{id}` and the answer part of `POST …/score` each in one `write_gate` section, with the 404 check at its start (D1, A request on one posting). Verify in `test_api.py`:
  - a `DELETE` started from another thread while one of these requests holds the gate waits until the request has answered;
  - a request arriving after the delete answers 404 for each of the four, with no file written;
  - `POST …/score` answers 404 when the posting is deleted between `runs.score` and the answer (spec: Delete a posting → Edit after a delete).
- [x] 1.4 Add `Runs.exclusive(name)`, `AvailabilityChecks.exclusive()` and `AvailabilityChecks.running()`, and make `start` claim before it loads its batch (D2). Verify with unit tests:
  - `Runs.exclusive` raises `RunBusyError` while a pass or a single score computes;
  - a pass started while `Runs.exclusive` holds the slot raises `RunBusyError`;
  - the slot is free again after an exception inside the block;
  - `AvailabilityChecks.exclusive` raises `CheckBusyError` while a check computes;
  - a check started while `AvailabilityChecks.exclusive` is held waits, and its batch leaves out a posting deleted inside the block;
  - a failed load in `start` frees the claim;
  - `running()` names the running check and returns `None` otherwise.
- [x] 1.5 Skip a deleted posting in the `score` node (D3). Verify in `test_triage_graph.py`: a pass pauses over unscreened postings, one posting of its batch is deleted, and the pass continues. Then there is no judge call and no score file for it, no `failed` result, and the total drops by one (spec: A paused pass skips a deleted posting).
- [x] 1.6 Add `DELETE /postings/{id}` and `delete_blocked` on `GET /postings/{id}` (D4). Verify in `test_api.py`:
  - 204, then `GET /postings/{id}` answers 404 and `GET /pool` no longer lists the posting;
  - the counter no longer counts the deleted posting's rating;
  - a second `DELETE` answers 404;
  - an unsafe ID answers 404;
  - while a single score holds the slot, 409 `scoring in progress`;
  - while a check runs, 409 `check in progress`;
  - `delete_blocked` reads `"scoring"`, `"check"` and `null` in those three states.
- [x] 1.7 Cover what follows a delete with regression tests (spec: Delete a posting, A deleted posting is no duplicate, Scores keep naming a deleted example):
  - `test_intake_duplicates.py`: after a delete, the same link is no duplicate, and `POST /postings` stores a new posting;
  - a rated posting deleted, then `LabelIndex.sync` and `PostingIndex.sync`: neither returns its ID any more;
  - another posting's score that names the deleted one keeps it in `example_ids`, and its `GET /postings/{id}` `examples` leaves it out.

## 2. Frontend

- [x] 2.1 Add `DeleteButton` and `DeleteDialog` in `components/posting.tsx`, and the `DELETE` call in `api.ts` (D5). Verify with component tests:
  - the dialog names title and company, and for a rated posting the level label;
  - „Abbrechen“ has the focus on open;
  - Escape closes the dialog without a request;
  - a double press sends one request;
  - 409 shows the reason and keeps the dialog open;
  - 500 shows the retry message;
  - 404 counts as success;
  - the disabled state shows `WhyDisabled` with the reason;
  - axe finds no violation.
- [x] 2.2 Put the button into the pool row after `StatusControl`, disabled while `usePass().busy` or a check runs. Reload the pool after a delete, keeping filter, sort and selection rules. Add `[role="alertdialog"]` to the shortcut guard. Verify in `PoolView.test.tsx`:
  - after a confirmed delete the row is gone and the filters stay;
  - with the dialog open, „1“ rates nothing;
  - during a pass and during a check the button is disabled with the matching reason.
- [x] 2.3 Put the button into the posting page's head row after `AvailabilityControl`, and give „Bearbeiten“ the default height. Disable the button from `delete_blocked`. Return to `#/pool` after a delete. Verify in `PostingPage.test.tsx`:
  - delete, then the hash is `#/pool`;
  - `delete_blocked: "check"` disables the button with the check reason;
  - „Bearbeiten“, both selects and the trash button have the same height class.

## 3. End to end and docs

- [x] 3.1 Add an e2e walkthrough over a demo copy. It deletes a rated posting from the pool and an unrated one from its page, each through the dialog. Then:
  - both are gone from the pool;
  - the data repository loads;
  - submitting one of the links again stores a new posting;
  - at desktop and phone width, the head row's four controls have the same height in the browser.

  Verify with `env -C backend uv run pytest -m e2e -q` after `npm --prefix frontend run build`.
- [x] 3.2 Click-test both delete paths in the browser against the real dev server, including the disabled state during a pass. Verified when both deletes work and the reason icon shows.
- [x] 3.3 Update the README pool workflow section and the AGENTS.md „Current state“ section. Retake `docs/images/pool.png` and `posting.png` with `scripts/readme_images.py`. Verified when the README mentions the delete and both images show the trash button.
- [x] 3.4 Run every check: `env -C backend uv run pytest -q`, `env -C backend uv run pytest -m e2e -q`, `env -C backend uv run ruff check .`, `npm --prefix frontend test`, `npm --prefix frontend run lint` and `npm --prefix frontend run build`. Verified when all pass and the `push` CI run on the branch head is green.
