# Spec Delta

## Purpose

Measures whether the learning job match and every other LLM-backed behavior actually work, with automated, repeatable evals on labeled data.

## ADDED Requirements

### Requirement: Precision at k on held-out labels
The eval harness SHALL report precision@k for the triage ranking on labels held out by time: labels recorded after a cut-off date are scored using only labels recorded before it.

#### Scenario: Time split respected
- **WHEN** the harness evaluates with a cut-off date
- **THEN** no label recorded after the cut-off is used as an example or for training

#### Scenario: Report
- **WHEN** an eval run completes
- **THEN** it reports precision@k, the k used, the number of held-out labels and the cut-off date

### Requirement: Baseline comparison
The harness SHALL report the same metric for a baseline that reproduces the old process's decisions, measured on a rated sample of the postings the old process discarded.

#### Scenario: Baseline row
- **WHEN** the labels include the old process's decisions
- **THEN** the report shows the baseline's precision@k next to the system's

### Requirement: Decision-model competitor
From a configurable minimum number of labels (default 100), the harness SHALL also evaluate a logistic regression trained on the extracted features, and report it next to the LLM judge.

#### Scenario: Enough labels
- **WHEN** at least the minimum number of training labels exists
- **THEN** the report includes the logistic regression's precision@k

#### Scenario: Too few labels
- **WHEN** fewer labels exist
- **THEN** the report states that the competitor was skipped and why

### Requirement: Hosted decision-model competitor
When a decision model is configured, the harness SHALL evaluate it as a further competitor: scoring postings on the same time split, reported with precision@k and cost per posting next to the LLM judge, and filling the categorical features, reported with per-field accuracy next to the extractor.

#### Scenario: Decision model configured
- **WHEN** the eval suite runs with a decision model configured
- **THEN** the report shows the decision model's precision@k, cost per posting and per-field accuracy next to the LLM judge's and the extractor's

#### Scenario: No decision model configured
- **WHEN** no decision model is configured
- **THEN** the report states that the decision-model competitor was skipped and why

### Requirement: Graph versus agent
The harness SHALL compare triage as the fixed graph against triage as the free agent with the same capabilities, reporting precision@k, cost per posting and the variance across repeated runs.

#### Scenario: Comparison report
- **WHEN** the comparison runs with a number of repetitions
- **THEN** the report shows precision@k, cost per posting and variance for both variants

### Requirement: Eval for every LLM-backed behavior
Every LLM-backed behavior in this capability set — feature extraction, scoring, intake's retry and fallback loop, the content guard, and the conversational agent — SHALL have an automated quality eval with a named metric and named data. A structural or mocked test SHALL NOT count as such an eval.

#### Scenario: Each eval reports
- **WHEN** the full eval suite runs on the demo persona
- **THEN** each of these behaviors reports its metric

### Requirement: Private results stay private
Evals SHALL run against any configured data repository. Results from a real user's data SHALL be written outside this repository.

#### Scenario: Run on real data
- **WHEN** an eval runs against a data repository other than the demo persona
- **THEN** its report is written outside this repository
