# data-repository Specification

## Purpose
Defines the user data repository: a separate git repository in a documented, versioned format that holds every piece of user data and is the source of truth for all local stores.

## Requirements

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

### Requirement: Location from configuration
The system SHALL read the data repository location from configuration and SHALL NOT assume a fixed path.

#### Scenario: Configured location
- **WHEN** the configured location points to a valid data repository
- **THEN** the system loads profile, policy pack, postings and labels from it

#### Scenario: Missing location
- **WHEN** no location is configured or the path does not exist
- **THEN** the system refuses to start a triage run and reports which setting is missing

### Requirement: Validation on load
The system SHALL validate every data file against its schema on load and SHALL reject invalid files with an error naming the file and the violated constraint.

#### Scenario: Invalid file
- **WHEN** a posting file lacks a required field
- **THEN** loading fails with an error naming that file and field
- **AND** no partial data from that file is used

#### Scenario: Unsupported schema version
- **WHEN** a file references a schema version the system does not support
- **THEN** loading fails with an error naming the file, its version and the supported versions

### Requirement: Labels written back
The system SHALL write each new label to the data repository in the label schema, so labels survive a rebuild of every local store.

#### Scenario: Label persisted
- **WHEN** the user rates a posting
- **THEN** a schema-valid label file for that posting exists in the data repository

#### Scenario: Local stores rebuilt
- **WHEN** the local checkpoint and vector stores are deleted and the system starts again
- **THEN** retrieval and scoring use the same labels as before the deletion

### Requirement: Demo persona fixture
This repository SHALL contain a fictional demo persona data repository in the same schema, and tests, CI and demos SHALL use only that fixture.

#### Scenario: Fixture validates
- **WHEN** the demo persona fixture is loaded
- **THEN** every file passes schema validation

#### Scenario: Demo run
- **WHEN** the data repository location points to the demo persona fixture
- **THEN** a complete triage and rating cycle runs without any other user data

### Requirement: Scores and pool settings written back
The system SHALL write each posting's latest score, reasoning and scoring time, each pass's quality measure and the pool settings (hint threshold and rate) to the data repository in their schemas, so they survive a rebuild of every local store.

#### Scenario: Score persisted
- **WHEN** a pass scores a posting
- **THEN** a schema-valid score file for that posting exists in the data repository

#### Scenario: Local stores rebuilt
- **WHEN** the local checkpoint and vector stores are deleted and the system starts again
- **THEN** the pool shows the same scores, statuses and settings as before the deletion

### Requirement: Extraction labels
The data repository MAY hold an extraction-labels file with hand-settled feature values per posting ID and feature ID, and an optional minimum accuracy between 0 and 1 for the extractor. The file SHALL have a published schema and a schema version, SHALL be validated on load, and SHALL be absent without error. A label SHALL name a posting that exists and a feature of the feature set.

#### Scenario: File absent
- **WHEN** the file does not exist
- **THEN** the repository loads as before and the benchmark reports no accuracy

#### Scenario: Valid file
- **WHEN** the file conforms to its schema
- **THEN** the repository loads and the benchmark reads the labels and the minimum accuracy from it

#### Scenario: Label for a missing posting
- **WHEN** a label names a posting ID without a posting file
- **THEN** loading fails with an error naming the file and the posting ID

#### Scenario: Label for an unknown feature
- **WHEN** a label names a feature that is not in the feature set
- **THEN** loading fails with an error naming the file, the posting ID and the feature

#### Scenario: Minimum accuracy out of range
- **WHEN** the minimum accuracy lies outside 0 to 1
- **THEN** loading fails with an error naming the file and the value

### Requirement: Company records
The data repository MAY hold one company record per company, with a published schema and a schema version, validated on load. A record SHALL hold the company's name as the postings carry it, the source of its facts (LinkedIn, the employer's website or an entry by hand) and the fetch or entry date, and MAY hold a size class and a founding year. A repository without company records SHALL load as before.

#### Scenario: Records absent
- **WHEN** the repository has no company records
- **THEN** it loads, and extraction runs without company facts

#### Scenario: Valid record
- **WHEN** a record conforms to its schema
- **THEN** the repository loads and extraction for a posting of that company receives its facts

#### Scenario: Invalid record
- **WHEN** a record holds a founding year that is not a four-digit year, or a size class that is not a number range
- **THEN** loading fails with an error naming the file and the violated constraint
