# match-evaluation Specification

## Purpose
Measures whether the learning job match and every other LLM-backed behavior actually work, with automated, repeatable evals on labeled data.

## Requirements

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
When a run names a decision model, the harness SHALL evaluate it as a further competitor: scoring postings on the same time split, reported with precision@k and cost per posting next to the LLM judge, and filling the categorical features, reported with per-field accuracy next to the extractor. The decision model SHALL come from the run's command line and SHALL NOT come from a setting, so changing the content guard's model never changes what these evals test.

#### Scenario: Decision model configured
- **WHEN** the eval suite runs with a decision model named for the run
- **THEN** the report shows the decision model's precision@k, cost per posting and per-field accuracy next to the LLM judge's and the extractor's

#### Scenario: No decision model configured
- **WHEN** the run names no decision model, even though a content-guard model is configured
- **THEN** the report states that the decision-model competitor was skipped and why

### Requirement: Content-guard eval tests the guard model of the run
The content-guard eval SHALL report one row for Mistral Moderation and one for the decision model named for the run, each with its own default thresholds, and SHALL skip a row with its reason when it is not available. A regression run SHALL name the model the app runs as the content guard's classifier, so the eval and the app cannot disagree about the guard; a search run MAY name another model.

#### Scenario: Guard model named
- **WHEN** the eval runs with a decision model named for the run
- **THEN** the report has a row for that model next to Mistral Moderation's row

#### Scenario: No guard model named
- **WHEN** the eval runs without a named decision model
- **THEN** the decision-model row states that it was skipped and why, and Mistral Moderation's row is unaffected

### Requirement: Graph versus agent
The harness SHALL compare triage as the fixed graph against triage as the free agent with the same capabilities, reporting precision@k, cost per posting and the variance across repeated runs.

#### Scenario: Comparison report
- **WHEN** the comparison runs with a number of repetitions
- **THEN** the report shows precision@k, cost per posting and variance for both variants

### Requirement: Eval for every LLM-backed behavior
Every LLM-backed behavior in this capability set — feature extraction, scoring, intake's retry and fallback loop, the alert-mail finder's model fallback, the content guard, and the conversational agent — SHALL have an automated quality eval with a named metric and named data. A structural or mocked test SHALL NOT count as such an eval.

#### Scenario: Each eval reports
- **WHEN** the full eval suite runs on the demo persona
- **THEN** each of these behaviors reports its metric

### Requirement: Private results stay private
Evals SHALL run against any configured data repository. Results from a real user's data SHALL be written outside this repository.

#### Scenario: Run on real data
- **WHEN** an eval runs against a data repository other than the demo persona
- **THEN** its report is written outside this repository

### Requirement: Extractor benchmark run
The harness SHALL provide one command that runs one extractor over the postings of a data repository and prints one table: the result per feature, the cost per posting, the mean latency and the number of postings. The extractor is the configured one unless a model, and optionally a base URL, is named for the run. A failed call SHALL be recorded as an error of the run and SHALL NOT stop it.

#### Scenario: One run
- **WHEN** the command runs with the configured extractor
- **THEN** it extracts the postings and prints one table with the per-feature result, cost per posting, mean latency and posting count

#### Scenario: Another model for one run
- **WHEN** the command runs with a model named for the run
- **THEN** that model extracts the postings and the table and the stored record name it

#### Scenario: One call fails
- **WHEN** a call fails for one posting
- **THEN** the error is listed in the table and the run goes on with the next posting

#### Scenario: Limited run
- **WHEN** the command runs with a posting limit
- **THEN** it extracts the first postings in posting-ID order, so runs with the same limit see the same postings, and the table shows that count

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

### Requirement: Named benchmark metric
Every figure of the benchmark SHALL name its metric and the number of cases it rests on. Accuracy is the share of labelled cases in which an extracted value equals the label, where a failed call counts as wrong; it SHALL appear only for features with labels and SHALL NOT be presented as accuracy on all postings. Agreement is the share of postings on which all compared runs gave the same value for a feature, counted over postings every compared run answered.

#### Scenario: No labels yet
- **WHEN** the data repository holds no extraction labels
- **THEN** a run's table shows no accuracy and states that none was computed

#### Scenario: Labels exist
- **WHEN** extraction labels cover some features of some postings
- **THEN** a run's table shows the accuracy for the labelled cases, with the case count per feature

### Requirement: Comparing stored runs
The command SHALL compare two or more stored runs on the postings every one of them answered, and print per feature the agreement, with each run's model, cost per posting and mean latency side by side. It SHALL write the cases on which the runs disagree and that have no label to a disagreements file outside this repository, listing posting, feature, each run's value and an empty label, with the postings that differ in most features first.

