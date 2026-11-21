# Spec Delta

## ADDED Requirements

### Requirement: A deleted posting is no duplicate
After a posting is deleted, its links and its text SHALL no longer count as stored. Submitting the same link again SHALL store a fresh posting.

#### Scenario: Same link after a delete
- **WHEN** the user deletes a posting and then submits its link again
- **THEN** a new posting is stored, unrated and without a score, and no duplicate is reported
