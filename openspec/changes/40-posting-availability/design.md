# Design

## Context

See `proposal.md` → Why. The code this change builds on:

- `Posting` (`data/models.py`) has an application `status`, no availability. `Entity` forbids unknown fields. `update_posting` (`data/writer.py`) merges top-level keys under `write_gate` and sets schema version `"2"` only for `status` and `origin`. The policy pack's `login_wall_hosts` and `import_mapping` were added as optional fields without a version change.
- `download_plain` (`intake/fetch.py`) follows redirects with httpx and retries a 429 or 5xx once at once. Only while `guarded_link` is set (the alert run, `alert_runs.add_entry`) does `_check_hop` check each hop, and it refuses LinkedIn's expired redirect, because `strip_query` drops `trk`. Unguarded, the redirect is followed, and `page_from_html` returns the "similar jobs" search page as posting text.
- `fetch_posting` (`intake/ladder.py`) tries the plain fetch, then the rendered fetch. `is_gone` reads HTTP 404/410 off the attempts. `find_posting` runs the intake loop after a gone link unless `search_if_gone=False`. Only the import passes `False`.
- `pool.rank` builds the rows that `GET /pool`, the posting page and the rating answer all look up by ID (`api/app.py` uses `next(row for row in rank(…))`). `pass_batch` takes every posting. `best_open` and `_explore` filter by application status only.
- The alert runs (`intake/alert_runs.py`) are the pattern for a background run the user starts: one at a time, state in memory, a restart forgets it.

## Goals / Non-Goals

**Goals:**

- One function decides closed, available or unknown for a fetched link. The check and intake share it.
- A closed redirect is recognised before its target is requested, whether the hop is guarded or not.
- A check never overwrites a hand setting, even one made while the check runs.

**Non-Goals:**

- A cancel button for a check. A check sends one plain request per posting and no model call, so it is cheap to let it finish.
- Rendering pages in a browser during the check. A script-only page that answers 200 counts as available.
- Making a 404 at intake skip the rendered step. Only a closed redirect ends the ladder early (D4).

## Decisions

### D1 Availability as an optional field on the posting

`Posting.availability: {state: "available"|"closed"|"unknown", set_at, set_by: "check"|"user"} | None`. Absent means never checked. The pool reads it with the posting, with no second lookup. Rejected: a file per posting, which every pool load would read as well. The field is optional and keeps the schema version, as the policy pack's later fields did. A version 1 or 2 file without it stays valid. Rejected: a version 3. It would mark nothing an external writer has to do differently, since the field is optional.

### D2 Closed rules: defaults in code, the policy pack adds

`ClosedRule {host, redirect_marker?, text_marker?}`, exactly one marker. `DEFAULT_CLOSED_RULES` sits beside `DEFAULT_LOGIN_WALL_HOSTS` and holds LinkedIn's `trk=expired_jd_redirect`. `closed_rules(policy_pack)` returns the defaults followed by `policy_pack.closed_rules`. Why the policy pack's rules add to the defaults instead of replacing them: [ADR 0014](../../../docs/decisions/0014-closed-rules-add-to-the-code-defaults.md).

A rule's host matches itself and its subdomains, as `is_login_walled` does. A redirect marker is matched as a substring of a hop's full address. A text marker is matched, ignoring case, against the visible text of the whole page (`html_text` of the HTML). It is not matched against the posting text that `page_from_html` cuts out, since a LinkedIn header line saying "no longer accepting" lies outside the cut. It is not matched against the raw HTML either: the probe found "no longer available" in script text on a live page.

### D3 Recognition inside the fetch

- The rules reach `fetch` through a context variable `closed_rules`, default `DEFAULT_CLOSED_RULES`. `find_posting` and the check set it from the policy pack. This is the same mechanism as `guarded_link`, and it avoids threading a rules argument through `fetch_posting`, `fetch_plain`, `download_plain` and `download_rendered`.
- `download_plain` always installs a hop hook. A hop whose address matches a redirect marker for its host raises `FetchError(CLOSED_REDIRECT)` before the request is sent. The guarded refusal runs after it, so an expired LinkedIn link from a mail is reported as closed, not as refused. The Chromium route check of `download_rendered` asks the same question, so the rendered step can never render a closed redirect target.
- `page_from_html` sets `Page.closed` when a text marker matches.
- The check uses `download_plain` plus `closed_by_text(url, html)`. It does not need posting text: a page that answers 200 with no marker is available even when `page_from_html` would find no posting in it.

Rejected: matching the final address after the redirect was followed. It works only unguarded, and it sends a request to a page that is known to be dead.

### D4 Intake: a closed page is gone

