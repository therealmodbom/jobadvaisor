# Spec Delta

## Purpose

Lets the user ask questions about triage results and trigger actions in conversation, using the same capabilities the triage run uses.

## ADDED Requirements

### Requirement: Shared capabilities
The conversational agent SHALL act only through the shared tool set that triage and intake also use: fetching a posting, checking exclusions, extracting features, finding similar rated postings, scoring a posting, and researching a company.

#### Scenario: Same result as triage
- **WHEN** the agent checks exclusions for a posting
- **THEN** the result equals the triage run's exclusion result for that posting and policy pack

### Requirement: Explaining a decision
The agent SHALL answer why a posting was excluded or scored as it was, citing the stored exclusion rule, features, score reasoning or rated examples.

#### Scenario: Why excluded
- **WHEN** the user asks why a posting was excluded
- **THEN** the answer names the exclusion rule that matched

### Requirement: Finding similar postings
The agent SHALL find stored postings similar to one the user names.

#### Scenario: More like this
- **WHEN** the user asks for postings like a given posting
- **THEN** the answer lists stored postings ranked by similarity to it

### Requirement: Rescoring on request
The agent SHALL rescore a batch on request, using the labels stored at that moment, and SHALL report how the scores changed.

#### Scenario: Rescore after feedback
- **WHEN** the user asks to rescore a batch after rating new postings
- **THEN** the batch is scored again and the answer lists the postings whose score changed

### Requirement: No silent data changes
The agent SHALL NOT create, change or delete labels, policy rules or profile data on its own. Changes to user data happen only through the rating flow.

#### Scenario: Request to relabel
- **WHEN** the user asks the agent to mark a posting as positive
- **THEN** the agent points to the rating flow and stores no label itself
