# Spec Delta

## ADDED Requirements

### Requirement: Company records
The data repository MAY hold one company record per company, with a published schema and a schema version, validated on load. A record SHALL hold the company's name as the postings carry it, the source of its facts and the fetch date, and MAY hold a size class and a founding year. A repository without company records SHALL load as before.

#### Scenario: Records absent
- **WHEN** the repository has no company records
- **THEN** it loads, and extraction runs without company facts

#### Scenario: Valid record
- **WHEN** a record conforms to its schema
- **THEN** the repository loads and extraction for a posting of that company receives its facts

#### Scenario: Invalid record
- **WHEN** a record holds a founding year that is not a four-digit year, or a size class that is not a number range
- **THEN** loading fails with an error naming the file and the violated constraint
