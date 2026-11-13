# Spec Delta

## MODIFIED Requirements

### Requirement: Eval for every LLM-backed behavior
Every LLM-backed behavior in this capability set — feature extraction, scoring, intake's retry and fallback loop, the alert-mail finder's model fallback, the content guard, and the conversational agent — SHALL have an automated quality eval with a named metric and named data. A structural or mocked test SHALL NOT count as such an eval.

#### Scenario: Each eval reports
- **WHEN** the full eval suite runs on the demo persona
- **THEN** each of these behaviors reports its metric

## ADDED Requirements

### Requirement: Alert mail finder eval
The harness SHALL measure the alert-mail finder on fictional alert mails, as pasted HTML and as plain text. It SHALL report the share of listed postings found, and the share of returned links that are correct after the personal parameters are removed, per fixed rule and for the model fallback. Mails a fixed rule reads SHALL be measured without a model call. The data SHALL include mails with footer and unsubscribe links, and a mail with an instruction addressed to an AI system.

#### Scenario: Report
- **WHEN** the finder eval runs
- **THEN** it reports postings found and links correct for each fixed rule and for the model fallback, with the cases behind each figure

#### Scenario: No model or no classifier
- **WHEN** the finder eval runs without an intake model, or without a screening classifier
- **THEN** the fixed rules are still measured, and the model fallback is reported as skipped with the reason

#### Scenario: Case without postings
- **WHEN** a case expects no posting and the finder returns none
- **THEN** the case scores full marks on both figures
