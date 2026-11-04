# Tasks

## 1. Pay range box

- [x] 1.1 Add a fictional pay range box (employer name, explanatory sentence, base pay range) to `fixtures/intake/pages/linkedin-guest.html`, above the description
- [x] 1.2 Failing tests in `backend/tests/test_intake_fetch.py`: the box's wording and figures are in the stored text, before the description; the page without a box (the short-description case) stores none; a page with criteria but no description falls back to the visible text
- [x] 1.3 Capture the `compensation` class in `backend/jobadvaisor/intake/fetch.py` until the tests pass; description, criteria and pay box are separate captures and the description is required
- [x] 1.4 Run the backend test suite; check live pages with and without a pay box
