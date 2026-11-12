# Design

## Context

Motivation and scope are in `proposal.md`, behavior in this change's specs. The baseline is the archived `learning-job-match` (see its `design.md` for the triage graph, the data layout, the API and the UI presentation). What holds today:

- A score lives only in a run's graph state (`triage/graph.py`, node `score`), as an integer 0–10 with reasoning and example IDs. A `Posting` has no score field; `GET /runs` lists paused runs only.
- A run presents a list (`select`), pauses in `await_ratings` and writes labels in `write_labels`. `presented_at` marks what a run presented.
- No code decides whether a score "fits": the 0–10 scale has no verdict cut, and the eval's "positive" comes from the user's labels.
- The data repository holds `profile.json`, `policy-pack.json`, `postings/<id>.json` and `labels/<id>.json`, all with `schema_version`; the Pydantic models generate `schemas/*.schema.json` (ADR 0006).
- Users who come to the app often keep their job leads in a Markdown file of their own: tables with a link per row, a status and an own assessment, grouped under headings, next to notes and logs. Its layout is each user's own, and this repository is meant to become public, so the app holds no knowledge of any one layout (2026-10-21).

## Goals / Non-Goals

**Goals:**

- The pool, its ranking and the counters are computed by one backend function that the API and the agent tool both call, so the two never disagree.
- A pass reuses the existing nodes (`load`, `exclude`, `extract`, `score`) and their tests; only the ends of the graph change.
- Every new file the app writes goes to the data repository in a schema, so a rebuild of the local stores loses nothing.

**Non-Goals:**

- Server-side filtering and paging. The pool is in the thousands at most, and the list rows carry no posting text; the client filters.
- A job queue or a scheduler. A pass is one background computation the user starts, like a run today.

## Decisions

### Score, status and origin go to the data repository

A score is written to `scores/<posting-id>.json` (`score`, `reasoning`, `example_ids`, `scored_at`, `schema_version`), a new entity with its own schema. The user's application status (`open` | `applied` | `done`, shown as open, "beworben", "erledigt") and the import's origin mark (`table`, `fit`, `status` as the list gave them) become optional fields of the posting. Application status and origin are user and import data, so the posting file carries them; a score is derived data, so it gets its own file and a posting's file stays untouched by a pass.

Alternative: keep scores in the local state directory next to the Chroma index. Rejected: a lost state directory would cost a paid pass over the whole pool to recover, and the scores would not be visible to an external reader of the data repository.

Schema version: only the posting goes from version 1 to 2, since only it gains fields; label, profile and policy pack stay at 1, and the new score and pool files start at 1. Today one `SchemaVersion` constant serves every entity, so the models gain a supported-version list per entity. The posting loader accepts 1 and 2 and reads version 1 as status open without an origin mark. `presented_at` stays in the schema, since earlier data holds it, and nothing writes it any more.

### Pool settings and pass history in one file

`pool.json` holds `settings` (`correction_threshold`, default 10; `correction_rate`, default 0.3; `rate_min_ratings`, fixed at 10 in code and not a setting) and `passes` (`[{started_at, finished_at, scored, corrections, rated, rate}]`, appended by each pass that scored at least one posting; `started_at` is absent in passes written before slice 2, which then count from `finished_at`). One file keeps the number of entities small; the user edits the two settings in the app, which writes this file. A missing file means the defaults and an empty history.

### A pass is the triage graph without its rating pause

The graph becomes `load` → `exclude` → (`confirm_unscreened`) → `extract` → `score` → `store_scores` → end. `select`, `await_ratings` and `write_labels` leave it. `load` takes every posting without a label and without a score; with corrections counted since the last pass it takes every posting without a label. Rated postings are not rescored: their rating decides their place, and their stored score is the one the corrections were measured against (the retrieval excludes a posting from its own examples already). `store_scores` writes the score files and appends the pass to `pool.json`, computing the pass's quality measure at that moment.

