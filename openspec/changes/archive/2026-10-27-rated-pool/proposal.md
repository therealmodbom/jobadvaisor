# Proposal

## Why

The user's main use is a daily-growing stock of postings, old and new, from which the app finds the ones worth applying to, and which improves with the corrections the user gives. Slice 7 built the opposite: a run scores only the postings unrated at its start, a finished run disappears, and scores never reach the posting. The walkthrough of slice 7 (task 7.8, 2026-10-13) showed that this run-centred model does not fit that use. A real-data evaluation (task 8.2 of the archived `learning-job-match`) needs a workflow that does, so this change comes before it.

## What Changes

- **A pool of all stored postings** is the main view, ranked by fit and filterable by text and state, with a page per posting (#14, #20). It replaces the feedback list; the run concept leaves the UI.
- **The latest score and reasoning stay with the posting** and outlive any run (#20).
- **Scoring is triggered by a button "Neue Anzeigen bewerten"**, not by the user starting a run and not automatically. The pass scores every posting without a score and, after corrections, rescores every unrated posting (rated postings keep their score, which the corrections were measured against); "only similar postings" stays a later option.
- **Corrections are counted.** A correction is a rating whose verdict contradicts the posting's score (a score of 6 or more fits, below 6 does not). The view shows the count and the share of contradicting ratings since the last pass, and hints "neue Bewertung sinnvoll" when the count reaches the user's threshold (default 10) or the share reaches the user's rate (default 30 %, from 10 ratings on), and "Ranking passt gut" when it stays low. Each pass stores its rate as a quality measure.
- **Rating happens in the pool** and needs no run. A reason chip can give the verdict, and one rating can carry chips of both polarities (#19).
- **Application status** per posting: open, "beworben", "erledigt". The last two leave the recommendation (#20).
- **Exploration** becomes a mark in the filter "noch nicht bewertet": about every fifth posting comes from the lower half of the scores, marked "Stichprobe".
- **Several links at once** go into intake (#3, first increment, pulled forward from the kickoff brief's change "Sourcing from job alert mails and portals").
- **Import of a job list** the user keeps elsewhere (#21), by upload in the web UI, with no script to run. The app knows no list layout: it finds tables by their link column, and the user confirms a mapping (status column, status values, own assessment) that the data repository stores. Table, assessment and status become an origin mark that does not count for learning; the application status comes from each entry's own status through the mapping. Entries whose status maps to skip, or whose link no longer answers, are not imported and are listed in the report.
- **The agent can list the best-fitting open postings over the whole pool** with no run open (#20, last slice).
- Task 8.2 (the full eval on the user's real data) moves here and runs after the import.

**BREAKING:** the paused-run rating flow and `POST /runs/{id}/ratings` go away; the posting file format gains optional fields (schema version 2), and score and pool are new files.

## Capabilities

### New Capabilities

- `posting-pool`: the pool of stored postings, its ranking and filters, the application status, the scoring pass with the correction counter and hints, and the exploration mark.

### Modified Capabilities

- `job-triage`: scores persist per posting; a scoring pass replaces the run that pauses for ratings; the exploration slot moves into the pool.
- `rating-feedback`: ratings are written directly from the pool; a chip can give the verdict; chips of both polarities mix.
- `web-ui`: the pool view and a page per posting replace the feedback list.
- `data-repository`: a score entity, a status and an origin mark on the posting, and the pool settings.
- `posting-intake`: several links at once; import of a job list with the guard against closed postings.
- `job-agent`: a tool over the pool.

## Non-goals

- Extracting postings from pasted job alert mails (rest of #3). It may depend on #9 and #10, since LinkedIn alert-mail links sit behind a login, and stays a later change.
- Scoring without the user's button (right after intake, or on a schedule).
- Rescoring only the postings similar to a corrected one. The pass rescores every unrated posting; the user chose the cheaper-to-build variant, and the option can follow.
- Login-walled postings (#9, #10), postings added from the chat (#18), and chip descriptions and maintenance (#15–#17).
- Any real job list, or the layout of one, in this repository, its tests or its fixtures.

## Impact

- Backend: `triage/graph.py` and `triage/runs.py` (pass without a rating pause), `data/models.py`, `data/writer.py`, `schemas/*.schema.json` (version step), `api/app.py` (pool, status, rating and pass routes), `intake/` (several links, import), `agent/__init__.py` (pool tool).
- Frontend: `App.tsx` routes, a pool view and a posting page replacing `FeedbackView`/`FeedbackList`, `lib/chips.ts` (#19).
- Evals: the scoring eval runs per pass on the demo persona; the agent eval gains a pool question; the import's closed-posting guard gets a case in the intake eval.
- No new dependency is expected.
