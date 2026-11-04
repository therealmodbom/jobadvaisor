# Spec Delta

## MODIFIED Requirements

### Requirement: Documented schema per entity
The system SHALL define one versioned JSON Schema per entity — profile, policy pack, posting, label, score, pool (settings and pass history) — and publish the schemas in this repository as the public contract for external writers such as a legacy exporter. A posting MAY carry an application status and an origin mark; a score belongs to a posting by its ID. The policy pack MAY hold the user's import mapping for job lists (status column, status values per application status and skip, assessment column), so the layout of the user's own list lives in the data repository and not in this repository.

#### Scenario: Schema carries a version
- **WHEN** a schema file is read
- **THEN** it declares a schema version that data files reference

#### Scenario: External writer targets the schema
- **WHEN** a file written by an external tool conforms to the published schema
- **THEN** the system loads it without any tool-specific import step

#### Scenario: Earlier version loads
- **WHEN** a posting file references the schema version before this change
- **THEN** it loads, with the status open and no origin mark

## ADDED Requirements

### Requirement: Scores and pool settings written back
The system SHALL write each posting's latest score, reasoning and scoring time, each pass's quality measure and the pool settings (hint threshold and rate) to the data repository in their schemas, so they survive a rebuild of every local store.

#### Scenario: Score persisted
- **WHEN** a pass scores a posting
- **THEN** a schema-valid score file for that posting exists in the data repository

#### Scenario: Local stores rebuilt
- **WHEN** the local checkpoint and vector stores are deleted and the system starts again
- **THEN** the pool shows the same scores, statuses and settings as before the deletion
