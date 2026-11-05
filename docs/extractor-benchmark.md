# Extractor benchmark

The benchmark measures how well one model extracts the features of your postings. It calls a paid model once per posting.

```bash
env -C backend uv run python -m jobadvaisor.evals.extractor_benchmark --data <path> --limit 5
env -C backend uv run python -m jobadvaisor.evals.extractor_benchmark --data <path> --model <model> [--base-url <url>]
env -C backend uv run python -m jobadvaisor.evals.extractor_benchmark --data <path> --history
env -C backend uv run python -m jobadvaisor.evals.extractor_benchmark --data <path> --compare <run id> <run id>
env -C backend uv run python -m jobadvaisor.evals.extractor_benchmark --data <path> --settle <disagreements file>
```

A run extracts the postings with one model (`EXTRACTOR_MODEL`, falling back to `LLM_MODEL`, unless `--model` names another) and prints one table. The table shows the accuracy per feature, the cost per posting, the mean latency, the posting count and the failed calls. `--limit N` takes the first N postings in ID order. Every run appends a record to `<STATE_DIRECTORY>/<repository key>/benchmark/records.jsonl` and stores the extracted values in `benchmark/runs/`. The records hold figures and the parameters of the approach (model, base URL, hashes of the extraction instructions and the feature set, the commit). They hold no posting text and no extracted value.

`--role decider` runs the hosted decision model that `--model` names (required) instead, through the router's `questions` format. A decision model answers only the categorical features, as `choice` questions, so its table, its accuracy and its comparisons cover those features. It is the way to try a model such as `typesafe/jev-1.14.0`, which the extractor's structured output cannot reach.

Accuracy needs labels. The data repository may hold `extraction-labels.json` with hand-settled values (`labels[posting ID][feature ID]`) and an optional `min_accuracy` between 0 and 1. The schema is `schemas/extraction-labels.schema.json`. Without labels the table says that no accuracy was computed. With labels, accuracy covers the labelled cases only and shows the case count per feature. A failed call counts as wrong.

`--compare` takes two or more stored runs. It reports the agreement per feature over the postings every run answered, with each run's model, cost and latency side by side. It also writes the unlabelled disagreements to `benchmark/disagreements-<stamp>.json`, the postings with the most differing features first. Fill in `label` for the cases you can judge and pass the file to `--settle`. That merges the filled entries into `extraction-labels.json`, and the next run reports accuracy against them. Agreement says nothing about correctness, since two models can agree and both be wrong.

The state directory must lie outside this repository and outside the data repository. Every mode refuses to start otherwise and names `STATE_DIRECTORY`. With both Langfuse keys set, a run is also recorded in Langfuse as an experiment. A Langfuse failure only prints a warning.

The accuracy of the configured extractor also runs as a DeepEval suite. It makes paid calls and fails below `min_accuracy`. Set DeepEval's folder before starting, since DeepEval reads it at import. The failure message prints the exact value if it is missing.

```bash
env -C backend DEEPEVAL_CACHE_FOLDER=<state directory of the repository>/deepeval uv run deepeval test run tests/accuracy_suite.py
```
