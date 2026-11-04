# Spec Delta

## Purpose

Scores a batch of postings against the user's profile, policy pack and past ratings, and returns a ranked list that also includes deliberately low-scored postings for exploration.

## ADDED Requirements

### Requirement: Fixed triage order
A triage run SHALL process each posting in this order: hard exclusions, feature extraction, scoring. A posting excluded in the first step SHALL NOT be scored.

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
- **THEN** the next run extracts and scores it like any other posting

#### Scenario: Unscreened posting with screening on
- **WHEN** a run's batch contains a posting the content guard never checked and a screening classifier is configured
- **THEN** the run screens it before any extraction call and records the result in the posting
- **AND** a flagged result excludes it like any other flagged posting

#### Scenario: Unscreened posting with screening off
- **WHEN** a run's batch contains a posting the content guard never checked and no screening classifier is configured
- **THEN** the run pauses before any extraction call, names those postings and asks the user whether to continue with them or abort the run

#### Scenario: Continue not remembered
- **WHEN** the user continued a run with an unscreened posting and screening is still off in a later run
- **THEN** the later run asks again

#### Scenario: Run aborted over unscreened postings
- **WHEN** the user answers that question with abort
- **THEN** the run ends without any extraction or scoring call

### Requirement: Deterministic hard exclusions
Hard exclusions SHALL be evaluated deterministically from rules in the user's policy pack. The same posting and policy pack SHALL always produce the same exclusion result, without a model call.

#### Scenario: Repeatable result
- **WHEN** the same posting is checked twice against the same policy pack
- **THEN** both results are identical

#### Scenario: Rules come from the data repository
- **WHEN** the policy pack in the data repository changes
- **THEN** the next run applies the changed rules without a code change

### Requirement: Configurable feature extraction
The system SHALL extract structured features from each posting. The feature set SHALL be configurable per user and SHALL by default cover role type, seniority, domain, tech stack, location, remote option and company stage.

#### Scenario: Default features
- **WHEN** a posting is processed with the default feature set
- **THEN** the stored result contains a value or an explicit "unknown" for each default feature

#### Scenario: User-defined feature
- **WHEN** the user's configuration adds a feature
- **THEN** extraction results include that feature

### Requirement: Scoring with rated examples
The system SHALL score each non-excluded posting with a numeric score and a written reasoning, using the most similar already-rated postings, including the user's reasons, as examples. Scoring SHALL also work when no rated postings exist yet.

#### Scenario: Examples used
- **WHEN** rated postings exist
- **THEN** the reasoning for a score references the rated postings it was compared with

#### Scenario: Cold start
- **WHEN** no rated postings exist
- **THEN** every non-excluded posting still receives a score and reasoning

### Requirement: Every posting in the result
A triage run's result SHALL record every posting of the batch, with its score or its exclusion, low-scored and excluded ones included. The user MAY rate any posting in the result. The postings presented for rating are the selection described in Exploration slot.

#### Scenario: Low score kept
- **WHEN** a posting receives the lowest score in the batch
- **THEN** it still appears in the run result with its score and reasoning

### Requirement: Exploration slot
About 20 % of the postings presented for rating in each run SHALL be low-scored postings chosen for exploration, marked as such, so the system does not only confirm its own ranking. The presented list SHALL contain each posting at most once. Slots the exploration share cannot fill SHALL go to the next highest-scored postings. When fewer scored postings exist than the list size, all of them SHALL be presented.

#### Scenario: Exploration share
- **WHEN** a run presents 10 postings for rating and enough low-scored postings exist
- **THEN** 2 of them are marked as exploration picks

#### Scenario: Too few low-scored postings
- **WHEN** fewer low-scored postings exist than the exploration share asks for
- **THEN** all available ones are used, the remaining slots hold the next highest-scored postings, and the run does not fail

#### Scenario: No duplicates in a small batch
- **WHEN** the batch holds fewer scored postings than the list size
- **THEN** every scored posting is presented exactly once
