# Spec Delta

## ADDED Requirements

### Requirement: Agent reports the strength of a rating
Wherever the agent reports a stored rating of a posting, it SHALL include the rating's strength when the label has one, so its answers can tell "ja, vielleicht" from "ja, auf jeden Fall".

#### Scenario: Question about a rating
- **WHEN** the user asks the agent how they rated a posting they rated "nein, eher nicht"
- **THEN** the agent's answer is based on the negative verdict with the strength weak, and names it as such

#### Scenario: Rating without strength
- **WHEN** the agent reports a rating whose label has no strength
- **THEN** it reports the verdict only
