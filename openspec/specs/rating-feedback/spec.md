# rating-feedback Specification

## Purpose
Collects the user's ratings of triaged postings, with reasons, and turns them into labels that shape every later triage run.

## Requirements

### Requirement: Rating with reasons
Each rating SHALL record a verdict of positive or negative, optional reason chips and optional free text. Reason chips SHALL come from a configurable list in the data repository. A chip MAY name a polarity (positive or negative). Chips of both polarities MAY appear on one rating. A rating given without a verdict SHALL take the verdict of its first chip that names a polarity; a rating that names a verdict keeps it whatever its chips say. A rating without a verdict and without a chip that names a polarity SHALL be rejected.

#### Scenario: Rating with a chip
- **WHEN** the user rates a posting negative with the chip "too junior"
- **THEN** the stored label holds the negative verdict and that chip

#### Scenario: Mixed chips
- **WHEN** the user rates a posting positive with a positive chip and a negative chip
- **THEN** the stored label holds the positive verdict and both chips

#### Scenario: Verdict from a chip
- **WHEN** a rating names no verdict and the chip "too junior" of negative polarity
- **THEN** the stored label holds the negative verdict

#### Scenario: No verdict to derive
- **WHEN** a rating names neither a verdict nor a chip that carries a polarity
- **THEN** the rating is rejected with an error saying a verdict is missing

#### Scenario: Chip of the other verdict
- **WHEN** a rating is positive and names a chip configured for negative verdicts
- **THEN** the rating is stored with both the verdict and the chip

#### Scenario: Unknown chip
- **WHEN** a rating names a chip that is not in the configured list
- **THEN** the rating is rejected with an error naming the chip

### Requirement: Labels feed the next pass
Labels SHALL be available as rated examples to the next scoring pass, without a manual rebuild.

#### Scenario: New label used
- **WHEN** the user rates a posting and then starts a pass that scores a similar posting
- **THEN** the similar posting's reasoning can reference the newly rated posting

### Requirement: Cold-start labels
The system SHALL accept labels supplied in the label schema by an external exporter, and SHALL treat them by their recorded kind: confirmed interest as positive, rejection with reason as negative, records marked as not reflecting preference as excluded from training and retrieval, and unrated records as unlabeled. Postings imported from a job list carry no label from the import.

#### Scenario: Excluded record never positive
- **WHEN** an imported label is marked as not reflecting preference
- **THEN** it is never used as a positive example and never counted in evals

#### Scenario: Unlabeled record offered for rating
- **WHEN** an imported posting has no label
- **THEN** it appears under the pool filter "noch nicht bewertet"

### Requirement: Strength of a rating
A rating that carries a verdict MAY also carry a strength, `weak` or `strong`. Verdict and strength together give four levels: positive strong ("ja, auf jeden Fall"), positive weak ("ja, vielleicht"), negative weak ("nein, eher nicht") and negative strong ("nein, auf keinen Fall"). A rating without a strength SHALL be a plain yes or no, and a stored label without a strength SHALL stay valid and be treated exactly as before. A strength without a verdict SHALL be rejected, including on a rating whose verdict would only be derived from a chip, and a label of kind `imported_not_preference` SHALL carry none. A strength SHALL NOT change the direction: counting, chip rules and evals use the verdict alone.

#### Scenario: Rating at each level
- **WHEN** the user rates a posting positive with strength weak, and later another negative with strength strong
- **THEN** the stored labels hold those verdicts with those strengths, and the rating read back shows them

#### Scenario: Label without strength
- **WHEN** a stored label has a verdict and no strength
- **THEN** it loads, is shown as a plain yes or no, and counts as before

#### Scenario: Strength without verdict
- **WHEN** a rating names a strength but no verdict
- **THEN** the rating is rejected with an error saying a strength needs a verdict

#### Scenario: Changing the level
- **WHEN** the user rates a posting "ja, vielleicht" and later "ja, auf jeden Fall"
- **THEN** the stored label holds the positive verdict with strength strong, and its other fields are unchanged

#### Scenario: Plain verdict after a level
- **WHEN** a posting stored as "nein, eher nicht" is rated negative without a strength
- **THEN** the stored label holds the negative verdict and no strength
