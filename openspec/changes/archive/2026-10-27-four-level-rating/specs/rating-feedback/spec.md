# Spec Delta

## ADDED Requirements

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
