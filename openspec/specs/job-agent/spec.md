# job-agent Specification

## Purpose
Lets the user ask questions about triage results and trigger actions in conversation, using the same capabilities the triage run uses.

## Requirements

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
The agent SHALL rescore a posting or a set of postings on request, using the labels stored at that moment, and SHALL report how the scores changed. The stored score of the pool changes only through a pass or a single score the user starts.

#### Scenario: Rescore after feedback
- **WHEN** the user asks to rescore some postings after rating new ones
- **THEN** they are scored again and the answer lists the postings whose score changed

#### Scenario: Pool unchanged
- **WHEN** the agent rescored postings on request
- **THEN** the stored scores of the pool stay as the last pass or single score left them

### Requirement: No silent data changes
The agent SHALL NOT create, change or delete labels, policy rules, profile data or application statuses on its own. Changes to user data happen only through the rating flow and the pool.

#### Scenario: Request to relabel
- **WHEN** the user asks the agent to mark a posting as positive
- **THEN** the agent points to the rating flow and stores no label itself

#### Scenario: Request to mark as applied
- **WHEN** the user asks the agent to mark a posting "beworben"
- **THEN** the agent points to the pool and stores no status itself

### Requirement: Agent reports the strength of a rating
Wherever the agent reports a stored rating of a posting, it SHALL include the rating's strength when the label has one, so its answers can tell "ja, vielleicht" from "ja, auf jeden Fall".

#### Scenario: Question about a rating
- **WHEN** the user asks the agent how they rated a posting they rated "nein, eher nicht"
- **THEN** the agent's answer is based on the negative verdict with the strength weak, and names it as such

#### Scenario: Rating without strength
- **WHEN** the agent reports a rating whose label has no strength
- **THEN** it reports the verdict only

### Requirement: Best-fitting open postings over the pool
The agent SHALL list the best-fitting open postings across the whole pool without a run, in the order of the pool's ranking, each with score, the user's rating, application status and a link to its page. It SHALL leave out postings with the status "beworben" or "erledigt" unless asked. It SHALL answer questions about stored ratings (chips and notes), for example which postings the user marked "too junior".

#### Scenario: Which to apply to
- **WHEN** the user asks which posting they should apply to and no run exists
- **THEN** the answer lists the top open postings of the pool with score, rating and a link each

#### Scenario: Ratings by chip
- **WHEN** the user asks which postings they marked with a chip
- **THEN** the answer lists the postings whose stored label carries that chip
