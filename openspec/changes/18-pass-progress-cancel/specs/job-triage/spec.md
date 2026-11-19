# Spec Delta

## MODIFIED Requirements

### Requirement: Fixed triage order
A scoring pass SHALL process each posting in this order: hard exclusions and the content guard, then scoring. A posting excluded in the first step SHALL NOT be scored. A pass SHALL make one model call per posting it scores and SHALL NOT extract features.

#### Scenario: Excluded posting
- **WHEN** a posting matches a hard exclusion rule
- **THEN** it is marked excluded with the matching rule's identifier
- **AND** no scoring call is made for it

#### Scenario: Posting flagged by the content guard
- **WHEN** a posting is flagged by the content guard and the user has not released it
- **THEN** it is marked excluded with the reason "content guard" and the flagged categories
- **AND** no scoring call is made for it

#### Scenario: Released posting
- **WHEN** the user releases a flagged posting
- **THEN** the next pass scores it like any other posting

#### Scenario: Unscreened posting with screening on
- **WHEN** a pass contains a posting the content guard never checked and a screening classifier is configured
- **THEN** the pass screens it before any scoring call and records the result in the posting
- **AND** a flagged result excludes it like any other flagged posting

#### Scenario: Unscreened posting with screening off
- **WHEN** a pass contains a posting the content guard never checked and no screening classifier is configured
- **THEN** the pass pauses before any scoring call, names those postings and asks the user whether to continue with them or abort the pass

#### Scenario: Continue not remembered
- **WHEN** the user continued a pass with an unscreened posting and screening is still off in a later pass
- **THEN** the later pass asks again

#### Scenario: Run aborted over unscreened postings
- **WHEN** the user answers that question with abort
- **THEN** the pass ends without any scoring call, and the postings stay unscored

#### Scenario: One call per scored posting
- **WHEN** a pass scores 80 postings
- **THEN** it makes 80 judge calls and no extraction call

### Requirement: Configurable feature extraction
The system SHALL be able to extract structured features from a posting, for the agent's tool and the evals; a scoring pass does not extract. The feature set SHALL be configurable per user and SHALL by default cover role type, seniority, domain, tech stack, location, remote option and company stage. When the posting's company has a stored record with facts, the extraction SHALL receive them as a block separate from the posting, labelled as the result of a lookup (a record the user entered by hand is labelled as entered by hand), and the instructions SHALL say that the facts come from a lookup or an entry by hand and the text from the posting. Only the typed values of the record (size class and founding year) SHALL reach the model, never text taken from the company's page.

#### Scenario: Default features
- **WHEN** a posting is extracted with the default feature set
- **THEN** the result contains a value or an explicit "unknown" for each default feature

#### Scenario: User-defined feature
- **WHEN** the user's configuration adds a feature
- **THEN** extraction results include that feature

#### Scenario: Facts available
- **WHEN** a posting's company has a record with a size class and a founding year
- **THEN** the extraction call carries both in a data block of their own, apart from the posting block

#### Scenario: No facts
- **WHEN** the company has no record, or a record without facts
- **THEN** the extraction call carries no facts block and behaves as before
