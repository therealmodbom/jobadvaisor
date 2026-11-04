# Proposal

## Why

A LinkedIn guest page is stored whole: about 12.5k characters, of which the posting body is a fraction. The rest is sign-in blocks, "Similar jobs" lists of unrelated titles and the sign-in footer (issue comment of 2026-10-26). That noise costs tokens in every extraction and scoring call and can steer the judge. The guest HTML carries no JSON-LD `JobPosting`, so the general fetch always falls back to the whole page text.

## What Changes

- A posting fetched from a LinkedIn page stores the posting's description and its criteria block (seniority, employment type, industries, job function), and nothing else of the page. Title, company and location are read from the page header and supplied as fields, because the stored text no longer carries them.
- When the page has no recognisable description, the general behavior stays: the visible text is stored.
- A one-off repair reduces LinkedIn postings already stored whole to the same body without fetching them again, and reports the ones whose layout it does not recognise. Scores and features computed on the long text are redone only when the user asks; that is a paid run and the user's call.
- Whether `linkedin.com` leaves the default login-wall list is a separate decision (first criterion of the issue). It changes configuration, not a requirement, so it is not part of the spec delta.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `posting-intake`: a new requirement for what a LinkedIn page contributes to the stored text and fields. No existing requirement changes.

## Impact

- `backend/jobadvaisor/intake/fetch.py` (the cut and the header fields), `backend/tests/test_intake_fetch.py`, a fictional LinkedIn-shaped fixture under `fixtures/`.
- `backend/jobadvaisor/intake/ladder.py` and the intake eval's LinkedIn case, if the user removes `linkedin.com` from `DEFAULT_LOGIN_WALL_HOSTS`.
- A one-off repair script for stored LinkedIn texts; it takes the data repository path as an argument and is run outside this repository's workflow.

## Non-goals

- The Jev extractor measurement, ratings and the 7.2 eval (#30).
- Cutting the chrome of other portals; this change names LinkedIn only (bwi.de: #31).
- `xing.com` stays on the login-wall list.
- Changing the posting schema (no separate raw-text field).