The `Runs` class keeps starting, computing and reading a pass in a background thread and the unscreened pause, so the pass keeps the checkpointing, the busy check (one pass at a time, 409) and the restart behavior it has now. The routes `POST /runs/{id}/ratings`, `presented_count` and the paused-run list go.

Alternative: run the pass as a plain function without LangGraph. Rejected: the unscreened pause needs `interrupt()` and its resume, and a second code path for the same steps would fork the nodes' tests.

### Correction and fit rule

`FIT_SCORE = 6`: a score of 6 or more counts as "fits". The judge scores 0–10 and no existing code cuts it; 6 is the user's wording ("8 versus Nicht passend") made concrete and is a constant in one place, changeable without a spec change if the scale's use shows another cut. A correction is a label of kind `rating` whose verdict contradicts its posting's stored score and whose `rated_at` is after the start of the last pass (decision, 2026-10-14: a correction given while a pass computes was not learned by it, so it counts toward the next one; the counter therefore need not be zero right after a pass). A pass rescores every unrated posting when this counter is above zero. Counting reads the labels and score files, so it needs no counter of its own and cannot drift; a posting without a score has nothing to contradict and is not counted, nor does it enter the share's denominator. The hint is a pure function of the counter, the share and the settings.

### One ranking function

`pool.rank(repository, …)` returns the rows in this order: rated positive first (by score, then recency), then unrated by score, then rated negative, excluded and guard-held; ties by `added_at`, newest first. Application status "applied" and "done" filter out by default. `GET /pool` returns the rows (no posting text), the counter, the share, the hint and the settings; `GET /postings/{id}` returns the page's data. The agent's pool tool calls the same function.

### The exploration mark

