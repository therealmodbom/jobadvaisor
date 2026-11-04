# Design

## Context

See proposal.md, Why. At the start, `decider(settings)` in `llm.py` read `DECIDER_MODEL` for three consumers: the guard (`classifier_from_settings`), the `decider_competitor` eval and the content-guard eval row, and `extractor_benchmark --role decider`. `decider_client(model, base_url, settings)` already builds a client for an explicit pair and stays the shared builder. The guard calls its model in the router's `questions` format (`DeciderClassifier`), which only some models answer.

## Goals / Non-Goals

**Goals:**
- Setting names follow the task: only the content guard has one.
- An eval that tests a decision model gets it from its command line.

**Non-Goals:** see proposal.md, Non-Goals.

## Decisions

- **`GUARD_MODEL` stays a `questions`-format model.** The format belongs to the guard role, not to the setting's name. A chat-format safety model is added in #50 behind its own setting, so no `GUARD_FORMAT` switch exists for a case that does not exist. Rejected: `GUARD_FORMAT=questions|chat` now, more surface for no user.
- **`--model` and `--base-url` on `python -m jobadvaisor.evals`, built once in `main` into a candidate `Decider`.** `content_guard` and `decider_competitor` move into `CANDIDATE_EVALS` and receive it as a third argument; every other eval keeps its `(repository, settings)` signature. `--base-url` falls back to `LLM_BASE_URL`, not to `GUARD_BASE_URL`, since the option belongs to the run. Rejected: copying settings with `GUARD_MODEL` replaced by `--model`, because that would also change the guard that scoring and agent evals run with.
- **The regression run lives in the workflow, not in code.** CI passes `--model "$GUARD_MODEL"`. A plain local run without `--model` skips the guard row. Rejected: defaulting the row to `GUARD_MODEL` in code, which would make every run name its candidate except this one; it also keeps the contract of #55 (models per task from the configuration or the command line) uniform.
- **`--role decider` requires `--model`; its `--base-url` stays optional.** No setting stands in for the model.
- **No startup check for a leftover `DECIDER_MODEL`.** The check would exist for one rename. The owner renames `local.env` and the Actions variable with the merge. The cost is a silent fall-back to Mistral or off if one is forgotten, which the guard's startup notice and the intake view show ("screening is off").
- **Code names stay.** `Decider`, `evals/decider.py`, `--role decider` and `decider_competitor` still describe a decision model that answers through `questions`.

## Risks / Trade-offs

- A forgotten old variable weakens the guard without a message → the owner renames both places at the merge and verifies afterwards that screening is on.
- A plain `evals` run no longer tests a decision model by itself → intended; each run names its candidate.
- The CI summary step or a missing `GUARD_MODEL` variable gives `--model ""`, which skips the rows → acceptable, the skip reason is in the report.

## Eval

The content-guard eval stays as it is: detection rate on 12 injected demo postings and false-positive rate on 30 clean ones (the demo persona). This change moves where the model comes from, not what is measured, so no new data is needed and no paid run is made; tests stub the model client and check the plumbing and the skip reasons.
