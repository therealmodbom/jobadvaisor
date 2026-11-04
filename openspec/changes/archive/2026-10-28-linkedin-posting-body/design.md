# Design

## Context

See proposal.md, Why. Observed on a real guest page (2026-10-28, `fetch_plain`): the HTML holds no JSON-LD `JobPosting`, so `page_from_html` takes the whole visible main text. The HTML has stable markup:
- `description__text` holds the posting body and `description__job-criteria-list` the criteria block (seniority, employment type, industries, function). "Similar jobs" and the footer sit outside both.
- The header holds the title (`top-card-layout__title`, the page's only `h1`), the company (`topcard__org-name-link`) and the location (the first `topcard__flavor--bullet`).

Today the fields title, company and location are filled from the stored text, which for LinkedIn begins with exactly that header. A cut text without the header would leave the field filler nothing to read, so the fields have to come from the markup (`Page.supplied`, as for JSON-LD).

The stored text has no separate raw field (schema version 2). The page chrome of linkedin.com is public, so a host rule in this repository is fine.

## Goals / Non-Goals

**Goals:**
- The stored text of a LinkedIn posting is body plus criteria, taken from the HTML structure rather than from text lines; its title, company and location come from the header markup.
- Postings already stored whole can be reduced to the same body without a new fetch, with an honest report of the ones that cannot.

**Non-Goals:**
- Other portals' chrome, the posting schema, any model call.

## Decisions

**Cut in the HTML parser, not on the finished text.** `_PageParser` already splits the page by tags; keeping only text inside the two containers needs no text markers ("Report this job", "Referrals increase…") that change with LinkedIn's wording or language. Alternative: cut text lines between marker lines. Rejected for new fetches because the markers are localized and brittle; it is used only for the repair of stored texts, where the HTML is gone.

**Header fields supplied from the markup.** For a LinkedIn page the parser returns title, company and location from the three header elements as `supplied`. Each is optional, as for JSON-LD: a missing element leaves that field to the existing field filler, which then sees only the cut text and may answer "unknown". The user can correct any field (existing behavior).

**Applied after the JSON-LD check, by host.** If a LinkedIn page ever carries a usable JSON-LD description, that wins as for any host. The containers apply only when JSON-LD yields nothing.

**A recognised description is stored whatever its length; only "no description found" falls back.** The fallback is for a missing or empty container (a layout change). A short but valid posting is stored as it is, so a short posting never regains the similar-job and sign-in text. "Recognised" means the container exists and holds text; the existing `MIN_PAGE_TEXT` check applies to the fallback text only, as for any page.

**Repair of stored postings is a one-off script that tells the truth about what it did.** The HTML is gone, so it cuts the stored text by the whole-page layout's line markers (from the line after "Report this job" to the line before "Referrals increase your chances"), and drops two fixed blocks some pages show right after the first marker: a 17-line sign-in block ("Use AI to assess how you fit") and the 4-line job poster block (a "Direct message the job poster" line, the poster's name twice, a headline). Both shapes were found by a dry run on real data; a poster block of another shape makes the text unchanged. A text that does not show the layout (for example an expired posting whose URL redirected to a search page) is left unchanged and listed in the report; the script defaults to a dry run and a second run finds nothing left to trim. Title, company and location of the stored postings are not touched. A one-off data repair may be a script (user-facing actions go through the web UI; this is not one). Alternative: a "re-read" button that fetches again. Rejected for now: it needs the network for every page and a UI for a single use.

**Scores and features are not recomputed by the repair.** They are redone on the user's request (or with the next "Neue Anzeigen bewerten"); the paid run is a decision for the user.

**No LLM eval.** No model is involved in the cut, so no eval applies. The change is covered by unit tests on a fictional LinkedIn-shaped fixture, and by the intake eval's LinkedIn case if the login-wall default changes.

## Risks / Trade-offs

- LinkedIn renames the container classes → no description is found and the page falls back to its visible text, so the posting stays usable; the real-URL check in the PR catches a rename at the time of the change.
- A renamed header element leaves a field to the field filler, which sees only the cut text → that field can be "unknown"; the user can correct it.
- The line-marker rule for stored text can misfire on an unusual layout → such texts are left unchanged and reported.
- The two rules (HTML containers for new fetches, line markers for stored text) can differ in what they keep → both keep the criteria block, and on the one real page checked both gave the same length (3472 characters). A pay-range box that LinkedIn shows outside the description stays in repaired texts but is not read for new fetches; adding it is a separate change.

## Open Questions

- `linkedin.com` leaving `DEFAULT_LOGIN_WALL_HOSTS` is a separate decision; it changes configuration and the intake eval's LinkedIn case, not this spec.
