# Spec Delta

## MODIFIED Requirements

### Requirement: Rescoring on request
The agent SHALL rescore a posting or a set of postings on request, using the labels stored at that moment, and SHALL report how the scores changed. The stored score of the pool changes only through a pass the user starts.

#### Scenario: Rescore after feedback
- **WHEN** the user asks to rescore some postings after rating new ones
- **THEN** they are scored again and the answer lists the postings whose score changed

#### Scenario: Pool unchanged
- **WHEN** the agent rescored postings on request
- **THEN** the stored scores of the pool stay as the last pass left them

### Requirement: No silent data changes
The agent SHALL NOT create, change or delete labels, policy rules, profile data or application statuses on its own. Changes to user data happen only through the rating flow and the pool.

#### Scenario: Request to relabel
- **WHEN** the user asks the agent to mark a posting as positive
- **THEN** the agent points to the rating flow and stores no label itself

#### Scenario: Request to mark as applied
- **WHEN** the user asks the agent to mark a posting "beworben"
- **THEN** the agent points to the pool and stores no status itself

## ADDED Requirements

### Requirement: Best-fitting open postings over the pool
The agent SHALL list the best-fitting open postings across the whole pool without a run, in the order of the pool's ranking, each with score, the user's rating, application status and a link to its page. It SHALL leave out postings with the status "beworben" or "erledigt" unless asked. It SHALL answer questions about stored ratings (chips and notes), for example which postings the user marked "too junior".

#### Scenario: Which to apply to
- **WHEN** the user asks which posting they should apply to and no run exists
- **THEN** the answer lists the top open postings of the pool with score, rating and a link each

#### Scenario: Ratings by chip
- **WHEN** the user asks which postings they marked with a chip
- **THEN** the answer lists the postings whose stored label carries that chip
