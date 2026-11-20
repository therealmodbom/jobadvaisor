# Proposal

## Why

On `main` a posting has an application status (`open`, `applied`, `done`) but nothing says whether the employer still accepts applications. The pool, the ranking, the agent's recommendations and the scoring pass treat every stored posting as live. A probe of the 67 postings of a real pool on 2026-11-20 found about a third of them gone: about 20 links answered HTTP 404 or 410, and 6 to 7 LinkedIn links redirected to a search page instead of the posting. The user has to open each one by hand to find out, and each pass pays a judge call for postings nobody can apply to any more (#40).

Intake has the same blind spot. A LinkedIn link whose posting expired is stored as a posting today: the plain fetch follows the redirect, and the search page "similar jobs" (about 10,000 characters, no posting in it) becomes the posting text. From a job-alert mail the same link fails with "redirect with personal parameters", because the redirect target carries `trk=expired_jd_redirect`.

## What Changes

- Each posting gains an availability: `available`, `closed` or `unknown`. It records when it was last set and whether the check or the user set it. It is separate from the application status. A posting without it has never been checked and counts as not closed.
- A check of availability that the user starts in the pool view, „Verfügbarkeit prüfen“. It fetches every posting with status open that is not closed and that the user did not set by hand. It runs in the background, one at a time, and reports how many postings it found closed, available and unknown. No model call.
- What counts as closed: a link answering HTTP 404 or 410, or a match of a closed rule. A closed rule names a host and either a redirect target marker (a text the address of a redirect contains) or a page text marker (a text the page contains). Default rules live in the code, starting with LinkedIn's `trk=expired_jd_redirect`. The policy pack MAY hold more rules, which add to the defaults. A rate limit (HTTP 429), a timeout or any other failure gives `unknown`, which never closes a posting.
- Closed postings leave the default pool view, the filters „Offen“, „Noch nicht bewertet“ and „Bewertet“, the scoring pass, the exploration picks and the agent's best-fitting postings. A new filter „Geschlossen“ lists them. Their page stays reachable, and they can still be rated. A rating of a closed posting still counts for the correction counter and as a scoring example.
- The user sets the availability by hand, in both directions, from the posting page. A check never overwrites a hand setting.
- Intake treats a closed rule like a gone link. A redirect target marker or HTTP 404/410 on the submitted link means the page was replaced: nothing is stored, and the answer, the import report and the alert run say the posting is closed. A page text marker means the posting text is still there: the posting is stored at once with availability `closed`.
- The look and position of „Verfügbarkeit prüfen“, its report, the filter „Geschlossen“ and the hand setting are settled in a Design artifact on the JobAdvAIsor design system and linked from `design.md`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `posting-pool`: adds „Availability of a posting“, „Availability check on request“, „One check at a time“, „What a check covers“, „Closed by a gone link or a closed rule“, „Unknown never closes a posting“, „Closed rules from code and policy pack“, „Hand setting of availability“, „Closed postings leave the ranking“ and „Ratings of closed postings still count“.
- `posting-intake`: adds „Closed page at intake“ and „Closed page text stored as closed“; modifies „Closed postings are not imported“ (a redirect marker counts like a gone link).
- `job-agent`: adds „Closed postings are no recommendation“, „Agent tools name a closed posting“ and „Agent sets no availability“.
- `web-ui`: adds „Availability check in the pool view“, „Availability check refused or lost“, „Filter Geschlossen“, „Availability on the posting page“ and „Closed outcome at intake“.
- `data-repository`: adds „Availability stored with the posting“ and „Closed rules in the policy pack“.

## Impact

- Backend:
  - new `availability.py`: the rule matching, the check of one posting and the background run of a check (one at a time, state in memory, like the alert runs).
  - `intake/fetch.py`: the hop check (`_check_hop`) and the plain fetch learn about redirect target markers, so a closed redirect is recognised before the hop is refused or followed.
  - `intake/ladder.py`, `intake/postings.py`, `intake/imports.py`, `intake/alert_runs.py`: a closed page counts as gone; a page text marker stores the posting as closed.
  - `pool.py`: rows carry `availability`; `pass_batch`, `next_pass`, `best_open` and the exploration picks leave closed postings out.
  - `api/app.py`: start and read a check, the hand setting through `PATCH /postings/{id}`, the intake answers name a closed posting.
  - `data/models.py`, `data/writer.py`: `Posting.availability`, `PolicyPack.closed_rules`, a locked write of the availability alone; the generated `schemas/posting.schema.json` and `schemas/policy-pack.schema.json`.
- Frontend: `api.ts`, `views/PoolView.tsx` (check button, report, filter), the posting page view (hand setting), the import and intake views (closed outcome), their tests and the e2e walkthrough.
- Data format: two optional fields, `availability` on a posting and `closed_rules` in the policy pack. Existing files stay valid and keep their schema version.
- Docs: the README pool workflow section, the AGENTS.md "Current state" section, an ADR on closed rules adding to the defaults.

## Non-goals

- A scheduled check in the background. It becomes a follow-up issue; this change has only the check the user starts.
- A UI editor for the policy pack's own closed rules. It becomes a follow-up issue; this change reads them from the policy pack.
- Deleting closed postings (#113 (Delete a posting permanently from the web app)).
- A second round inside one check for postings that answered 429. The next check the user starts picks them up.
- Checking postings with status „beworben“ or „erledigt“, or postings already closed.
- Rendering pages in a browser for the check. It uses the plain fetch only.
- A new eval. No model is involved; the rule matching gets regression tests in the default `pytest`.