- `GONE_OUTCOMES` gains `CLOSED_REDIRECT`, so `is_gone` and the import's "link gone" count cover it without further change.
- `fetch_posting` stops after a `CLOSED_REDIRECT` attempt. A 404 still runs the rendered step as before.
- `find_posting` drops `search_if_gone`: a gone link never runs the intake loop, for every caller: a gone page holds no posting to store, and the posting rarely lives on elsewhere under the same terms. This is the only behaviour change for a 404 on a single link. Before, the loop looked for another source and spent a model call doing it.
- `PostingNotFoundError` gains `closed: bool` (`is_gone` of its attempts).
  - `POST /postings` answers 422 with `"closed": true`.
  - `POST /postings/batch` answers `outcome: "closed"`.
  - The alert run reports `state: "closed"`.
- A `Page` with `closed` is stored with `availability {closed, now, check}`.

### D5 The check

New module `availability.py`:

- `check_posting(posting) -> state`. Each stored URL is tried in order. The first that answers 200 with no text marker gives `available`. If every URL answers 404, 410 or `CLOSED_REDIRECT`, or 200 with a text marker, the posting is `closed`. Anything else (a 429, a timeout, a refused hop, another HTTP error) gives `unknown`.
- `AvailabilityChecks` follows the alert runs: one check at a time (`CheckBusyError(check_id)`), a `ThreadPoolExecutor` of one, and state in memory. The state is `{check_id, status: running|done|failed, total, done, counts: {available, closed, unknown}, closed: [{posting_id, title, company}], error}`.
- **Selection** (`check_batch`): application status `open`, `availability` not closed, `set_by` not `user`. It is computed when the check starts.
- **Order and spacing:** the batch is interleaved by host, round-robin. A request waits until `HOST_SPACING_SECONDS = 3` have passed since the last request to the same host. The spike showed 429s even at 3 s. That is accepted: those postings end as `unknown`, and the next check tries them again. A slower spacing would mostly lengthen every check.
- **Write:** `write_availability(root, posting_id, availability)` is gated. It re-reads the file under `write_gate` and writes nothing when the file's availability is `set_by: user`, or when the posting no longer exists (#113 (Delete a posting permanently from the web app)). A hand setting made while the check runs therefore survives. Every other key stays as `update_posting` leaves it.
- The check does not set `guarded_link`. Its links were checked at intake, like those of the import and of a single link.

### D6 API

- `POST /availability/checks` → 202 `{check_id, total}`, or 409 `{error, check_id}` while one runs.
- `GET /availability/checks/{id}` → the state, or 404 for an unknown check (state is in memory).
- `GET /pool` adds `next_check: {total}`, the size of `check_batch`, so the button can name it before a start.
- `PATCH /postings/{id}` accepts `availability: "available"|"closed"` and writes `{state, now, user}`.
- Pool rows gain `availability` (the stored dict or null).

### D7 The pool and the agent

- `rank` keeps closed rows, since the posting page and the rating answer look rows up in it. The consumers leave them out:
  - `pass_batch` (and with it `next_pass` and the pass's own batch in `triage/graph.py`)
  - `best_open`
  - the input of `_explore`
- `counter` and the judge's rated examples are untouched, so a closed posting's rating keeps counting.
- Agent tools that return postings (`find_postings`, `best_open_postings`, `find_similar_postings`) add `closed: true` for a closed posting. No tool writes availability.

### D8 Web UI

- In `FILTERS`, „Offen“, „Noch nicht bewertet“ and „Bewertet“ require `availability?.state !== "closed"`. A new entry „Geschlossen“ keeps open-status rows that are closed.
- The check button, its progress and report, the closed mark on a row, and the availability block with its hand setting on the posting page follow a Design artifact on the „JobAdvAIsor Design System“. It is drawn before the UI task starts and linked here.
- The view remembers a running check's ID in `localStorage`, like the pass, so a reload resumes the poll.

## Risks / Trade-offs

- [An employer's site answers 404 for a moment and the posting is closed wrongly] → The user reopens it by hand on its page. A check never overwrites that.
- [LinkedIn changes its redirect marker] → Postings then stay available, so nothing is closed wrongly. A new default rule fixes it, or the user adds a rule to the policy pack.
- [Rate limits leave many postings unknown] → They stay in the pool and are tried again by the next check. The report names the count.
- [A context variable set in one thread is not seen in another] → It is set in the thread that fetches: inside `find_posting` and inside the check's worker, as `guarded_link` is in the alert run.
- [#113 (Delete a posting permanently from the web app) changes the same files: `pool.py`, `api/app.py`, `PoolView.tsx`, the posting-pool and web-ui specs] → This change adds requirements and modifies none of the pool's. Whichever branch merges second merges `origin/main` and keeps both sides.

## Migration Plan

None. Both fields are optional. Existing postings count as never checked until the first check. Rollback means deploying the previous release: postings that now carry `availability` then fail to load, because `Entity` forbids unknown fields. A rollback after a check therefore needs that key removed from each posting file first. The data repository's git history shows which files the check changed.

## Evaluation

No LLM behaviour is added or changed. The rule matching, the check's outcomes and the pool filters get regression tests in the default `pytest`. Their fixtures are synthetic pages behind an httpx mock transport, one per outcome: open, 404, 410, a redirect to a marker, a page text marker, 429, and a timeout.