#### Scenario: Two runs compared
- **WHEN** two stored runs of different models are compared
- **THEN** the report shows per feature the agreement and the number of postings it rests on, and the disagreements file lists the unlabelled cases where the values differ, the most-differing postings first

#### Scenario: Fewer than two runs
- **WHEN** fewer than two runs are named
- **THEN** the command stops and says that a comparison needs at least two

#### Scenario: Runs over different postings
- **WHEN** the compared runs did not extract the same postings
- **THEN** only the postings every run answered are compared, and the report states how many that is

#### Scenario: Labelled case is not listed
- **WHEN** a case already has a label
- **THEN** a disagreement on it is not listed

### Requirement: Settling disagreements into labels
Filling in the labels of a disagreements file and passing the file back to the command SHALL merge the filled entries into the data repository's extraction labels and leave empty entries unmerged.

#### Scenario: User settles
- **WHEN** the user fills in labels and passes the file back
- **THEN** the filled labels are in the data repository's extraction labels and the next run reports accuracy against them

#### Scenario: Empty entries
- **WHEN** an entry of the file has no label
- **THEN** it is not merged

### Requirement: Benchmark run records
Each benchmark run SHALL append one record to a JSONL file in the data repository's state directory: run ID, date, data repository key, role, model, base URL, a hash of the extraction instructions, a hash of the feature set, the app's commit, the metrics with their case counts, per-feature results, cost per posting, mean latency and errors. The run's extracted values SHALL be stored in a separate file in the same state directory, one per run, which a comparison reads. A history view SHALL print the stored records as a table. The record format SHALL name the role, so the scoring benchmark can store its records in the same file.

#### Scenario: Two runs on different days
- **WHEN** the command ran on two days
- **THEN** the history view shows both runs, one row per run, with date, model, metric, case count, cost, latency and the run ID that the comparison takes

#### Scenario: Approach change is visible
- **WHEN** the extraction instructions or the feature set change between two runs
- **THEN** the hashes in their records differ

#### Scenario: Records stay private
- **WHEN** the benchmark runs against a data repository other than the demo persona
- **THEN** the records, the extracted values and the disagreements file are written outside this repository and outside the data repository

#### Scenario: Eval framework files stay in the state directory
- **WHEN** the benchmark or the accuracy suite runs
- **THEN** the files the eval framework writes for the run are in the state directory, none in the working directory, and they hold no posting text

#### Scenario: State directory inside a repository
- **WHEN** the resolved state directory lies inside this repository or inside the data repository
- **THEN** the command stops before any model call, writes nothing, and names the setting to change

#### Scenario: No posting text in records
- **WHEN** a record is written
- **THEN** it holds figures, parameters and feature identifiers, and no posting text or extracted value

### Requirement: Benchmark runs mirrored to Langfuse
When Langfuse is configured, the benchmark SHALL also record each run there as an experiment on the same postings, carrying the metric scores with their case counts, the cost per posting and the mean latency, so runs can be compared in Langfuse. The JSONL records remain the history the command reads. A failure to reach Langfuse SHALL NOT fail the run or prevent the JSONL record from being written.

#### Scenario: Langfuse configured
- **WHEN** the benchmark runs with Langfuse configured
- **THEN** the run appears in Langfuse as an experiment with its scores, cost and latency, and the JSONL record is written as well

#### Scenario: Langfuse not configured
- **WHEN** the benchmark runs without Langfuse keys
- **THEN** only the JSONL record is written and no error is raised

#### Scenario: Langfuse unreachable
- **WHEN** recording to Langfuse fails
- **THEN** the JSONL record is written, the table is printed, and the failure is reported as a warning

### Requirement: Accuracy suite in the eval test runner
The accuracy of the configured extractor against extraction labels SHALL also run through the eval test runner, as a test suite with one case per labelled posting. When the extraction labels set a minimum accuracy, the suite SHALL fail if the accuracy falls below it. The suite SHALL make model calls only when run explicitly and SHALL NOT run with the default test run.

#### Scenario: Suite run
- **WHEN** the suite is run explicitly against a data repository with labels
- **THEN** the extractor is scored on the labelled postings and the per-feature accuracy equals what the benchmark command reports for the same run

#### Scenario: Below the minimum
- **WHEN** the labels set a minimum accuracy and the accuracy is below it
- **THEN** the suite fails and names the accuracy and the minimum

#### Scenario: Nothing to score
- **WHEN** the data repository holds no extraction labels
- **THEN** the suite is skipped with the reason

#### Scenario: Default test run
- **WHEN** the default test run executes
- **THEN** the suite is not collected and no model is called

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
