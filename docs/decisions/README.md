# Architecture Decision Records

One file per significant decision: `NNNN-<kebab-title>.md`, numbered in order, never renumbered.

Each ADR has the sections Status, Context, Decision, Alternatives considered, Consequences. A superseded ADR stays and links its successor.

## Index

| # | Title | Status |
|---|---|---|
| 0001 | [Git repository as the user data store](0001-git-repository-as-user-data-store.md) | Accepted, "the app never commits" superseded by 0010 |
| 0002 | [Legacy exporter outside the app](0002-legacy-exporter-outside-the-app.md) | Accepted |
| 0003 | [Provider-agnostic LLM access through LangChain](0003-provider-agnostic-llm-access-through-langchain.md) | Accepted |
| 0004 | [SQLite and Chroma locally, Postgres as the later adapter](0004-sqlite-and-chroma-locally-postgres-later.md) | Accepted |
| 0005 | [Hybrid agent design: fixed triage graph plus a free agent over the same tools](0005-hybrid-agent-design.md) | Accepted |
| 0006 | [Pydantic models as the single source of the data repository's JSON Schemas](0006-pydantic-models-as-schema-source.md) | Accepted |
| 0007 | [Layout-free list import with a stored mapping](0007-layout-free-list-import-with-a-stored-mapping.md) | Accepted |
| 0008 | [Rating strength as a second label field, not a wider verdict](0008-rating-strength-as-a-second-label-field.md) | Accepted |
| 0009 | [A release image from GHCR, published to the private network from the loopback port](0009-container-from-ghcr-behind-tailscale-serve.md) | Accepted, hand commit and push superseded by 0010 |
| 0010 | [The app commits and pushes the data repository](0010-the-app-commits-and-pushes-the-data-repository.md) | Accepted |
