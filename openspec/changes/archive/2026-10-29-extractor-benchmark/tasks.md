# Tasks

## 1. Data repository: extraction labels

- [x] 1.1 Add `ExtractionLabels` (labels per posting and feature, optional `min_accuracy` between 0 and 1) to `data/models.py` and generate its schema into `schemas/`; verify the schema-sync test passes and an out-of-range `min_accuracy` is rejected
- [x] 1.2 Load the file as optional in `data/loader.py` and fail a label naming a missing posting or a feature outside the feature set; verify loader tests cover an absent file, a valid file, a missing posting, an unknown feature, and the demo persona still loads

## 2. Plumbing

- [x] 2.1 Split the model construction of `chat_model` in `llm.py` into a function taking (model, base URL, settings) that `chat_model` calls; verify `test_llm.py` passes unchanged and a new test builds a client from a pair
- [x] 2.2 Add `deepeval` (4.2.x, as checked in design.md) to the backend dependencies and import it only through one helper that first sets `DEEPEVAL_CACHE_FOLDER` and `DEEPEVAL_RESULTS_FOLDER` to the state directory (after the boundary check of 3.4a); verify a test run of a deterministic custom `BaseMetric` through `evaluate` makes no network call, leaves no `.deepeval` folder in the working directory and writes its files into the state directory

## 3. The run

- [x] 3.1 Extract the postings with one model, metering cost and wall-clock latency per call and collecting failed calls as errors; verify with a stub model that a failing call is an error and the run goes on, and that `--limit` takes the first N postings in ID order
- [x] 3.2 Compute the approach parameters (hash of the extraction instructions, hash of the feature set, the app's commit, null outside git); verify the hashes stay equal for equal input and change when the instruction text or the feature set changes
- [x] 3.3 Compute accuracy per feature with a custom DeepEval metric on one `LLMTestCase` per labelled posting with the posting ID as `input` (never its text), the run ID as `identifier` and the model, base URL and the two hashes as `hyperparameters` (failed call = wrong, the extraction eval's value normalization); verify with stubs: no labels gives no accuracy, labels give accuracy with case counts, a list is scored as a set and text ignoring case
- [x] 3.4 Append the JSONL record and write the run's extracted values to `benchmark/runs/<run id>.json` in the state directory, refusing to overwrite an existing run file; verify the record holds figures and parameters but no posting text or extracted value, and the values file holds them
- [x] 3.4a Resolve the state directory before any model call and stop, naming the setting, when it lies inside this repository or inside the data repository (symlinks and relative paths resolved), for run, `--compare` and `--history`; verify tests for a state directory inside each repository, for one beside it, and that nothing is written and no model is called in the refused cases
- [x] 3.5 Print the table (per-feature result with the metric named and case counts, cost per posting, mean latency, posting count, errors); verify the output names the metric

- [x] 3.6 Run a decision model as the subject (`--role decider`, model `DECIDER_MODEL` or `--model`): categorical features as `choice` questions through the existing `evals/decider.py` call, the router's cost metered, record role `decider`, labels restricted to the answered features; verify with a stub client that only categorical features are asked, a label on another feature is not counted, the record says `decider`, and the comparison with an extractor run lists only the common features

## 4. Comparing runs and settling

- [x] 4.1 `--compare RUN_ID ...`: agreement per feature over the postings every run answered, each run's model, cost and latency side by side; verify two runs over different postings use the common ones and say how many, and fewer than two runs stops with a message
- [x] 4.2 Write the unlabelled disagreements to the disagreements file, postings with the most differing features first; verify a labelled case is not listed and the order is by differing-feature count
- [x] 4.3 `--settle FILE` merges the non-null labels into `extraction-labels.json`, creating it if absent; verify empty entries stay unmerged, an existing label is overwritten only by a filled entry, and the result loads
- [x] 4.4 `--history` prints the stored records as a table; verify two records with different dates appear as separate rows

## 5. Langfuse mirror and test suite

- [x] 5.1 With both Langfuse keys set, record the run as a Langfuse experiment (scores with case counts, cost per posting, mean latency, replayed values) after the JSONL record is written; a failure only warns. Verify with a stub client: keys set → one run with those scores; no keys → no call and no error; client raising → record and table still produced and a warning printed
- [x] 5.2 Add the DeepEval test module for `deepeval test run` (same cases as the command for the configured extractor, fail below `min_accuracy`, skip with the reason when there are no labels) named so the default `pytest` run never collects it; verify with a stub model that the default run collects none of it, an explicit run scores and fails below the minimum, and the figures equal the command's

## 6. Documentation and wrap-up

- [x] 6.1 Document the command, the labels file and the metrics in the README evals section, and update the "Current state" paragraph of `AGENTS.md`; verify by reading both against the spec
- [x] 6.2 Run `ruff` and the full backend test suite and verify both are clean
- [x] 6.3 On the user's word, run the command once with the current extractor and once with `typesafe/jev-1.14.0` on the stored postings, compare the two runs, and let the user judge the largest disagreements; verify two records exist and note only the outcome (metric, direction of the result) in the PR, without posting text or counts of the user's data
