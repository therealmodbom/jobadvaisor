# Proposal

## Why

`DECIDER_MODEL` names a model type, but the app uses it for one task: the content guard's classifier. The same setting also chose the competitor in the scoring and extraction evals, so swapping the guard model silently changed what those evals tested. Issue #52 (Name model settings after their task) is the first step of #55 (Evaluation architecture): models per task, taken from the configuration or from the command line.

## What Changes

- **BREAKING**: `GUARD_MODEL` and `GUARD_BASE_URL` replace `DECIDER_MODEL` and `DECIDER_BASE_URL`. The old names are not read any more and nothing warns about them.
- The content guard picks its classifier in a documented order: `GUARD_MODEL`, then Mistral Moderation (`MISTRAL_API_KEY`), then off. It still fails closed.
- `python -m jobadvaisor.evals` gets `--model` and `--base-url`: the decision model that the `decider_competitor` eval and the decision-model row of the `content_guard` eval test. Without `--model` those rows are skipped with that reason.
- `extractor_benchmark --role decider` requires `--model`; it no longer reads a setting.
- The CI eval job passes `--model "$GUARD_MODEL"`, so the guard row tests the model the app runs.
- `.env.example`, README, ADR 0003, `docs/extractor-benchmark.md` and the CI variable use the new names.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `match-evaluation`: the decision-model competitor and the decision-model benchmark subject are named for the run, not taken from a configured setting.

## Non-Goals

- One eval contract, a run history and DeepEval (rest of #55, #34 Move the existing evals onto DeepEval, #33 Recurring benchmark).
- A chat-format safety model behind its own setting (#50).
- Comparing Jev 1.14 with 1.13 for the guard (#51, Content guard: larger eval data).
- Renaming code that still describes its subject: `Decider`, `evals/decider.py`, `--role decider`, the eval name `decider_competitor`.
- A startup check or warning for a leftover `DECIDER_MODEL`; the rename on the owner's machine and in CI is done together with the merge.

## Impact

- `backend/jobadvaisor`: `settings.py`, `llm.py`, `guard.py`, `evals/__main__.py`, `evals/decider.py`, `evals/extractor_benchmark.py`.
- `.env.example`, `README.md`, `docs/decisions/0003-provider-agnostic-llm-access-through-langchain.md`, `docs/extractor-benchmark.md`, `.github/workflows/ci.yml`.
- Deployment: `local.env` and the Actions variable change their name; a stale `DECIDER_MODEL` turns the guard to Mistral or off without a message.
