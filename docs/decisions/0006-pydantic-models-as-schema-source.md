# 0006. Pydantic models as the single source of the data repository's JSON Schemas

## Status

Accepted, 2026-10-06.

## Context

The data repository format is a public contract: the app validates every file against it, and external exporters write to it (see [ADR 0001](0001-git-repository-as-user-data-store.md) and [ADR 0002](0002-legacy-exporter-outside-the-app.md)). It has to exist as one JSON Schema per entity. The app also needs typed models for the same entities in code. This decision was made while planning the first change; the kickoff brief does not list it.

## Decision

Entities (profile, policy pack, posting, label) are Pydantic models, each with a `schema_version`. A script generates `schemas/*.schema.json` (JSON Schema 2020-12) from them, and the generated files are committed. A CI check fails when the committed files differ from freshly generated ones. The loader accepts only the versions in a supported list.

## Alternatives considered

No alternative was weighed explicitly. This decision implies rejecting the obvious one:

- **Hand-written JSON Schemas as the source**, with models written or generated separately. Two hand-maintained definitions of the same entity drift apart, and validation and documentation would no longer agree with the code.

## Consequences

- One definition per entity: the code, the validation and the published schema always agree.
- Exporters consume the committed schema files without running the app.
- The schemas' exact shape follows Pydantic's generator output, not hand-tuned JSON Schema.
- Every model change requires regenerating the schemas, and an incompatible change requires a version bump and an updated supported-version list.
