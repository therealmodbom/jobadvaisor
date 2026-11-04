# 0004. SQLite and Chroma locally, Postgres as the later adapter

## Status

Accepted, 2026-10-05.

## Context

The triage graph pauses for ratings and resumes later, so it needs persisted LangGraph checkpoints. Scoring retrieves similar, already rated postings, so it needs a vector index. The data repository is the source of truth (see [ADR 0001](0001-git-repository-as-user-data-store.md)), so both stores hold derived state only. The app runs for one user on one machine, and setup should need nothing beyond the language toolchains.

## Decision

Checkpoints use LangGraph's `SqliteSaver`, created behind a factory. The vector index is Chroma, persisted in a local directory. Both are rebuildable and are rebuilt when missing. A later change adds Postgres as a second adapter for both stores behind the same interfaces, switched by connection URL: LangGraph's Postgres checkpointer for checkpoints, and pgvector for the vector index.

## Alternatives considered

- **Postgres from day one**, local in Docker or an external database. The brief rejects it for this change in favor of a low entry barrier with no Docker needed. It stays the planned second adapter.

## Consequences

- Setup is `uv` and `npm` only. Deleting the vector index loses nothing: it is rebuilt from the data repository. Deleting the checkpoints loses no data either, but abandons any run paused for ratings.
- Store access must stay behind narrow interfaces, so that the Postgres adapter replaces implementations, not callers.
- Two adapters will exist eventually, and Chroma and pgvector can differ in retrieval behavior. Any switch needs the retrieval evals rerun.
- SQLite and a local Chroma directory support one process and one user. That matches the scope, not a hosted multi-user setup.
