# Spec Delta

## MODIFIED Requirements

### Requirement: Rescoring on request
The agent SHALL rescore a posting or a set of postings on request, using the labels stored at that moment, and SHALL report how the scores changed. The stored score of the pool changes only through a pass or a single score the user starts.

#### Scenario: Rescore after feedback
- **WHEN** the user asks to rescore some postings after rating new ones
- **THEN** they are scored again and the answer lists the postings whose score changed

#### Scenario: Pool unchanged
- **WHEN** the agent rescored postings on request
- **THEN** the stored scores of the pool stay as the last pass or single score left them
