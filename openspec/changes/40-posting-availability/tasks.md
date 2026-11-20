# Tasks

## 0. Look

- [x] 0.1 Draw a Design artifact on the „JobAdvAIsor Design System“. It covers:
  - „Verfügbarkeit prüfen“ with its count, its disabled state with the info icon, its progress, its cancel and its report in the pool view;
  - the filter „Stelle geschlossen“ and the closed mark on a row;
  - the availability with the hand setting on the posting page;
  - „Stelle geschlossen“ in the intake view, among several links and in the alert run.

  The chosen variant, its link and its texts are recorded in `design.md` → D8. Verified when `design.md` links the artifact and names the chosen variant.

## 1. Backend: data, rules and recognition

- [x] 1.1 Add the data fields:
  - `Availability` and `Posting.availability` (D1);
  - `ClosedRule`, with exactly one marker and a `HOST_PATTERN` host, and `PolicyPack.closed_rules` (D2);
  - in the docstrings of `login_wall_hosts` and `closed_rules`, which one replaces the defaults and which one adds to them.

  Regenerate `schemas/posting.schema.json` and `schemas/policy-pack.schema.json`. Verify with `test_schemas.py` and `test_data_models.py`:
  - a version 1 and a version 2 posting without the field load;
  - a rule with no marker or both, or a malformed host, fails, and the error names the file and `closed_rules[<index>]` (spec: Closed rules in the policy pack).
- [x] 1.2 Add the rule functions:
  - `DEFAULT_CLOSED_RULES`;
  - `closed_rules(policy_pack)`;
  - host matching with subdomains;
  - `closed_by_text(url, html)` over `html_text`, ignoring case.

  Verify with unit tests:
  - an own rule adds to the LinkedIn default;
  - a subdomain matches;
  - a marker inside `<script>` does not match (spec: Page text marker reads the visible page).
- [x] 1.3 Add recognition in the fetch (D3):
  - the `closed_rules` context variable;
  - the always-installed hop hook in `download_plain`, raising `CLOSED_REDIRECT` before the hop is sent and before the guarded refusal;
  - `download_plain(retry=False)`;
  - the always-installed route check in `download_rendered`;
  - `page_from_html` checking text markers before the posting-text gate (`CLOSED_TEXT`, `Page.closed`).

  Verify with httpx mock transport tests in `test_intake_fetch.py` and `test_redirect_guard.py`:
  - a redirect to `…?trk=expired_jd_redirect` raises `CLOSED_REDIRECT`, guarded and unguarded, and the mock records no request to the target;
  - `retry=False` sends one request on a 429;
  - a short page with a marker raises `CLOSED_TEXT`, and a long one gives `Page.closed`.

  Also test the rendered fetch: an unguarded link whose plain fetch ends in a 429 and whose rendered fetch redirects to the marker raises `CLOSED_REDIRECT`, and Chromium requests no target (Playwright route test).
- [x] 1.4 Add both writes:
  - `write_availability`, a gated re-read that writes nothing over `set_by: user` or for a missing posting;
  - `PATCH /postings/{id}` `availability`, written unconditionally (D5, D6).

  Verify with writer tests:
  - a hand setting made between the check's read and its write survives;
  - other keys and the schema version stay unchanged.

  Then verify with `test_api.py` (`Api(Harness(…))`):
  - close by hand, then reopen by hand;
  - `"check"` removes the key, and the posting is back in `check_batch`;
  - a 422 for `"unknown"`;
  - `POST /postings/{id}/score` scores a closed posting and leaves it closed.

  Specs: Hand setting of availability, Hand setting returned to the check, Single score of a closed posting.

## 2. Backend: intake, check, pool, agent

