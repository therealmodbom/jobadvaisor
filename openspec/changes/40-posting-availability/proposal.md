# Proposal

## Why

On `main` a posting has an application status (`open`, `applied`, `done`), but nothing says whether the employer still accepts applications. The pool, the ranking, the agent's recommendations and the scoring pass treat every stored posting as live.

A probe of a real pool on 2026-11-20 found about a third of its links gone. Most answered HTTP 404 or 410. A smaller share were LinkedIn links that redirected to a search page instead of the posting. The user has to open each posting by hand to find out, and each pass pays a judge call for postings nobody can apply to any more (#40 (Track whether a posting is still open)).

Intake has the same blind spot. Today a LinkedIn link whose posting expired is stored as a posting. The plain fetch follows the redirect, and the search page "similar jobs" becomes the posting text: about 10,000 characters with no posting in them. From a job-alert mail the same link fails with "redirect with personal parameters", because the redirect target carries `trk=expired_jd_redirect`.

## What Changes

- Each posting gains an availability: `available`, `closed` or `unknown`.
  - It records when it was last set and whether the check or the user set it.
  - It is separate from the application status.
  - A posting without it has never been checked and counts as not closed.
- The user starts a check of availability, „Verfügbarkeit prüfen“, in the pool view.
  - It fetches every posting with status open that has a link, is not closed and was not set by hand.
  - It runs in the background, one at a time, and makes no model call.
  - It reports how many postings it found closed, available and unknown.
- What counts as closed: a link answering HTTP 404 or 410, or a match of a closed rule.
  - A closed rule names a host and either a redirect marker (a text the address of a redirect contains) or a page text marker (a text the visible page contains).
  - Default rules live in the code, starting with LinkedIn's `trk=expired_jd_redirect`. The policy pack MAY hold more rules, which add to the defaults.
  - A rate limit (HTTP 429), a timeout or any other failure gives `unknown`, which never closes a posting.
- Closed postings leave:
  - the default pool view;
  - the filters „Offen“, „Noch nicht bewertet“ and „Bewertet“;
  - the scoring pass;
  - the exploration picks;
  - the agent's best-fitting postings.
  
  A new filter „Geschlossen“ lists them. Their page stays reachable, and they can still be rated. A rating of a closed posting still counts for the correction counter and as a scoring example.
- The user sets the availability by hand, in both directions, from the posting page. A check never overwrites a hand setting. „Wieder automatisch prüfen“ removes the hand setting, so the next check covers the posting again.
- A closed posting can still be scored on request from its page. Only the pass leaves it out.
- Intake treats a closed rule like a gone link.
  - A redirect marker, HTTP 404/410, or a page text marker on a page without posting text means the page was replaced. Nothing from it is stored, and a redirect target that a marker matches is never requested.
  - A new link is still looked for at another source, as today. When none yields it, the answer and the alert run say the posting is closed. The import skips it as link gone, as today.
  - A page text marker on a page that still holds the posting text stores the posting at once with availability `closed`.
- A Design artifact on the JobAdvAIsor design system settles the look and position of:
  - „Verfügbarkeit prüfen“ and its report;
  - the filter „Geschlossen“;
  - the hand setting;
  - „Stelle geschlossen“.
  
  It is linked from `design.md`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `posting-pool`: adds „Availability of a posting“, „Availability check on request“, „Report of a check“, „One check at a time“, „What a check covers“, „Closed by a gone link or a closed rule“, „Unknown never closes a posting“, „Closed rules from code and policy pack“, „Page text marker reads the visible page“, „Hand setting of availability“, „Hand setting returned to the check“, „Single score of a closed posting“, „A pass leaves closed postings out“, „No exploration mark on a closed posting“ and „Ratings of closed postings still count“. Modifies „Ranking by fit“, „Filters“, „Scoring pass on request“, „Postings without a score in the range“ and „Default pass variant“.
- `posting-intake`: adds „Closed page at intake“, „Closed when no other source holds the posting“ and „Closed page text stored as closed“. Modifies „Input forms“, „Links from a mail carry no personal parameters“, „Chosen entries added in the background“ and „Closed postings are not imported“.
- `job-agent`: adds „Closed postings are no recommendation“ and „Search results mark a closed posting“. Modifies „No silent data changes“.
- `rating-feedback`: modifies „Cold-start labels“, since an unlabeled closed posting is listed under „geschlossen“.
- `web-ui`: adds „Availability check button“, „Availability check progress and report“, „Availability check refused or lost“, „Filter Geschlossen“, „Closed mark on a row“ and „Availability on the posting page“. Modifies „Intake view“, „Several links at once“ and „Alert mail run progress and outcome“.
- `data-repository`: adds „Availability stored with the posting“ and „Closed rules in the policy pack“.

## Impact

- Backend:
  - New `availability.py`: the check of one posting, the batch, and the background run of a check, one at a time with state in memory, like the alert runs.
  - `intake/fetch.py`: the `closed_rules` context variable. The plain fetch's hop hook and the rendered fetch's route check recognise a redirect marker before the hop is sent, guarded or not. `page_from_html` recognises a page text marker. `download_plain` gains a single-attempt mode.
  - `intake/ladder.py`, `intake/postings.py`, `intake/alert_runs.py`, `api/app.py`: a closed page counts as gone, a closed outcome reaches the answers, a page text marker stores the posting as closed. `intake/imports.py` and `data/fill_company_facts.py` pick up the closed outcomes through `GONE_OUTCOMES`.
  - `pool.py`: rows carry `availability`. `pass_batch`, `next_pass`, `best_open` and the exploration picks leave closed postings out.
  - `api/app.py`: starting and reading a check, `next_check` on the pool, the hand setting through `PATCH /postings/{id}`.
  - `agent/__init__.py`, `tools/research.py`: the closed mark in search results and the policy pack's rules for their fetches.
  - `data/models.py`, `data/writer.py`: `Posting.availability`, `PolicyPack.closed_rules`, a gated write of the availability by a check, and the generated `schemas/posting.schema.json` and `schemas/policy-pack.schema.json`.
- Frontend: `api.ts`, `views/PoolView.tsx` (check button, report, filter, closed mark), `views/PostingPage.tsx` (availability and hand setting), `views/IntakeView.tsx` and `views/AlertMailView.tsx` (closed outcome), their tests and the e2e walkthrough.
- Data format: two optional fields, `availability` on a posting and `closed_rules` in the policy pack. Existing files stay valid and keep their schema version. A release from before this change cannot load a posting that a check has written to.
- Docs: the README pool workflow section and images, the AGENTS.md "Current state" section, ADR 0014 on closed rules adding to the defaults.

## Non-goals

- A scheduled check in the background. It becomes a follow-up issue. This change has only the check the user starts.
- A UI editor for the policy pack's own closed rules. It becomes a follow-up issue. This change reads them from the policy pack.
- Deleting closed postings (#113 (Delete a posting permanently from the web app)).
- A second round inside one check for postings that answered 429. The next check the user starts picks them up.
- Checking postings with status „beworben“ or „erledigt“, postings already closed, and postings without a link.
- Rendering pages in a browser for the check. It uses the plain fetch only.
- A default page text marker for LinkedIn (see `design.md` → Non-Goals).
- A new eval. No model input changes in a way an eval would measure. The rule matching and the tools' closed mark get regression tests in the default `pytest`.
