# Proposal

## Why

The goal is to follow how well the extraction approach performs over time, and to know with numbers whether a cheaper extractor such as `typesafe/jev-1.14.0` is as good as the current one before `EXTRACTOR_MODEL` is switched (issue #69, the extraction half of #58). Today's `feature_extraction` eval runs one model against hand-written expectations on the demo persona only, measures no latency and keeps no history. Real postings have no expected values, so the ground truth has to grow out of the runs themselves.

## What Changes

- A benchmark command runs **one extractor** over the postings of a data repository and prints one table: result per feature, cost per posting, mean latency, posting count, with the metric named. The model is the configured extractor, or one named for the run.
- Each run appends one record to a JSONL file under the state directory: date, model, base URL, hashes of the extraction instructions and of the feature set, the app's commit, metrics with case counts, cost, latency, errors. The run's extracted values are stored next to it, outside both repositories; the command refuses a state directory inside this repository or the data repository, and DeepEval's own run files are kept there too (no posting text in them). A history view prints the records, so the performance of the extraction approach can be followed across days, including the effect of a prompt or feature-set change.
- The command compares two or more stored runs (typically different models): agreement per feature, cost and latency side by side, and a disagreements file for the user, the postings that differ most first. The user's judgements are merged as extraction labels in the data repository (`--settle`).
- Once labels exist, every run also reports accuracy against them, with the case count.
- The accuracy against labels is a custom DeepEval metric, and the same cases run as a test suite through `deepeval test run` (excluded from the default test run, fails below an optional minimum accuracy). Agreement, comparison, metering, records and the Langfuse mirror stay own code. Moving the existing evals the same way is issue #72.
- With Langfuse configured, each run is also recorded there as an experiment (scores, cost, latency). The JSONL file stays the history the command reads.
- The record format carries a `role` (`extractor`, `judge`, `decider`) so the scoring benchmark (#70) reuses it. Only `extractor` is built here.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `match-evaluation`: new requirements for the extractor benchmark run, comparing stored runs, settling disagreements into labels, run records, the Langfuse mirror and the accuracy test suite.
- `data-repository`: an optional extraction-labels file with a published schema.

## Impact

- New module `backend/jobadvaisor/evals/extractor_benchmark.py`, run as `python -m jobadvaisor.evals.extractor_benchmark`, and a DeepEval test module for `deepeval test run`; `deepeval` is added to the backend dependencies.
- New model `ExtractionLabels` in `backend/jobadvaisor/data/models.py`, its schema in `schemas/`, loaded optionally by `data/loader.py`.
- `llm.py`: the model construction of `chat_model` is split out so a model and base URL named for one run build a client without a settings field.
- README and the evals section of `AGENTS.md` mention the command.
- Costs: a run calls the model once per posting. The first real runs (a few cents each) happen only on explicit go-ahead.

## Non-goals

- Judge and decision-model comparison, precision@k and the time split (#70). Only the record format is prepared for it.
- Switching `EXTRACTOR_MODEL`. The user decides from the runs.
- Rescoring stored postings.
- A web UI, scheduling or a run on a new model's release. The command stays a script, as evals may.
- Replacing the existing `feature_extraction` eval or its demo `expected.json`, or moving any existing eval onto DeepEval (#72).
- DeepEval's hosted report store (Confident AI) and judge-model metrics.
- A checker model that settles disagreements.
