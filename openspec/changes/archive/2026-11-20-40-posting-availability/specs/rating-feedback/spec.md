# Spec Delta

## MODIFIED Requirements

### Requirement: Cold-start labels
The system SHALL accept labels supplied in the label schema by an external exporter, and SHALL treat them by their recorded kind: confirmed interest as positive, rejection with reason as negative, records marked as not reflecting preference as excluded from training and retrieval, and unrated records as unlabeled. Postings imported from a job list carry no label from the import.

#### Scenario: Excluded record never positive
- **WHEN** an imported label is marked as not reflecting preference
- **THEN** it is never used as a positive example and never counted in evals

#### Scenario: Unlabeled record offered for rating
- **WHEN** an imported posting has no label and is not closed
- **THEN** it appears under the pool filter "noch nicht bewertet"

#### Scenario: Unlabeled closed record offered for rating
- **WHEN** an imported posting has no label and is closed
- **THEN** it appears under the pool filter "geschlossen", where the user can rate it
