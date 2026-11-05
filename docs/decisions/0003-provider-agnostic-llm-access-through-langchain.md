# 0003. Provider-agnostic LLM access through LangChain

## Status

Accepted, 2026-10-05. Amended 2026-10-10: decision models are the one exception to LangChain access (last paragraph of the Decision). Amended 2026-10-11: the decision model is the default content-guard classifier.

## Context

The app uses language models in several roles: feature extraction, scoring as a judge, intake and a conversational agent. Each role may suit a different model, and the best choice changes over time. Users may run models through an OpenAI-compatible router. The evals need to compare models and pin the model used per role.

## Decision

All model access goes through LangChain. `init_chat_model` builds one chat model per role (`extractor`, `judge`, `intake`, `agent`). Each role reads `<ROLE>_MODEL` and an optional `<ROLE>_BASE_URL`, with `LLM_MODEL` and `LLM_BASE_URL` as the default for every role. Embeddings use `init_embeddings` with `EMBEDDING_MODEL`. Structured results use `with_structured_output` against Pydantic models. Routers work through `base_url`.

Decision models, which return probabilities per option instead of text, are the one exception: LangChain has no binding for their request format, so the `decider` role calls the OpenAI-compatible chat-completions endpoint directly. It stays provider-agnostic in the same way. The app uses one only as the content guard's classifier, configured by `GUARD_MODEL` and an optional `GUARD_BASE_URL` and called in the `questions` format; the guard falls back to Mistral Moderation, then to off. Everywhere else a decision model is an eval competitor that each run names with `--model`, never from a setting.

## Alternatives considered

No alternative was weighed explicitly. This decision implies rejecting the obvious one:

- **One provider's SDK, called directly.** It would be thinner, but would lock the app and its evals to one vendor and make a per-role model choice a code change.

## Consequences

- A role's model changes through configuration, not code. Evals can compare providers on the same task.
- LangChain models plug directly into LangGraph, which the triage graph uses (see [ADR 0005](0005-hybrid-agent-design.md)).
- The app carries LangChain as a dependency and follows its release churn. Provider-specific features are available only as far as LangChain exposes them.
- Each LangChain provider package reads its own API key (for example `OPENAI_API_KEY`) from the process environment. These keys are documented as a comment in `.env.example`, not as settings fields, and the app's settings do not pass `.env` entries on to the environment. `LLM_API_KEY`, when set, is passed to every model client instead, so a router such as Requesty works with one key from `.env` (task 3.1).
