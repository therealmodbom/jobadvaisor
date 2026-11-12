# 0001. Git repository as the user data store

## Status

Accepted, 2026-10-05. Partly superseded by [ADR 0010](0010-the-app-commits-and-pushes-the-data-repository.md): the app no longer only writes files, it commits and pushes them on a button press. The rest stands.

## Context

JobAdvAIsor's code repository is meant to become public, so no user data may live in it. The app has a single user on localhost. That user's profile, rules, postings and ratings are small (tens to a few hundred records), change over time, and are worth keeping with history and a backup. External tools, such as an exporter from an older workflow, must be able to write the data without running the app.

## Decision

Each user keeps their data in a separate, private, plain git repository, with a remote optional. The app reads its location from configuration (`DATA_REPOSITORY`). Every entity is a JSON file in a documented format with one JSON Schema per entity, and the app validates each file on load. The app writes files and never commits; the user commits. Every local store (checkpoints, vector index) is derived from this repository and can be rebuilt from it.

## Alternatives considered

No alternative was weighed explicitly. This decision implies rejecting the obvious one:

- **A database as the primary store** (SQLite or Postgres). It would give transactions and queries, but the data would be neither diffable nor human-readable, history and backup would need extra tooling, and an external tool could no longer write plain files.

## Consequences

- The code repository holds no user data, so it can be published once the separation is verified.
- History, diff and backup come from git. Users can read and edit their data by hand.
- The file format is a public contract and changes only deliberately (see [ADR 0006](0006-pydantic-models-as-schema-source.md)).
- Every load validates every file, and local stores must be rebuilt or updated when files change.
- There are no transactions and no concurrent writers. That fits a single local user only.
- Users commit their own changes. An uncommitted rating is still on disk, but has no history yet.
