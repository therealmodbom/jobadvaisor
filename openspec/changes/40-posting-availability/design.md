# Design

## Context

See `proposal.md` → Why. The code this change builds on:

- `Posting` (`data/models.py`) has an application `status` and no availability. `Entity` forbids unknown fields. `update_posting` (`data/writer.py`) merges top-level keys under `write_gate` and sets schema version `"2"` only for `status` and `origin`. The policy pack's `login_wall_hosts` and `import_mapping` were added as optional fields without a version change.
- `download_plain` (`intake/fetch.py`) follows redirects with httpx and retries a 429 or 5xx once, at once. Only while `guarded_link` is set does `_check_hop` check each hop. That happens in the alert run (`alert_runs.add_entry`), and the hop check refuses LinkedIn's expired redirect, because `strip_query` drops `trk`. `download_rendered` installs its route check under the same condition only. Unguarded, both follow the redirect, and `page_from_html` returns the "similar jobs" search page as posting text. It raises "no posting text" for under `MIN_PAGE_TEXT` characters.
- `fetch_posting` (`intake/ladder.py`) tries the plain fetch, then the rendered fetch. `is_gone` reads HTTP 404/410 off the attempts. `find_posting` runs the intake loop after a gone link unless `search_if_gone=False`. Only the import passes `False`. `fill_company_facts` treats `GONE_OUTCOMES` as settled.
- `pool.rank` builds the rows that `GET /pool`, the posting page and the rating answer all look up by ID (`next(row for row in rank(…))` in `api/app.py`). `pass_batch` takes every posting. `best_open` and `_explore` filter by application status only. `_explore` takes the open rows of the unrated scored group and appends the others after its picks.
- The alert runs are the pattern for a background run the user starts: one at a time, state in memory, a restart forgets it. `intake/company_facts.Throttle` spaces requests per host, with an injectable clock and sleep.

## Goals / Non-Goals

**Goals:**

- One set of functions decides closed, available or unknown for a fetched link. The check and intake share it.
- A closed redirect is recognised before its target is requested, in the plain and in the rendered fetch, guarded or not.
- A check never overwrites a hand setting, even one made while the check runs.

**Non-Goals:**

- A cancel button for a check. A check sends one plain request per link and no model call.
- Rendering pages in a browser during the check. A script-only page that answers 200 counts as available. The probe found that a removed Arbeitsagentur posting answers HTTP 410 to the plain fetch, so the check catches it without the adapter.
- A default page text marker for LinkedIn. The phrase "no longer accepting applications" did not appear on any guest page in the probe of 2026-11-20 (it seems to be shown only when logged in). A default that was never seen to match is left out. LinkedIn's expired postings are caught by the redirect marker and by 404. A user who sees such a phrase on a guest page can add a rule to the policy pack.
- Skipping the rendered step after a 404 at intake. Only a closed redirect ends the ladder early (D4).

## Decisions

### D1 Availability as an optional field on the posting

`Posting.availability: {state: "available"|"closed"|"unknown", set_at, set_by: "check"|"user"} | None`. Absent means never checked. The pool reads it with the posting, so it needs no second lookup. Rejected: a file per posting, which every pool load would read as well. The field is optional and keeps the schema version, as the policy pack's later fields did. A version 1 or 2 file without it stays valid. Rejected: a version 3. It would tell an external writer nothing it has to do differently, since the field is optional.

### D2 Closed rules: defaults in code, the policy pack adds

`ClosedRule {host, redirect_marker?, text_marker?}`, with exactly one marker and `host` matching `HOST_PATTERN`. A validation error names `closed_rules[<index>]`. `DEFAULT_CLOSED_RULES` sits beside `DEFAULT_LOGIN_WALL_HOSTS` and holds LinkedIn's `trk=expired_jd_redirect`. `closed_rules(policy_pack)` returns the defaults and the policy pack's rules. Why the policy pack's rules add to the defaults instead of replacing them: [ADR 0014](../../../docs/decisions/0014-closed-rules-add-to-the-code-defaults.md). The docstrings of `login_wall_hosts` and `closed_rules` say which one replaces and which one adds.

