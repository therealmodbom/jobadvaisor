# Tasks

## 0. Look

- [ ] 0.1 Draw a Design artifact on the „JobAdvAIsor Design System“ covering:
  - „Verfügbarkeit prüfen“ with its count, its progress and its report in the pool view;
  - the filter „Geschlossen“ and the closed mark on a row;
  - the availability block with the hand setting on the posting page;
  - „Stelle geschlossen“ in the intake view and the alert run.
  
  The owner picks the variant, and its link and texts are recorded in `design.md` → D8. Verified when `design.md` links the artifact and names the chosen variant.

## 1. Backend: data, rules and recognition

- [ ] 1.1 Add `Availability` and `Posting.availability` (D1), `ClosedRule` with exactly one marker, and `PolicyPack.closed_rules` (D2). Regenerate `schemas/posting.schema.json` and `schemas/policy-pack.schema.json`. Verify with `test_schemas.py` and with model tests:
  - a version 1 and a version 2 posting without the field load;
  - a rule with no marker or both fails with the policy pack file named (spec: Closed rules in the policy pack).
- [ ] 1.2 Add `DEFAULT_CLOSED_RULES` and `closed_rules(policy_pack)` (defaults first, then the pack's rules). Add host matching with subdomains, and `closed_by_text(url, html)` over the visible page text, ignoring case. Verify with unit tests:
  - an own rule adds to the LinkedIn default;
  - a subdomain matches;
  - a marker that appears only inside `<script>` does not match.
- [ ] 1.3 Add the `closed_rules` context variable and the always-installed hop hook in `download_plain` that raises `FetchError(CLOSED_REDIRECT)` before a matching hop is sent and before the guarded refusal. Give `download_rendered`'s route check the same question, and set `Page.closed` in `page_from_html` (D3). Verify with httpx mock transport tests:
  - a redirect to `…?trk=expired_jd_redirect` raises `CLOSED_REDIRECT`, guarded and unguarded, and the mock records no request to the target;
  - a 200 page with a text marker gives `Page.closed`.
- [ ] 1.4 Add `write_availability` (gated re-read, no write over `set_by: user` or for a missing posting) and `PATCH /postings/{id}` `availability` (D5, D6). Verify with writer tests:
  - a hand setting made between the check's read and its write survives;
  - the posting's other keys and its schema version stay unchanged.
  
  Then `test_api.py` for both directions and a 422 for `"unknown"` (spec: Hand setting of availability).

## 2. Backend: intake, check, pool, agent

- [ ] 2.1 Intake (D4):
  - `CLOSED_REDIRECT` joins `GONE_OUTCOMES`;
  - `fetch_posting` stops after it;
  - the intake loop runs under the same `closed_rules`;
  - `PostingNotFoundError.closed`;
  - `POST /postings` 422 with `closed: true`, `/postings/batch` `outcome: "closed"`, the alert run `state: "closed"`;
  - a `Page.closed` is stored with availability closed.
  
  Verify with `test_intake_fetch.py`, `test_intake_postings.py`, `test_intake_batch.py`, `test_redirect_guard.py`, `test_import.py`, `test_alert_runs.py` and `test_api.py` (spec: Closed page at intake, Closed page text stored as closed, Closed postings are not imported):
  - a single 404 or redirect-marker link still runs the loop, the page behind the redirect is never fetched, and when the loop finds nothing the answer says closed;
  - the import counts a redirect marker as link gone.
- [ ] 2.2 `availability.py` (D5):
  - `check_batch`, `check_posting` over every stored URL (login-walled ones skipped), the round-robin host order with `HOST_SPACING_SECONDS`, and `download_plain(retry=False)`;
  - `AvailabilityChecks` (one at a time, state in memory, counts and the closed list).
  
  Verify with tests using a mock transport and an injected clock and sleep, so they wait for no real time:
  - open, 404, 410, a redirect marker, a text marker, 429 and a timeout each give the right state;
  - two URLs, one available, give available;
  - applied, closed and hand-set postings are not fetched;
  - a posting whose only URL is login-walled is unknown and not fetched;
  - two requests to one host are 3 s apart, and a 429 is not retried at once;
  - a second start raises `CheckBusyError` (spec: What a check covers, Closed by a gone link or a closed rule, Unknown never closes a posting, One check at a time).
- [ ] 2.3 API (D6): `POST /availability/checks` (202, 409 with `check_id`), `GET /availability/checks/{id}` (404 unknown), `GET /pool` `next_check`, and `availability` on pool rows. Verify with `test_api.py` through `ApiHarness`.
- [ ] 2.4 Pool (D7): `pass_batch`, `next_pass`, `best_open` and the `_explore` input leave closed postings out, and `rank` keeps them. Verify with `test_pool.py`:
  - a closed unscored posting is in no pass batch and not counted in `next_pass`;
  - it gets no exploration mark;
  - it is not in `best_open`;
  - its rating still counts in `counter` (spec: Closed postings leave the ranking, Ratings of closed postings still count).
  
  Also verify with a graph test that the pass's batch skips it.
- [ ] 2.5 Agent tools (D7) mark `closed: true` in `find_postings`, `best_open_postings` and `find_similar_postings`, and no tool writes availability. Verify with `test_agent.py` (spec: Closed postings are no recommendation, Agent tools name a closed posting, Agent sets no availability).

## 3. Frontend

- [ ] 3.1 `api.ts`: types for `availability`, `next_check`, the check state, the closed intake outcomes, and the `PATCH` field. Verify with `npm --prefix frontend run build`.
- [ ] 3.2 `PoolView.tsx`:
  - the filters „Offen“, „Noch nicht bewertet“ and „Bewertet“ exclude closed rows, and „Geschlossen“ lists them;
  - the closed mark on a row;
  - „Verfügbarkeit prüfen“ with count, progress, report, the 409 and lost-check states, and the ID kept in `localStorage`;
  - the new controls join the keyboard shortcut exclusion.

  Texts and placement follow the Design artifact. Verify with `PoolView.test.tsx`, including axe checks of the running and the report state (spec: Availability check in the pool view, Availability check refused or lost, Filter Geschlossen).
- [ ] 3.3 Posting page: the availability block with time, setter or „noch nie geprüft“, and the two hand-setting actions. Verify with its view test (spec: Availability on the posting page).
- [ ] 3.4 Intake view and alert run: „Stelle geschlossen“ with the attempts and without the text and PDF options. Verify with their view tests (spec: Closed outcome at intake).

## 4. End to end and docs

- [ ] 4.1 e2e walkthrough with stubbed fetches: start a check over the demo copy with one 404 and one redirect-marker posting, see the report, find both under „Geschlossen“, rate one, and reopen one by hand. Verify with `env -C backend uv run pytest -m e2e -q` after `npm --prefix frontend run build`.
- [ ] 4.2 Click test in the browser against the real dev server on a demo copy: start a check, read the report, use the filter, set by hand. Verify by screenshots in the PR description.
- [ ] 4.3 Update the README pool workflow section and the AGENTS.md "Current state" section. Retake `docs/images/pool.png` and `posting.png` with `scripts/readme_images.py` if the views change visibly. Verify that the README describes the check and the filter, and that `git status` shows the images only if they changed.
- [ ] 4.4 File the follow-up issues for a scheduled check and for a UI editor of the policy pack's closed rules. Verify both issue numbers are named in the PR description.
- [ ] 4.5 Run every check: `env -C backend uv run pytest -q`, `env -C backend uv run ruff check .`, `npm --prefix frontend test`, `npm --prefix frontend run lint` and `npm --prefix frontend run build`. Verified when all of them pass.
