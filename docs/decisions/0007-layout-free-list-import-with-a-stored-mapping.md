# 0007. Layout-free list import with a stored mapping

## Status

Accepted, 2026-10-21.

## Context

Users keep their job lists in their own Markdown layouts: their own headings, columns, status words and assessment scales. The app should take such a list in and show the entries in the pool. The code repository is meant to become public, so it must hold no single user's layout; a column name or status vocabulary derived from one real list is an indirect trace of that user (see "Privacy" in `AGENTS.md`).

## Decision

The importer knows no layout. It finds entry tables by their link column, the column holding the most http(s) URLs. The user confirms an `ImportMapping` in the web UI: the status column, the assessment column, and what each status value means (`open`, `applied`, `done` or `skip`). The mapping is stored in the policy pack, like `login_wall_hosts`, so the next import starts from it. An import is a preview of the tables and columns, then a confirmed start.

## Alternatives considered

- **A hardcoded layout of one list.** It is the shortest path, but it puts one user's layout into the public code and breaks for every other list.
- **A fixed generic format, with lists converted outside the app.** It keeps the app simple, but it needs a conversion script or a manual rewrite, and the app is meant to become a pure web tool with no scripts for users.
- **A plugin mechanism for formats.** It would serve every layout, but it is a mechanism with an interface to design and maintain for one user, and it still needs code for each list.

## Consequences

- The policy pack's schema gains `import_mapping`.
- The report lists every entry that was not imported, with its row text, link and reason, because the user needs to know which entries to follow up.
- A similar-text duplicate also receives the origin mark of an entry that may be another posting, since intake treats it as a duplicate. An entry never replaces a mark a posting already has unless the entry's listed link is one of that posting's URLs, so a posting reached through another link keeps its mark.
- The end-to-end tests run Python pytest with Playwright (sync API) against the real app with fake models, rather than `@playwright/test`.