- A rule's host matches itself and its subdomains, as `is_login_walled` does.
- A redirect marker is matched as a substring of a hop's full address.
- A text marker is matched, ignoring case, against `html_text(html)` of the whole page. That is the visible text without scripts, styles, navigation, header, footer, form controls and consent blocks (`SKIPPED_TAGS`, `CONSENT_MARK`). It is not matched against the raw HTML: the probe found "no longer available" in script text on a live page. It is not matched against the posting text that `page_from_html` cuts out of a LinkedIn page either. A rule for text inside a skipped element cannot match. That is the price of not matching script text.

### D3 Recognition inside the fetch

- The rules reach `fetch` through a context variable `closed_rules`, default `DEFAULT_CLOSED_RULES`. This is the same mechanism as `guarded_link`. It avoids threading a rules argument through `fetch_posting`, `fetch_plain`, `download_plain`, `download_rendered` and the loop's tools. It is set from the policy pack by:
  - `find_posting`, which covers the ladder and the intake loop;
  - the check's worker;
  - the agent's `fetch_posting` tool;
  - the research tool's plain fetch.
  
  `fill_company_facts` keeps the default, and it counts a closed redirect as settled, like a 404.
- `download_plain` always installs a hop hook. A hop whose address matches a redirect marker for its host raises `FetchError(CLOSED_REDIRECT)` before the request is sent. The guarded refusal runs after it, so an expired LinkedIn link from a mail is closed, not refused.
- `download_rendered` always installs its route check. The check asks the closed question first and the guarded question only while `guarded_link == url`. Without this, a plain fetch that ends in a 429 would hand the link to Chromium, which would follow the expired redirect and render the search page.
- `page_from_html` checks text markers before the posting-text gate:
  - With a marker and no qualifying posting text, it raises `FetchError(CLOSED_TEXT)`.
  - With a marker and posting text, it returns the `Page` with `closed=True`.
- The check calls `download_plain(url, retry=False)` and then `closed_by_text(url, html)`. It does not need posting text: a page that answers 200 with no marker is available, even when `page_from_html` would find no posting in it. The single attempt keeps the immediate second request after a 429 from hitting the rate limit again and breaking the host spacing.

Rejected: matching the final address after the redirect was followed. That works only unguarded, and it sends a request to a page known to be dead.

### D4 Intake: a closed page is gone

- `GONE_OUTCOMES` gains `CLOSED_REDIRECT` and `CLOSED_TEXT`, so `is_gone` and the import's "link gone" count cover both without further change.
- `fetch_posting` stops after either attempt. A 404 still runs the rendered step as before.
- `find_posting` keeps `search_if_gone`.
  - A new link (single link, several links, alert mail entry) still runs the intake loop after a closed attempt, so a posting gone at one address can still be found at another.
  - The import keeps passing `False`.
  - The loop's own fetch tools run under the same `closed_rules`, so the loop never stores a closed page either.
- `PostingNotFoundError` gains `closed: bool`, which is `is_gone` of the submitted URL's attempts. It is true only after the loop also found nothing.
  - `POST /postings` answers 422 with `"closed": true`.
  - `POST /postings/batch` answers `outcome: "closed"`.
  - The alert run reports `state: "closed"`, and its `done` count includes closed entries (`alert_runs.py`, the count over finished states).
- A `Page` with `closed` is stored with `availability {closed, now, check}`.

### D5 The check

New module `availability.py`:

- **Selection** (`check_batch`): the batch is computed when the check starts and is the size `GET /pool` announces. A posting is in it when:
  - its application status is `open`;
  - its availability is not closed and not `set_by: user`;
  - it has at least one URL whose host is not login-walled (`login_wall_hosts`).
- `check_posting(posting) -> state`:
  - Each non-walled URL is fetched in order, with `guarded_link` set to it, as the alert run sets it. A refused hop gives `unknown`.
  - The first URL that answers 200 with no text marker gives `available`.
  - If every fetched URL answers 404, 410 or `CLOSED_REDIRECT`, or 200 with a text marker, the posting is `closed`.
  - Anything else gives `unknown`: a 429, a timeout, a refused hop, or another HTTP error.
- **Spacing:** a `Throttle(HOST_SPACING_SECONDS = 3)` instance of `intake/company_facts.Throttle` spaces requests per host. The batch is interleaved by host, round-robin, so other hosts go on while LinkedIn waits. The spike still saw 429s at 3 s. Those postings end as `unknown`, and the next check tries them again. A slower spacing would mostly lengthen every check.
- **Runs:** `AvailabilityChecks` follows the alert runs:
  - one check at a time (`CheckBusyError(check_id)`);
  - a `ThreadPoolExecutor` of one;
  - state in memory: `{check_id, status: running|done|failed, total, done, counts: {available, closed, unknown}, closed: [{posting_id, title, company}], error}`.
