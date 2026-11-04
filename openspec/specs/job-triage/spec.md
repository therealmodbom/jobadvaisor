# job-triage Specification

## Purpose
Scores a batch of postings against the user's profile, policy pack and past ratings, and returns a ranked list that also includes deliberately low-scored postings for exploration.

## Requirements

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

### Requirement: Deterministic hard exclusions
Hard exclusions SHALL be evaluated deterministically from rules in the user's policy pack. The same posting and policy pack SHALL always produce the same exclusion result, without a model call.

#### Scenario: Repeatable result
- **WHEN** the same posting is checked twice against the same policy pack
- **THEN** both results are identical

#### Scenario: Rules come from the data repository
- **WHEN** the policy pack in the data repository changes
- **THEN** the next run applies the changed rules without a code change

### Requirement: Configurable feature extraction
The system SHALL extract structured features from each posting. The feature set SHALL be configurable per user and SHALL by default cover role type, seniority, domain, tech stack, location, remote option and company stage. When the posting's company has a stored record with facts, the extraction SHALL receive them as a block separate from the posting, labelled as the result of a lookup (a record the user entered by hand is labelled as entered by hand), and the instructions SHALL say that the facts come from a lookup or an entry by hand and the text from the posting. Only the typed values of the record (size class and founding year) SHALL reach the model, never text taken from the company's page.

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

### Requirement: Rated examples carry the strength
Each rated posting shown to the judge as an example SHALL state the strength of its rating next to the verdict when the label has one. An example whose label has no strength SHALL read as before.

#### Scenario: Example with strength
- **WHEN** the judge is shown a posting rated "nein, auf keinen Fall"
- **THEN** its example states the negative verdict and the strength strong, with the user's reasons

#### Scenario: Example without strength
- **WHEN** the judge is shown a posting whose label has a verdict and no strength
- **THEN** its example states the verdict only
