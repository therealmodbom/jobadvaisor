# Spec Delta

## ADDED Requirements

### Requirement: Delete a posting
The user SHALL be able to delete a stored posting permanently. A delete SHALL remove the posting, its rating, its score and its hand-settled feature values from the data repository, with no trash step. Deleting a posting that does not exist SHALL answer „not found“ and change nothing.

#### Scenario: Delete a rated posting
- **WHEN** the user deletes a posting that has a rating and a score
- **THEN** the posting, its rating and its score are gone from the data repository

#### Scenario: Delete twice
- **WHEN** the user deletes a posting and a second delete of the same posting arrives
- **THEN** the second answers „not found“ and nothing else changes

### Requirement: A deleted posting is gone everywhere
After a delete the posting SHALL appear nowhere in the pool, a filter, the ranking, a scoring pass, an availability check, the agent's results or the scoring examples. Its rating SHALL no longer count for the correction counter.

#### Scenario: Gone from the pool and the counter
- **WHEN** the user deletes a rated posting
- **THEN** the pool no longer lists it, and the correction counter no longer counts its rating

#### Scenario: No longer a scoring example
- **WHEN** a rated posting is deleted and a pass scores another posting afterwards
- **THEN** the judge is not shown the deleted posting as an example

### Requirement: No delete while scoring or a check runs
The system SHALL refuse a delete while a scoring pass computes, a single posting is scored, or an availability check runs. The refusal SHALL name which of these is running and SHALL change nothing.

#### Scenario: Delete during a pass
- **WHEN** a delete arrives while a pass scores
- **THEN** it is refused as „scoring in progress“ and the posting stays

#### Scenario: Delete during a check
- **WHEN** a delete arrives while an availability check runs
- **THEN** it is refused as „check in progress“ and the posting stays

### Requirement: A paused pass skips a deleted posting
A pass paused over its question about unscreened postings SHALL, once resumed, skip each posting deleted while it waited. That posting SHALL get no score, no model call and no failure, and it SHALL leave the pass's total.

#### Scenario: Deleted while the pass waits
- **WHEN** a pass waits for the answer about unscreened postings, one posting of its batch is deleted, and the user continues
- **THEN** the pass scores the other postings, stores no score for the deleted one and reports no failure for it

### Requirement: Scores keep naming a deleted example
A delete SHALL NOT change the scores of other postings. A score that names a deleted posting among the examples the judge was shown SHALL keep that name as a record of the past score. A posting's page SHALL list only examples that still exist.

#### Scenario: Example deleted
- **WHEN** a posting's score names posting B as an example and B is deleted
- **THEN** the stored score still names B, and the posting's page no longer lists B among the compared postings
