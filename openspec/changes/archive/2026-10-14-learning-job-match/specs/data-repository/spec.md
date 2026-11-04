# Spec Delta

## Purpose

Defines the user data repository: a separate git repository in a documented, versioned format that holds every piece of user data and is the source of truth for all local stores.

## ADDED Requirements

### Requirement: Documented schema per entity
The system SHALL define one versioned JSON Schema per entity — profile, policy pack, posting, label — and publish the schemas in this repository as the public contract for external writers such as a legacy exporter.

#### Scenario: Schema carries a version
- **WHEN** a schema file is read
- **THEN** it declares a schema version that data files reference

#### Scenario: External writer targets the schema
- **WHEN** a file written by an external tool conforms to the published schema
- **THEN** the system loads it without any tool-specific import step

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
