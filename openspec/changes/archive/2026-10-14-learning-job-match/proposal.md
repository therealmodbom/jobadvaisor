# Proposal

## Why

Static matching of a profile against posting text misses the criteria a user never wrote down, so it produces both false positives and false negatives. This first change builds the foundation of JobAdvAIsor and its core: a job match that learns those criteria from the user's own ratings.

## What Changes

- A documented, versioned JSON Schema format for the user data repository (profile, policy pack, postings, labels), validated on load, plus a fictional demo persona in that format.
- Posting intake from a link, pasted text or a PDF. Links go through a ladder: the Bundesagentur für Arbeit job-detail interface for that job board's links, structured page data, then a headless browser, then a tool loop that retries, falls back and looks for an alternative source.
- A content guard for posting text, which is untrusted third-party content: structural defenses against prompt injection in every model call, plus screening for injected instructions and dangerous content when a classifier is configured. A flagged posting is excluded from triage until the user releases it.
- A fixed triage graph: deterministic hard exclusions from the policy pack, structured feature extraction, LLM scoring with already-rated postings as few-shot examples, and an exploration slot of deliberately low-scored postings.
- Human-in-the-loop rating: the graph pauses for a batch, the user rates each posting with optional reason chips and free text, and the labels go to the data repository and feed the next run.
- A conversational agent over the same tools as the graph.
- An eval harness: precision@k on time-split held-out labels, a logistic-regression competitor on the extracted features, a hosted decision-model competitor when one is configured, graph-versus-agent comparison, and an eval for every other LLM-backed behavior introduced here.
- A small but polished web UI: intake, a feedback list with score and reasoning, and the agent chat. It is minimal in scope, not in quality. The first version is meant for daily use, because a stopgap UI tends to stay.
- ADRs for the six decisions this change makes (see `design.md`).

## Non-goals

- CV tailoring, cover letters, the full review UI, and job sourcing from mails or portals. Each is a later change.
- The Postgres and pgvector adapter. This change keeps the store interfaces swappable but ships SQLite and Chroma only.
- An importer for any legacy format. The legacy exporter lives outside this repository and writes this app's schema.
- LLM fine-tuning, multi-user operation, authentication, and a hosted demo.
- Any concrete policy rule, profile value or label derived from a real user. Only the mechanism and the demo persona live here.

## Capabilities

### New Capabilities

- `data-repository`: the user data repository format (JSON Schemas per entity), loading with validation, writing labels back, and the demo persona fixture.
- `posting-intake`: turning a link, pasted text or PDF into a stored posting, including the fetch ladder, the retry/fallback tool loop and screening of untrusted posting content.
- `job-triage`: hard exclusions, feature extraction, scoring with retrieved rated examples, and the exploration slot that make up one triage run.
- `rating-feedback`: pausing a triage run for a batch rating, recording ratings with reasons, resuming, and feeding labels into later runs, including cold-start labels supplied by an exporter.
- `job-agent`: the conversational agent that answers questions and runs actions over the shared tools.
- `match-evaluation`: the eval harness and the evals every LLM-backed behavior in this change ships with.
- `web-ui`: the browser UI for intake, rating and the agent chat, small in scope and built for daily use: keyboard-fast rating, visible state at every step, accessible and consistent presentation.

### Modified Capabilities

None. `openspec/specs/` is empty; this change sets the baseline.

## Impact

- New code: a Python backend (FastAPI, LangGraph, LangChain chat models, Playwright, Chroma, SQLite checkpointer, Langfuse tracing, a decision model with Mistral Moderation as fallback for the content guard) and a React + Vite + TypeScript frontend. Repository layout and tooling are set in `design.md`.
- New public contract: the data repository schemas. The external exporter depends on them, so they are versioned and change only deliberately.
- New `.env.example` documenting the data repository location, LLM provider settings (including one API key for an OpenAI-compatible router and the decision model), the content guard's moderation key and Langfuse keys.
- New ADRs in `docs/decisions/` and an updated index.
- CI runs tests and evals against the demo persona only. The real baseline, which compares against the old process on a rated sample of postings it discarded, runs locally against the user's data repository. Its results stay out of this repository.
- Workflow note: execution spans several PRs, one per slice in `tasks.md`. `AGENTS.md` says the change is archived "after its PR merges", so archive comes after the last slice's PR merges.
