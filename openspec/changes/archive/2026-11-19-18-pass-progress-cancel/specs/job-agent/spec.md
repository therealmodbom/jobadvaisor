## MODIFIED Requirements

### Requirement: Shared capabilities
The conversational agent SHALL act only through the shared tool set that triage and intake draw on (a scoring pass reads no features, the agent still can): fetching a posting, checking exclusions, extracting features, finding similar rated postings, scoring a posting, and researching a company.

#### Scenario: Same result as triage
- **WHEN** the agent checks exclusions for a posting
- **THEN** the result equals the triage run's exclusion result for that posting and policy pack
