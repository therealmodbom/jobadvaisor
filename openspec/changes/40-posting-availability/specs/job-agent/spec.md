# Spec Delta

## ADDED Requirements

### Requirement: Closed postings are no recommendation
The tool that lists the best-fitting postings SHALL leave out closed postings, whatever application statuses it is asked for.

#### Scenario: Top-scored posting closed
- **WHEN** the top-scored open posting is closed and the tool lists the best-fitting postings
- **THEN** its result does not hold the closed posting

### Requirement: Search results mark a closed posting
The tools that search the stored postings and find similar ones SHALL mark each closed posting in their result.

#### Scenario: Search finds a closed posting
- **WHEN** the search tool's matches include a closed posting
- **THEN** the tool's result marks that match as closed

## MODIFIED Requirements

### Requirement: No silent data changes
The agent SHALL NOT create, change or delete labels, policy rules, profile data, application statuses or availabilities on its own, and SHALL NOT start a check of availability. Changes to user data happen only through the rating flow, the pool and the posting page.

#### Scenario: Request to relabel
- **WHEN** the user asks the agent to mark a posting as positive
- **THEN** the agent points to the rating flow and stores no label itself

#### Scenario: Request to mark as applied
- **WHEN** the user asks the agent to mark a posting "beworben"
- **THEN** the agent points to the pool and stores no status itself

#### Scenario: No tool writes an availability
- **WHEN** the agent's tools are listed
- **THEN** none of them writes an availability or starts a check