- [x] 2.1 Intake (D4):
  - `CLOSED_REDIRECT` and `CLOSED_TEXT` join `GONE_OUTCOMES`;
  - `fetch_posting` stops after either;
  - `find_posting`, the agent's `fetch_posting` tool and research set `closed_rules` from the policy pack;
  - `PostingNotFoundError.closed`;
  - the closed answers in `POST /postings` and `/postings/batch`, and in the alert run, whose `done` count includes closed;
  - a `Page.closed` is stored as closed.

  Verify with `test_intake_postings.py`, `test_intake_batch.py`, `test_import.py`, `test_alert_runs.py` and `test_api.py`. Each of these needs a test:
  - a 404 or redirect-marker link still runs the loop, and the target is never fetched;
  - a link whose loop finds nothing answers 422 with `closed: true`;
  - a link whose loop finds the posting elsewhere stores it with both URLs;
  - the batch answers `outcome: "closed"`;
  - the alert run gives `state: "closed"` and counts it as done;
  - the import counts a redirect marker as link gone;
  - a long page with a text marker is stored closed, set by check.

  Specs: Closed page at intake, Closed when no other source holds the posting, Closed page text stored as closed, Chosen entries added in the background, Closed postings are not imported.
- [x] 2.2 `availability.py` (D5) needs:
  - `check_batch`, which drops applied, closed, hand-set, linkless and login-walled-only postings;
  - `check_posting` over the non-walled URLs with `guarded_link` set;
  - round-robin host order and a `Throttle(HOST_SPACING_SECONDS)`;
  - `AvailabilityChecks`.

  Verify with mock-transport tests and an injected clock and sleep:
  - open, 404, 410, a redirect marker, a text marker, 429 and a timeout each give the right state;
  - 404 plus a live link gives available;
  - 404 plus a timeout gives unknown;
  - a refused hop gives unknown;
  - excluded postings are not fetched;
  - two requests to one host are 3 s apart, and a 429 is not retried;
  - a second start raises `CheckBusyError`.

  Specs: What a check covers, Closed by a gone link or a closed rule, Unknown never closes a posting, One check at a time, Report of a check.
- [x] 2.3 API (D6):
  - `POST /availability/checks` (202, or 409 with `check_id`);
  - `GET /availability/checks/{id}` (404 when unknown);
  - `GET /pool` `next_check`;
  - `availability` on pool rows.

  Verify with `test_api.py`.
- [x] 2.4 Pool (D7): `pass_batch`, `next_pass`, `best_open` and the `_explore` input leave closed postings out, and `rank` keeps them, each once. Verify with `test_pool.py`:
  - a closed posting, scored or not, is in neither pass variant's batch nor counted in `next_pass`;
  - it gets no exploration mark;
  - a closed scored unrated row appears once, in rank order;
  - it is not in `best_open`;
  - its rating still counts in `counter`.

  Also verify with graph tests in `test_triage_graph.py`:
  - the pass's batch skips a closed posting;
  - a posting closed on disk after the batch was taken, before `score` reaches it, gets no judge call and no new score, and counts as done. Specs: A pass leaves closed postings out, No exploration mark on a closed posting, Ratings of closed postings still count, Ranking by fit.
- [x] 2.6 Cancel a check (D5, D6): `AvailabilityChecks.cancel` sets `cancel_requested`, the worker stops before the next posting and ends `cancelled`; `POST /availability/checks/{id}/cancel` (202, 404, 409). Verify with tests: a cancel after some postings fetches no further posting, keeps the written results and reports their counts; a cancel of an ended check answers 409; an unknown ID 404 (spec: Cancel a check).
- [x] 2.5 Agent tools (D7): `find_postings` and `find_similar_postings` mark `closed: true`, and no tool writes availability. Verify with `test_agent.py` (spec: Closed postings are no recommendation, Search results mark a closed posting, No silent data changes).

## 3. Frontend

- [x] 3.1 `api.ts`: types for `availability`, `next_check`, the check state with `cancelled` and `cancel_requested`, the closed intake outcomes and the `PATCH` field. Verify with `npm --prefix frontend run build`.
- [x] 3.2 `PoolView.tsx`, layout and pass (D8):
  - the pool head in two columns, each action with its status below it;
  - the counter line under the pass button instead of the cost line, and the pass's disabled reason in an info icon;
  - the pass's progress, storing hint and cancel notice in its column;
  - the settings form moved out of the view (3.4).

  Verify with `PoolView.test.tsx`: the existing pass tests pass with the new placement; starting or ending a pass leaves the check button where it was. Specs: Pool view, Pass progress below the pass button, Cancel button of a pass, No cancel while storing, Result of a cancelled pass, Pass button, Counter line below the pass button.
