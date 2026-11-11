# Spec Delta

## MODIFIED Requirements

### Requirement: Scoring with rated examples
The system SHALL score each non-excluded posting with a numeric score and a written reasoning, using the most similar already-rated postings, including the user's reasons, as examples. Scoring SHALL also work when no rated postings exist yet. The latest score, its reasoning and its time SHALL be stored with the posting, outlive the pass, and be replaced by a later pass or by a score the user requests for that posting.

#### Scenario: Examples used
- **WHEN** rated postings exist
- **THEN** the reasoning for a score references the rated postings it was compared with

#### Scenario: Cold start
- **WHEN** no rated postings exist
- **THEN** every non-excluded posting still receives a score and reasoning

#### Scenario: Score outlives the pass
- **WHEN** a pass has finished and the application restarted
- **THEN** each scored posting still carries its latest score and reasoning

#### Scenario: Later pass replaces the score
- **WHEN** a posting is scored again in a later pass
- **THEN** the stored score, reasoning and time are the later ones

#### Scenario: Requested score replaces the score
- **WHEN** the user requests a score for a posting that already has one
- **THEN** the stored score, reasoning and time are the new ones
