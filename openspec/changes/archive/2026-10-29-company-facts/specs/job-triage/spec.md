# Spec Delta

## MODIFIED Requirements

### Requirement: Configurable feature extraction
The system SHALL extract structured features from each posting. The feature set SHALL be configurable per user and SHALL by default cover role type, seniority, domain, tech stack, location, remote option and company stage. When the posting's company has a stored record with facts, the extraction SHALL receive them as a block separate from the posting, labelled as the result of a lookup, and the instructions SHALL say that the facts come from a lookup and the text from the posting. Only the typed values of the record (size class and founding year) SHALL reach the model, never text taken from the company's page.

#### Scenario: Default features
- **WHEN** a posting is processed with the default feature set
- **THEN** the stored result contains a value or an explicit "unknown" for each default feature

#### Scenario: User-defined feature
- **WHEN** the user's configuration adds a feature
- **THEN** extraction results include that feature

#### Scenario: Facts available
- **WHEN** a posting's company has a record with a size class and a founding year
- **THEN** the extraction call carries both in a data block of their own, apart from the posting block

#### Scenario: No facts
- **WHEN** the company has no record, or a record without facts
- **THEN** the extraction call carries no facts block and behaves as before