- **Write by a check:** `write_availability(root, posting_id, availability)` is gated. It re-reads the file under `write_gate` and writes nothing when the file's availability is `set_by: user`, or when the posting no longer exists (#113 (Delete a posting permanently from the web app)). A hand setting made while the check runs therefore survives.
- **Write by the user:** `PATCH /postings/{id}` writes unconditionally through `update_posting`, so one hand setting can replace another.

### D6 API

- `POST /availability/checks` → 202 `{check_id, total}`, or 409 `{error, check_id}` while one runs.
- `GET /availability/checks/{id}` → the state, or 404 for an unknown check.
- `GET /pool` adds `next_check: {total}`.
- `PATCH /postings/{id}` accepts `availability: "available"|"closed"` and writes `{state, now, user}`. `availability: "check"` removes the key („Wieder automatisch prüfen“), so the posting counts as never checked. Removing it does not keep the last state as set by a check, because no check set it. `"unknown"` answers 422. `update_posting` gains key removal for this.
- `POST /postings/{id}/score` keeps refusing only held and excluded postings. A closed posting can be scored on request; only the pass leaves it out.
- Pool rows gain `availability` (the stored dict, or null).

### D7 The pool and the agent

- `rank` keeps closed rows, since the posting page and the rating answer look rows up in it.
  - `_explore` gets only the open, not-closed rows of the unrated scored group. Closed rows are appended after the picks, as rows of another status are today, and each row appears once.
  - `pass_batch` leaves closed postings out. That carries through to `next_pass` and the pass's own batch in `triage/graph.py`.
  - `best_open` leaves closed rows out.
- `counter` and the judge's rated examples are untouched, so a closed posting's rating keeps counting.
- `find_postings` and `find_similar_postings` add `closed: true` to a closed match. `best_open_postings` cannot return one. `research_company` returns a stored posting as research material, not as a match to choose, and stays unchanged. No tool writes availability.

### D8 Web UI

- In `FILTERS`, „Offen“, „Noch nicht bewertet“ and „Bewertet“ require `availability?.state !== "closed"`. A new entry „Geschlossen“ keeps open-status rows that are closed.
- The check button, its disabled state with the info icon, its progress and report, the closed mark on a row, the availability block with its hand setting on the posting page, and „Stelle geschlossen“ in the intake and alert views follow a Design artifact on the „JobAdvAIsor Design System“. It is drawn before the UI tasks start and linked here.
- The view remembers a running check's ID in `localStorage`, like the pass, so a reload resumes the poll.

## Risks / Trade-offs

- [An employer's site answers 404 for a moment and the posting is closed wrongly] → The user reopens it by hand on its page, and a check never overwrites that.
- [LinkedIn changes its redirect marker] → Postings then stay available, so nothing is closed wrongly. A new default rule fixes it, or the user adds a rule to the policy pack.
- [Rate limits leave many postings unknown] → They stay in the pool, the next check tries them again, and the report names the count.
- [A context variable set in one thread is not seen in another] → It is set in the thread that fetches, as `guarded_link` is in the alert run.
- [#113 (Delete a posting permanently from the web app) changes the same files and modifies some of the same requirements: posting-pool „Filters“, possibly „Ranking by fit“ and „Scoring pass on request“, and the web-ui pool view] → Whichever branch merges second merges `origin/main`, keeps both sides of each modified requirement, and archives after the other change.

## Migration Plan

None for the data: both fields are optional, and existing postings count as never checked until the first check.

Rollback means deploying the previous release. After a check has run, every posting that carries `availability` then fails to load, because `Entity` forbids unknown fields. A rollback after a check therefore needs that key removed from each posting file first. The data repository's git history shows which files the check changed.

## Evaluation

No LLM behaviour is added or changed. The intake loop gets the same input as before, and the agent's tools gain a `closed` flag in their structured results, which is a tool contract tested in the default `pytest`. The rule matching, the check's outcomes and the pool filters get regression tests too. Their fixtures are synthetic pages behind an httpx mock transport, one per outcome:

- open;
- HTTP 404 and 410;
- a redirect to a marker;
- a page text marker with and without posting text;
- HTTP 429;
- a timeout.
