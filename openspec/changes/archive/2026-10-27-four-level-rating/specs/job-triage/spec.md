# Spec Delta

## ADDED Requirements

### Requirement: Rated examples carry the strength
Each rated posting shown to the judge as an example SHALL state the strength of its rating next to the verdict when the label has one. An example whose label has no strength SHALL read as before.

#### Scenario: Example with strength
- **WHEN** the judge is shown a posting rated "nein, auf keinen Fall"
- **THEN** its example states the negative verdict and the strength strong, with the user's reasons

#### Scenario: Example without strength
- **WHEN** the judge is shown a posting whose label has a verdict and no strength
- **THEN** its example states the verdict only
