# Tasks

## 1. Cut at fetch

- [x] 1.1 Add a fictional LinkedIn-shaped guest page under `fixtures/` (header, description, criteria block, sign-in blocks, similar jobs, footer), plus a variant with a short description; no real posting text
- [x] 1.2 Failing tests in `backend/tests/test_intake_fetch.py`: description and criteria kept; no sign-in, similar-job or footer text; title, company and location supplied from the header; a short description is kept without chrome; a page without a description falls back to the visible text; a page with JSON-LD is unchanged
- [x] 1.3 Implement the cut and the header fields for linkedin.com pages in `backend/jobadvaisor/intake/fetch.py` until the tests pass
- [x] 1.4 Run the backend test suite and fix regressions

## 2. Real check

- [x] 2.1 Run intake on one real LinkedIn URL against a throwaway data repository and check the stored text (length, no chrome) and the three fields

## 3. Stored postings

- [x] 3.1 One-off repair script: takes the data repository path, dry run by default, cuts stored LinkedIn texts by the whole-page layout, leaves other texts unchanged, prints a report of changed and unchanged postings
- [x] 3.2 Test the script on a fictional repository with a matching and a non-matching text
- [x] 3.3 Run it against the user's data after a dry run, German and English postings checked in the report first (rescoring is a decision for the user, via "Neue Anzeigen bewerten")

## 4. Login-wall default (decision)

- [x] 4.1 If the user confirms: remove `linkedin.com` from `DEFAULT_LOGIN_WALL_HOSTS` in `backend/jobadvaisor/intake/ladder.py` (`xing.com` stays), and update the tests and the intake eval's LinkedIn case

## 5. Docs

- [x] 5.1 Update the "Current state" in README/AGENTS.md if behavior changed
