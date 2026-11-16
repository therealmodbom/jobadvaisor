# Spec Delta

## MODIFIED Requirements

### Requirement: Eval for every LLM-backed behavior
Every LLM-backed behavior in this capability set — feature extraction, scoring, intake's retry and fallback loop, the alert-mail finder's model fallback, the content guard, and the conversational agent — SHALL have an automated quality eval with a named metric and named data. A structural or mocked test SHALL NOT count as such an eval.

#### Scenario: Each eval reports
- **WHEN** the full eval suite runs on the demo persona
- **THEN** each of these behaviors reports its metric

## ADDED Requirements

### Requirement: Alert mail finder eval data
The harness SHALL measure the alert-mail finder on anonymized real alert mails, as pasted HTML and as plain text. Every personal or search-specific value in them SHALL be replaced, and tokens SHALL be replaced by invalid ones.

#### Scenario: Anonymized data
- **WHEN** the finder eval's data is committed
- **THEN** it holds no recipient name, e-mail address, search term or token value, and every token is an invalid placeholder

### Requirement: Alert mail finder eval coverage
The finder eval's data SHALL include mails with footer and unsubscribe links, and a mail with an instruction addressed to an AI system.

#### Scenario: Coverage
- **WHEN** the finder eval's cases are listed
- **THEN** they include a mail whose links all lead to footer, settings or unsubscribe pages, and a mail with an instruction addressed to an AI system

### Requirement: Alert mail finder eval metrics
The harness SHALL report the share of listed postings found, and the share of returned links that are correct after the personal parameters are removed, per fixed rule and for the model fallback.

#### Scenario: Report
- **WHEN** the finder eval runs
- **THEN** it reports postings found and links correct for each fixed rule and for the model fallback, with the cases behind each figure

#### Scenario: Case without postings
- **WHEN** a case expects no posting and the finder returns none
- **THEN** the case scores full marks on both figures

### Requirement: Alert mail finder eval rules without a model
The harness SHALL measure the mails a fixed rule reads without a model call, so the fixed rules are measured also when no model or classifier is configured.

#### Scenario: No model or no classifier
- **WHEN** the finder eval runs without an intake model, or without a screening classifier
- **THEN** the fixed rules are still measured, and the model fallback is reported as skipped with the reason
