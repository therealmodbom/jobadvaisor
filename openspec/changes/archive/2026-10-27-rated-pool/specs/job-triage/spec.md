# Spec Delta

## MODIFIED Requirements

### Requirement: Fixed triage order
A scoring pass SHALL process each posting in this order: hard exclusions, feature extraction, scoring. A posting excluded in the first step SHALL NOT be scored.

#### Scenario: Excluded posting
- **WHEN** a posting matches a hard exclusion rule
- **THEN** it is marked excluded with the matching rule's identifier
- **AND** no scoring call is made for it

#### Scenario: Posting flagged by the content guard
- **WHEN** a posting is flagged by the content guard and the user has not released it
- **THEN** it is marked excluded with the reason "content guard" and the flagged categories
- **AND** no extraction or scoring call is made for it

#### Scenario: Released posting
- **WHEN** the user releases a flagged posting
- **THEN** the next pass extracts and scores it like any other posting

#### Scenario: Unscreened posting with screening on
- **WHEN** a pass contains a posting the content guard never checked and a screening classifier is configured
- **THEN** the pass screens it before any extraction call and records the result in the posting
- **AND** a flagged result excludes it like any other flagged posting

#### Scenario: Unscreened posting with screening off
- **WHEN** a pass contains a posting the content guard never checked and no screening classifier is configured
- **THEN** the pass pauses before any extraction call, names those postings and asks the user whether to continue with them or abort the pass

#### Scenario: Continue not remembered
- **WHEN** the user continued a pass with an unscreened posting and screening is still off in a later pass
- **THEN** the later pass asks again

#### Scenario: Run aborted over unscreened postings
- **WHEN** the user answers that question with abort
- **THEN** the pass ends without any extraction or scoring call, and the postings stay unscored

### Requirement: Scoring with rated examples
The system SHALL score each non-excluded posting with a numeric score and a written reasoning, using the most similar already-rated postings, including the user's reasons, as examples. Scoring SHALL also work when no rated postings exist yet. The latest score, its reasoning and its time SHALL be stored with the posting, outlive the pass, and be replaced by a later pass.

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

### Requirement: Every posting in the result
A pass SHALL record every posting it processed, with its score or its exclusion, low-scored and excluded ones included. The user MAY rate any posting in the pool.

#### Scenario: Low score kept
- **WHEN** a posting receives the lowest score in a pass
- **THEN** it is still stored with its score and reasoning

## REMOVED Requirements

### Requirement: Exploration slot
**Reason**: The pass no longer presents a list for rating; the pool is the list. The same idea returns as the exploration mark in the pool.
**Migration**: See "Exploration mark" in `posting-pool`.
