## 1. Storage of scores, status, origin and pool settings (slice 1)

- [x] 1.1 Add the `Score` and `Pool` models (settings, pass history), the optional `status` and `origin` fields on `Posting`, and the version step to 2 for the posting only (label, profile and policy pack stay at 1; the models get a supported-version list per entity instead of one shared constant); regenerate `schemas/*.schema.json`, keep the CI check that committed schemas equal generated ones; the posting loader accepts versions 1 and 2 and reads a version 1 posting as status open without an origin mark. Tests: schema validity, a version 1 posting loads, a version 2 posting round-trips, a label at version 1 still loads
- [x] 1.2 Writers and readers for `scores/<id>.json` and `pool.json` (missing file gives defaults and an empty history), in `data/writer.py`, with atomic writes like the label writer
- [x] 1.3 Pass graph: drop `select`, `await_ratings` and `write_labels`; `load` takes unlabeled, unscored postings, or every unlabeled posting when corrections were counted since the last pass; new `store_scores` node writes score files and appends the pass to `pool.json`; `Runs` starts, reads and resumes a pass (unscreened pause kept, one pass at a time); remove `POST /runs/{id}/ratings`, `presented_count` and the paused-run list. Tests: scores outlive a restart, a later pass replaces a score, rated postings are not rescored, an unscreened pause still resumes

## 2. Pool API and ranked view with status (slice 2; #20, #14)

- [x] 2.1 `pool.rank` and the correction counter (`FIT_SCORE = 6`, corrections since the last pass, share, hint from the settings); `GET /pool`, `GET /postings/{id}`, `PUT /pool/settings`, `PATCH /postings/{id}` with `status`, `POST /pool/passes` with a count preview and `GET` for its progress. Tests: ranking order incl. rated positive first and status filtering, a correction versus an agreement, the share needs 10 ratings, one count per posting, the hint
- [x] 2.2 Exploration mark in `GET /pool` (every fifth position from below the median, seeded by the label count). Test: 2 of 10 marked, fewer low-scored postings never fail
- [x] 2.3 Frontend: hash routes `#/pool` and `#/anzeigen/<id>`, pool view with text and state filters, status control, the pass button with its count, counter, share, hint and settings, German texts; remove `FeedbackView`/`FeedbackList` and the run concept from the UI; keep the unscreened question in the pass progress. Component and accessibility tests in both themes
- [x] 2.4 Posting page with text, original link, score and reasoning, rating, status and origin mark

## 3. Rating in the pool incl. #19 (slice 3)

- [x] 3.1 `PUT /postings/{id}/rating` writes the label at once and answers the updated counters; chips of both polarities are accepted; unknown chips are rejected with the chip named
- [x] 3.2 A missing verdict comes from the first chip that names a polarity (chips in the order sent); none to derive is a 422 naming the missing verdict
- [x] 3.3 Frontend (`chipFits` was already removed in slice 2): a chip toggle sets the verdict only when none is set, by mouse and by Shift+1–9; keyboard rating from the pool (Enter to the next unrated posting). Tests: verdict from a chip, mixed chips, explicit verdict unchanged
- [x] 3.4 Judge prompt shows an example's chips with their polarity; add the mixed-chip case to the scoring eval's demo data (done) and run the eval (tag `eval-20261019` on main: precision@5 0.80, mixed-chip citations 0 of 3 with the label-substring check, 1 of 3 read by hand; the check now matches a cue stem, and the prompt asks to name each reason that holds; tag `eval-20261019-2`: precision@5 0.80, mixed-chip citations 2 of 2)

## 4. Several links at once (slice 4; #3 first increment)

- [x] 4.1 `POST /postings/batch` with a list of URLs: sequential, per-URL outcome (stored, duplicate, failed with attempts), one failure never stops the rest. Tests with the fixture test server
- [x] 4.2 Intake view: text area, one URL per line, per-URL results with the text and PDF options for failures

