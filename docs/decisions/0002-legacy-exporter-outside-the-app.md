# 0002. Legacy exporter outside the app

## Status

Accepted, 2026-10-05.

## Context

A user may arrive with an earlier job-search workflow whose postings, decisions and reasons live in a layout of their own. Those records are valuable as cold-start labels. Each such layout belongs to one user and is private. The app has to stay generic and publishable.

## Decision

An exporter lives in the user's legacy repository, outside this project. It reads the legacy layout and writes files in this app's data repository format (see [ADR 0001](0001-git-repository-as-user-data-store.md)). The dependency runs one way: the exporter depends on the app's schema, never the reverse. The app has no importer for any legacy format.

## Alternatives considered

- **An importer inside the app.** The brief rules it out ("no importer for anyone's legacy format") without weighing it further. It would put knowledge of one user's private layout into the public repository, and tie the app to formats it does not own.

## Consequences

- The app knows only its own schema. No trace of any user's legacy layout enters this repository.
- The schema becomes a contract that external code depends on, so it is versioned and changes only deliberately (see [ADR 0006](0006-pydantic-models-as-schema-source.md)).
- The schema must be able to express what an exporter supplies, including cold-start label kinds and the old process's keep-or-discard decision.
- Each user with legacy data writes and maintains their own exporter.
