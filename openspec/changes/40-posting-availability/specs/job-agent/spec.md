# Spec Delta

## ADDED Requirements

### Requirement: Closed postings are no recommendation
The agent's list of best-fitting postings SHALL leave out closed postings, whatever application statuses it is asked for.

#### Scenario: Which to apply to
- **WHEN** the top-scored open posting is closed and the agent lists the best-fitting postings
- **THEN** the list does not hold the closed posting

### Requirement: Agent tools name a closed posting
Wherever an agent tool returns a stored posting, its result SHALL say whether the posting is closed, so the agent can tell the user.

#### Scenario: Search finds a closed posting
- **WHEN** the agent searches the stored postings and one match is closed
- **THEN** the tool's result marks that match as closed

### Requirement: Agent sets no availability
No agent tool SHALL change a posting's availability or start a check of availability.

#### Scenario: Tool set
- **WHEN** the agent's tools are listed
- **THEN** none of them writes an availability or starts a check
