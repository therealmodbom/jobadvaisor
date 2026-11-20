# Spec Delta

## ADDED Requirements

### Requirement: Availability stored with the posting
A posting file MAY carry an availability: its state (available, closed or unknown), the time it was set, and who set it (a check or the user). The field SHALL be optional and SHALL NOT change the posting's schema version, so every posting file valid before this change stays valid and loads as never checked.

#### Scenario: Posting file without availability
- **WHEN** a posting file of schema version 1 or 2 holds no availability
- **THEN** it loads, and the posting counts as never checked

#### Scenario: Availability written
- **WHEN** a check finds a posting closed
- **THEN** the posting file holds the state closed, the time of the check and the check as its setter, and every other field is unchanged

### Requirement: Closed rules in the policy pack
The policy pack MAY hold a list of closed rules, each naming a host in the same form as a login-walled host and exactly one marker, a redirect marker or a page text marker, as non-empty text. The field SHALL be optional; a policy pack without it uses the default rules only. A rule naming no marker or both, or a malformed host, SHALL be rejected on load.

#### Scenario: Rule with both markers
- **WHEN** the second closed rule of the policy pack names a redirect marker and a page text marker
- **THEN** loading fails with an error naming the policy pack file and the rule's position in the list
