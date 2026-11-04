# Spec Delta

## Purpose

Collects the user's ratings of triaged postings, with reasons, and turns them into labels that shape every later triage run.

## ADDED Requirements

### Requirement: Paused run awaiting ratings
A triage run SHALL pause after scoring and wait for the user's ratings. The paused run SHALL survive a restart of the application and resume where it stopped.

#### Scenario: Restart while paused
- **WHEN** the application restarts while a run awaits ratings
- **THEN** the same run with the same postings and scores is still awaiting ratings

#### Scenario: Resume
- **WHEN** the user submits the ratings for a paused run
- **THEN** the run resumes and completes

#### Scenario: Paused run lost
- **WHEN** the stored state of a paused run is lost before all its presented postings were rated
- **THEN** the next run offers the unrated ones for rating again

### Requirement: Rating with reasons
Each rating SHALL record a verdict of positive or negative, optional reason chips and optional free text. Reason chips SHALL come from a configurable list in the data repository. A chip MAY name the verdict it explains; such a chip SHALL be accepted only with that verdict.

#### Scenario: Rating with a chip
- **WHEN** the user rates a posting negative with the chip "too junior"
- **THEN** the stored label holds the negative verdict and that chip

#### Scenario: Chip of the other verdict
- **WHEN** a rating is positive and names a chip configured for negative verdicts
- **THEN** the rating is rejected with an error naming the chip

#### Scenario: Unknown chip
- **WHEN** a rating names a chip that is not in the configured list
- **THEN** the rating is rejected with an error naming the chip

### Requirement: Partial batch
The user SHALL be able to rate part of a batch and continue later. Unrated postings SHALL remain awaiting rating.

#### Scenario: Partial submission
- **WHEN** the user rates 3 of 10 postings
- **THEN** 3 labels are stored and 7 postings still await rating

### Requirement: Labels feed the next run
Labels SHALL be available as rated examples to the next triage run, without a manual rebuild.

#### Scenario: New label used
- **WHEN** the user rates a posting and then starts a new run with a similar posting
- **THEN** the new posting's reasoning can reference the newly rated posting

### Requirement: Cold-start labels
The system SHALL accept labels supplied in the label schema by an external exporter, and SHALL treat them by their recorded kind: confirmed interest as positive, rejection with reason as negative, records marked as not reflecting preference as excluded from training and retrieval, and unrated records as unlabeled.

#### Scenario: Excluded record never positive
- **WHEN** an imported label is marked as not reflecting preference
- **THEN** it is never used as a positive example and never counted in evals

#### Scenario: Unlabeled record offered for rating
- **WHEN** an imported posting has no label
- **THEN** it is offered for rating once through the feedback list
