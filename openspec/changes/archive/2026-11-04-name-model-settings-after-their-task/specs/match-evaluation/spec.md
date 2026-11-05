# Spec Delta

## MODIFIED Requirements

### Requirement: Hosted decision-model competitor
When a run names a decision model, the harness SHALL evaluate it as a further competitor: scoring postings on the same time split, reported with precision@k and cost per posting next to the LLM judge, and filling the categorical features, reported with per-field accuracy next to the extractor. The decision model SHALL come from the run's command line and SHALL NOT come from a setting, so changing the content guard's model never changes what these evals test.

#### Scenario: Decision model configured
- **WHEN** the eval suite runs with a decision model named for the run
- **THEN** the report shows the decision model's precision@k, cost per posting and per-field accuracy next to the LLM judge's and the extractor's

#### Scenario: No decision model configured
- **WHEN** the run names no decision model, even though a content-guard model is configured
- **THEN** the report states that the decision-model competitor was skipped and why

### Requirement: Decision models as benchmark subjects
The command SHALL be able to run a hosted decision model, named for the run, in place of the extractor. The command SHALL refuse a decision-model run that names no model. A decision model answers each categorical feature as a typed `choice` question with "unknown" as an extra option, so it has no answer for the other features. Its run is printed, stored, compared and mirrored like an extractor's run, with the record's role `decider`. Accuracy SHALL count only the labelled features the run answers, and a comparison SHALL cover only the features every compared run answered.

#### Scenario: Decision-model run
- **WHEN** the command runs with the decision-model role and a model
- **THEN** it asks the categorical features of each posting as choice questions, prints the table for those features, and stores a record with the role `decider` and the model

#### Scenario: Decision-model run without a model
- **WHEN** the command runs with the decision-model role and no model, even though a content-guard model is configured
- **THEN** it stops with a usage error that asks for a model, before any model call

#### Scenario: Labels for features it does not answer
- **WHEN** the labels cover a feature that is not categorical and the run is a decision-model run
- **THEN** the accuracy of that run does not count that feature

#### Scenario: Extractor and decision model compared
- **WHEN** a stored extractor run and a stored decision-model run are compared
- **THEN** the report shows the agreement only for the features both answered

## ADDED Requirements

### Requirement: Content-guard eval tests the guard model of the run
The content-guard eval SHALL report one row for Mistral Moderation and one for the decision model named for the run, each with its own default thresholds, and SHALL skip a row with its reason when it is not available. A regression run SHALL name the model the app runs as the content guard's classifier, so the eval and the app cannot disagree about the guard; a search run MAY name another model.

#### Scenario: Guard model named
- **WHEN** the eval runs with a decision model named for the run
- **THEN** the report has a row for that model next to Mistral Moderation's row

#### Scenario: No guard model named
- **WHEN** the eval runs without a named decision model
- **THEN** the decision-model row states that it was skipped and why, and Mistral Moderation's row is unaffected