In `GET /pool`, for the unrated postings with a score, about every fifth position (20 % rounded, like today's slot) is taken from below the median of their scores by a seeded pick and carries `exploration: true`, so the filter "noch nicht bewertet" shows the mark. The seed is the number of stored labels: stable while the user rates nothing, new after each rating, so the picks vary over time without a stored state.

Alternative: draw the sample at pass time and store it. Rejected: it needs stored state for something the next rating makes stale.

### Rating without a run

`PUT /postings/{id}/rating` takes `verdict` (optional), `chips` and `note`, validates the chips against the policy pack, derives a missing verdict from the first chip that names a polarity (task 3.2 spells out the order), writes the label at once and answers the updated counters. The chip-polarity check of `check_ratings` goes, since mixed chips are allowed. `PATCH /postings/{id}` gains `status`. The embedding sync stays out of the write, as today: scoring and the agent sync before they read.

The frontend's `chipFits` (hiding the other polarity) goes, and a chip's toggle sets the verdict only when none exists. The judge's prompt formats an example's chips with their polarity, so mixed chips read as "positive: remote; negative: onsite only" and not as a contradiction (an eval case, below).

### Several links

`POST /postings` keeps its single-input contract. A new `POST /postings/batch` takes `urls` (a list) and answers a list of per-URL outcomes (`stored`, `duplicate`, `failed` with attempts). It runs each URL through the same `find_posting` and `add_submission`, one after the other: the ladder opens browsers and calls models, and a parallel burst would hit the 429 handling the ladder already has. The intake view gets a text area, one URL per line.

### The list import

The import is a web feature, like every other action of the app (decision, 2026-10-14: no scripts to start, and the app is meant to become a pure web tool). It knows no list layout; the layout's meaning comes from a mapping the user confirms and the data repository stores. The decision and the rejected alternatives are in [ADR 0007](../../../../docs/decisions/0007-layout-free-list-import-with-a-stored-mapping.md).

- **Tables.** The parser reads every Markdown table of the uploaded file. A table's link column is the column holding the most http(s) URLs (at least one); a table without one is no entry table. Each row is an entry: its table (the nearest heading above the table), its row text (the cells except the link, joined), its link (the first http(s) URL in the link cell, none for a row without one) and the cells of the mapped status and assessment columns.
- **Mapping.** `ImportMapping` in the policy pack: `status_column` (optional), `assessment_column` (optional) and `values`, each status value to `open`, `applied`, `done` or `skip`. With a status column, only tables that have that column are entry tables, so a log with links but no status stays out. Header names and values match trimmed and case-insensitively; a value the mapping does not name gives open.
- **Flow.** `POST /imports/preview` (multipart file) answers the tables with their columns and entry counts, the distinct values per column (columns with up to 30 distinct values) and the stored mapping. The view shows the mapping form; confirming sends `POST /imports` with the file and the mapping (a JSON form field), which stores the mapping in the policy pack and answers 202 with an import ID, starting a background computation like a pass, one at a time. The browser keeps the file and sends it twice; the server stores it neither time. `GET /imports/{id}` answers progress and, when finished, the report.
- **Outcomes.** An entry whose status maps to `skip` is skipped without a fetch. An entry whose listed link answers HTTP 404 or 410 in the fetch ladder counts as skipped, link gone, and the intake loop does not look for it elsewhere (2026-10-22: a dead link in the list means a closed posting, and the loop picked another posting for it in the walkthrough); any other failure, a missing link included, counts as failed and is not retried inside the run. Every entry that was not imported is listed in the report with its row text (its cells except the link, joined), its link and the reason.
- **Origin and status.** A new posting gets the origin mark (table, assessment value, status value as the list gave them) and the mapped application status. A stored posting gains the origin mark and keeps its status. When an entry matches a stored posting by URL or by the same text and has a status whose mapped application status differs from the posting's, the report lists the posting with title, company and both statuses, so the user takes the list's status or keeps the app's (2026-10-21): until the app replaces the list, the list is imported again and again, and a silent mismatch would leave applied postings in the ranking. An entry with an empty status raises no discrepancy, and the discrepancies live in the import's memory only, so a restart drops them and the next import asks again.
- **Restart.** Entries go through intake one after another, so a restart in the middle loses nothing: uploading the file again finds what is stored as duplicates, since duplicates are found by URL.

The tests and the eval use an invented list in `fixtures/` whose layout (headings, columns, status vocabulary, assessment scale) is unlike any real user's list.

Alternative: a command run in a terminal against the data repository. Rejected by the user: it would be the one feature that needs a shell, and a hosted web tool has none.

Quality assurance is the exception to "no scripts" (decision, 2026-10-14): `python -m jobadvaisor.evals` and the CI run on a tag stay terminal and pipeline tools, since evals are administration and not part of using the app. The rule covers what the user does with the app; later CI/CD pipelines and GitHub Actions can take over QA steps without a UI.

### The agent's pool tool

`best_open_postings(limit, statuses)` returns the first rows of `pool.best_open` (open by default; `statuses` lists "beworben" or "erledigt" when asked): title, company, score, the user's rating (verdict and chips), status and the page address `#/anzeigen/<id>`. `pool.best_open` is `pool.rank` without postings rated negative, excluded or held and without the exploration picks, since a pick is a learning aid and no recommendation; the agent eval computes its expected answer with the same function. `find_postings` also searches the labels' chip labels and notes (decision, 2026-10-23, over a separate chip tool), so "Was habe ich als zu junior markiert?" is answerable, and returns the stored pool score with its reasoning as a data block, the reasoning left out for a posting the agent may not see. The chat renders the page addresses as links and opens a `#/…` link in the same tab. `rescore_run` becomes `rescore_postings(posting_ids)`, which compares with the stored pool score and writes nothing. `run_result` goes (decision, 2026-10-23): the chat has had no run since slice 2, so `POST /agent/messages` loses `run_id` and the agent its run reader.

The agent eval seeds a score for every posting without one on its temporary copy (0–10 by ID order), so the pool's ranking is defined on the demo persona, which no pass has scored; stored scores stay as they are, so the user's real data is ranked by its own.

## Evals

Every LLM-backed behavior names its eval (metric and data):

- **Scoring** (existing, precision@5 on the time split of the demo persona) runs on the pass's code path: the eval calls the same `score` step, so a regression in the pass shows there. New: a **mixed-chip case** in the scoring eval's data, where an example carries positive and negative chips; the metric is the same precision@5 plus a check that the reasoning cites both chips, on the demo persona.
- **Quality measure per pass** needs no model: it is computed from labels and scores. A unit test over a fictional history covers it; the real-data eval (task 8.2 moves here) reports it for the user's data.
- **Agent** (existing, task success rate): two new questions on the demo persona, "which posting should I apply to" (answer must list the top open postings by ID in order) and "what did I mark with a chip", plus a "mark it beworben" request (the posting stays unchanged and the answer points to the pool), since the refusal is new prompt behavior; the run-based rescore and stored-score questions move to the pool. 15 questions.
- **Import's closed-posting guard** has no model; its eval is a test over an invented list with a served page that answers 410, one that times out and one entry whose status maps to skip, checking the counts and the listed entries.
- **Task 8.2**: the full suite on the user's real data repository after the import, output outside this repository, as before.

### Latest tagged run

The last-slice code was evaluated by CI at tag `eval-20261023`. The demo fixture is **not unchanged** from `eval-20261013`: the mixed-chip case added `wrong-stack` to `demo-036`, and that label is part of the scoring training set. The run used `openai/gpt-6-luna`, except for the hosted decision-model competitor and the Mistral moderation classifier.

- Scoring: precision@5 **0.80** on 15 held-out postings (111 training labels); the mixed-chip reasoning check cited both polarities in **1/2** cases.
- Agent: **15/15** scripted questions succeeded (success rate **1.00**).
- Fixed graph vs. free agent: both mean precision@5 **0.7333** over three repetitions; graph variance **0.00889**, agent variance **0.03556**.
- Feature extraction: overall accuracy **1.00**; logistic regression competitor precision@5 **1.00**; hosted decision-model competitor precision@5 **0.60**.
- Intake: success rate **1.00**, mean tool calls **1.67**; field filling accuracy was title **0.889**, company **0.889**, location **1.00**.
- Content guard: decision model detection rate **1.00**, Mistral detection rate **0.8333**; both had false-positive rate **0.00** over their successful clean-posting calls. One Mistral call for a clean posting returned HTTP 429, so its rate covers 29 of 30 clean postings.
- Baseline precision@5 was **1.00** on the retained/discarded comparison.

The full eval report is retained as the CI artifact and is not committed here. The full suite must still run against the private real-data repository, including the pass quality measure, with its report outside this repository.

## Risks / Trade-offs

- [A whole-pool pass costs money per unrated posting ($0.0003 each on the demo model, so about $0.15 for 500)] → the pass shows the count before it starts, and the user starts it; "only similar" stays an option for later.
- [The fit cut of 6 splits a score the judge does not use as a verdict] → one constant, and the stored quality measure shows whether the share means anything; revisit after the real-data run.
- [The user's list layout changes] → the preview shows the tables and columns before every import, and a renamed status column no longer matches the stored mapping, so the form asks again instead of importing wrong statuses.
- [Closed-link detection by one failed fetch] → only "gone" answers skip an entry; every other failure is reported as failed for a retry.
- [Removing the paused-run rating flow breaks runs in flight] → the app has one user and no run is expected in flight at the upgrade; a run paused on `await_ratings` in an old checkpoint is ignored by the new graph and its labels are lost nowhere, since labels are written at rating time from now on.

## Migration Plan

Data repository files of version 1 load unchanged (posting version 2 adds only optional fields); the first pass writes `scores/` and `pool.json`. The demo persona fixture is regenerated into version 2 only if a test needs a status or an origin mark, so the existing fixture stays valid as it is. Rollback is a revert of the branch: older code ignores the new files and fields except that its loader rejects a version 2 posting, which is why the posting version step ships in the same slice as the first code that writes them.
