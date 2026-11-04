# Tasks

## 1. Guard setting

- [x] 1.1 Rename the settings to `guard_model` and `guard_base_url`, and `llm.decider()` to `guard_model()`; verify `test_llm.py` covers the key, the base-URL fallback and `None` without the setting
- [x] 1.2 Make the guard read `GUARD_MODEL`, then Mistral Moderation, then off, and document that order in `guard.py`; verify `test_guard.py` covers the order and the thresholds per classifier

## 2. Evals take their model from the command line

- [x] 2.1 Add `--model` and `--base-url` to `python -m jobadvaisor.evals` and give `content_guard` and `decider_competitor` the candidate; verify tests for the client pair, the base-URL option, and the skip reason when only `GUARD_MODEL` is set
- [x] 2.2 Make `extractor_benchmark --role decider` require `--model`; verify tests for the named model, the base URL and the usage error with `GUARD_MODEL` set
- [x] 2.3 Pass `--model "$GUARD_MODEL"` in the CI eval job and read the `GUARD_MODEL` variable there; verify the workflow diff

## 3. Names in text

- [x] 3.1 Update `.env.example`, README, ADR 0003 and `docs/extractor-benchmark.md`; verify `test_env_example.py` passes and `git grep DECIDER_` finds nothing outside the archive
- [x] 3.2 Run `uv run pytest` and `uv run ruff check .` in `backend/`; verify both are green
