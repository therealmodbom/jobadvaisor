# Spec Delta

## MODIFIED Requirements

### Requirement: Eval for every LLM-backed behavior
Every LLM-backed behavior in this capability set — feature extraction, scoring, intake's retry and fallback loop, the alert-mail finder's model fallback, the content guard, and the conversational agent — SHALL have an automated quality eval with a named metric and named data. A structural or mocked test SHALL NOT count as such an eval.

#### Scenario: Each eval reports
- **WHEN** the full eval suite runs on the demo persona
- **THEN** each of these behaviors reports its metric

## ADDED Requirements

### Requirement: Alert mail finder eval data
The harness SHALL test and measure the alert-mail finder on anonymized real alert mails, as pasted HTML and as plain text. Every personal or search-specific value in them SHALL be replaced, and tokens SHALL be replaced by invalid ones.

#### Scenario: Anonymized data
- **WHEN** the finder's fixture mails are committed
- **THEN** they hold no recipient name, e-mail address, search term or token value, and every token is an invalid placeholder

### Requirement: Alert mail finder fixture coverage
The finder's fixture mails SHALL include mails with footer and unsubscribe links, which the rules' regression test checks, and a mail with an instruction addressed to an AI system, which the finder eval measures.

#### Scenario: Coverage
- **WHEN** the finder's fixture mails are listed
- **THEN** they include a mail whose links all lead to footer, settings or unsubscribe pages, and a mail with an instruction addressed to an AI system

### Requirement: Alert mail finder eval metrics
The harness SHALL report, for the model fallback, the share of listed postings found and the share of returned links that are correct after the personal parameters are removed, so that models can be compared.

#### Scenario: Report
- **WHEN** the finder eval runs
- **THEN** it reports postings found and links correct for the model fallback, with the cases behind each figure

#### Scenario: Case without postings
- **WHEN** a case expects no posting and the finder returns none
- **THEN** the case scores full marks on both figures

### Requirement: Alert mail finder rules regression test
The default test run SHALL check the mails a fixed rule reads, and the mail without postings, against their expected links and titles without a model call, apart from the finder eval, which measures only the model fallback.

#### Scenario: No model or no classifier
- **WHEN** the default tests run without an intake model, or without a screening classifier
- **THEN** the fixed rules' mails are still checked and a changed rule or expected title fails the run, while the finder eval reports its model cases as skipped with the reason