## 5. Import of a job list (slice 5; #21)

- [x] 5.1 A fictional list under `fixtures/` (entry tables, a log section, one entry whose status maps to skip, one entry whose link answers 410, one that times out)
- [x] 5.2 Parser: only entry tables, other sections ignored; status mapping and the origin mark from table, assessment and status
- [x] 5.3 `POST /imports` (multipart upload, 202) and `GET /imports/{id}` (progress, then the report): a background computation, one at a time, each URL through the normal intake in sequence (duplicates get the origin mark), entries whose status maps to skip and "gone" entries skipped without storing content, other failures reported as failed; the upload is not stored. Tests on the fictional list: counts add up, a second upload imports only the rest
- [x] 5.4 Import view in the UI (upload, progress, report); pool filter "Herkunft" and the origin mark in the list and on the posting page. Component and accessibility tests
- [x] 5.5 Status discrepancies (2026-10-21): the import keeps a stored posting's application status and lists it when the list's status maps to another one; the import view shows each with title, company and both statuses and lets the user take the list's status or keep the app's. Tests on both sides
- [x] 5.6 Layout-free list import (2026-10-21): tables found by their link column; `ImportMapping` in the policy pack (status column, values to open/applied/done/skip, assessment column) with its schema; `POST /imports/preview` and `POST /imports` with the mapping; the report lists every entry not imported with row text, link and reason. An invented fixture unlike any real list replaces the old one; no list layout of any user stays in code, tests, fixtures or docs
- [x] 5.7 Import view: the mapping form between upload and start (prefilled from the stored mapping), the list of entries not imported; the e2e walkthrough confirms the mapping through the UI
- [x] 5.8 No silent drift (2026-10-21): the form marks tables without the chosen status column as not imported and status values the stored mapping does not name as new, and warns when no status column is chosen though one is stored; the report names the tables left out with their entry counts. Component, API and e2e tests
- [x] 5.9 Smoke-test findings (2026-10-22): a listed link answering 404/410 is skipped as gone without the intake loop looking elsewhere; an entry never replaces the origin mark of a posting it reached through another link, and names no status discrepancy for it. API tests
- [x] 5.10 The import moves into "Anzeige hinzufügen" (2026-10-22): a fourth source "Liste" next to Link, Text einfügen and PDF instead of the navigation entry "Liste importieren"; `#/importieren` stays the route of that source, so a reload still shows a running import. Component, accessibility and e2e tests

## 6. Agent over the pool (slice 6; #20 last part, #14 agent criteria)

- [x] 6.1 `best_open_postings` tool over `pool.rank`; `find_postings` returns chips and notes; `rescore_run` becomes a rescore of named postings that writes nothing
- [x] 6.2 Chat links posting addresses to `#/anzeigen/<id>`; the agent says it cannot set the status and points to the pool
- [x] 6.3 Two agent eval questions (which to apply to, what I marked with a chip); run the agent eval

## 7. Evals and wrap-up

- [x] 7.1 Eval run on a tag (`eval-<date>`) on the last slice's code; numbers into this change's design under Evals, and a note that the demo fixture is unchanged from `eval-20261013` unless a slice changed it
- [x] 7.2 Full eval suite against the user's real data repository after the import, with output outside this repository (manual step); verify the user has the report and the PR description states that it exists, without its numbers. Includes the pass quality measure on real data. Moved here from the archived `learning-job-match` (task 8.2). Moved on to issue #64 (2026-10-27): too few own ratings yet, and the change is archived without it
- [x] 7.3 Update `README.md` and `AGENTS.md` "Current state" for the pool; verify the README's demo path reaches a pass and a rating in the pool
- [x] 7.4 Run `openspec archive rated-pool --yes` on the branch of the last PR, before it merges (here a small archive PR, since every slice PR had merged before the rule changed); verify `openspec/specs/` holds `posting-pool` and `openspec list` shows no active change
