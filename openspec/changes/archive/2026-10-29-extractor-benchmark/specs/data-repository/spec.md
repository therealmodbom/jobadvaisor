# Spec Delta

## ADDED Requirements

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