- [x] 3.3 `PoolView.tsx`, check and filter:
  - the filters, with „Stelle geschlossen“ before „Herkunft“;
  - the mark „Stelle geschlossen“ on a row, and „Bewerbungsstatus“ as the rows' status label;
  - „Verfügbarkeit prüfen“ with its count, disabled state, info icon, „Prüfen abbrechen“, progress, report with three links and the rest behind a toggle, dismiss, and the 409 and lost-check states;
  - the check ID kept in `localStorage`;
  - the new controls in the keyboard shortcut exclusion.

  Texts follow D8. Verify with `PoolView.test.tsx`, including axe checks of the running, report and disabled states. Specs: Availability check button, Availability check progress and report, Cancel button of a check, Availability check refused or lost, Filter Stelle geschlossen, Closed mark on a row, Labels for application status and availability.
- [x] 3.4 `App.tsx`: the settings icon button „Einstellungen“ at the right end of the header, after the backup control, opening the threshold and rate form in a panel anchored to it, closed by Escape, from every view. Verify with `App.test.tsx`: the panel opens from the intake view, saving changes the pool's hint, Escape closes it and focus returns to the button (spec: Settings in the header).
- [x] 3.5 `PostingPage.tsx`: under the title one row with „Bearbeiten“, „Bewerbungsstatus“ and „Verfügbarkeit“; the note with its time and setter or „nicht geprüft“; the hand setting; „Wieder automatisch prüfen“ for a hand setting; the old status row removed. The score button stays enabled for a closed posting. Verify with `PostingPage.test.tsx` (specs: Availability on the posting page, Labels for application status and availability).
- [x] 3.6 `IntakeView.tsx` and `AlertMailView.tsx`: „Stelle geschlossen“ with its attempts and no text or PDF option, for a single link, among several links and for an alert run entry. Verify with `IntakeView.test.tsx` and `AlertMailView.test.tsx` (spec: Intake view, Several links at once, Alert mail run progress and outcome).

## 4. End to end and docs

- [ ] 4.1 Add an e2e walkthrough over a demo copy:
  - every demo URL is answered by a stubbed fetch, so no request leaves the machine;
  - `HOST_SPACING_SECONDS` is patched to 0;
  - one posting answers 404 and one redirects to the marker;
  - start a check and see the report;
  - find both postings under „Stelle geschlossen“;
  - rate one, and reopen one by hand.

  Verify with `env -C backend uv run pytest -m e2e -q` after `npm --prefix frontend run build`.
- [ ] 4.2 Click test in the browser against the real dev server on a demo copy, whose `example.com`/`example.org` links answer as unknown or not at all. Start a check and read the report, which shows unknowns. Cancel a second check. Close one posting by hand, find it under „Stelle geschlossen“, rate it and reopen it. Open „Einstellungen“ in the header. Verify by screenshots in the PR description.
- [ ] 4.3 Update the README pool workflow section and the AGENTS.md "Current state" section, and retake `docs/images/pool.png` and `posting.png` with `scripts/readme_images.py`. Verify that the README describes the check and the filter, and that both images show the new controls.
- [ ] 4.4 File the follow-up issues for a scheduled check and for a UI editor of the policy pack's closed rules. Verify that both issue numbers are named in the PR description.
- [ ] 4.5 Run every check: `env -C backend uv run pytest -q`, `env -C backend uv run pytest -m e2e -q`, `env -C backend uv run ruff check .`, `npm --prefix frontend test`, `npm --prefix frontend run lint` and `npm --prefix frontend run build`. Verified when all of them pass and the `push` CI run on the branch head is green (the `pull_request` run skips every job except gitleaks, so it hides a red e2e job).
