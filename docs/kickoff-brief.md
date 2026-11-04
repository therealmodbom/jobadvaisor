# Kickoff brief

Status: agreed 2026-10-05. Input for the first `openspec-explore`/`openspec-propose` run. Decisions marked as ADR candidates get their ADR in the change that implements them.

## Goal

A standalone, local-first assistant for a personal job search. It replaces a workflow of a git repository, IDE agents and skill prompts. It also serves as a public AI engineering reference project, so the repository must be publishable from day one.

Single user on localhost. A hosted demo with the demo persona is optional and later. Multi-user SaaS is out of scope.

## Core idea: a learning job match

Static matching (profile and stated preferences compared with the posting text) produces both false positives and false negatives, because many real criteria were never written down. JobAdvAIsor learns them from the user's decisions instead.

- The user always gets a list of postings, including low-scored ones, and rates each one.
- Ratings are stored with optional reason chips (for example "too junior", "wrong domain", "location", "interesting domain") and free text.
- Rated postings become retrieval examples and training data for later scoring.
- No LLM fine-tuning. The data size (tens to a few hundred labels) does not justify it.

## Repositories and data

- **`jobadvaisor` (this repository):** code, OpenSpec, ADRs, demo persona fixture. Private until the data separation is verified, then public.
- **Data repository (private, per user):** a local git repository, remote optional. The app reads and writes it in a documented format, one JSON Schema per entity, validated on load. Entities for the first change: profile, policy pack, postings, labels.
- **Legacy import:** an exporter lives in the user's legacy repository, outside this project. It reads the legacy layout and writes files in this app's schema. The dependency runs one way: the exporter depends on the app's schema, never the reverse. The app has no importer for anyone's legacy format.
- **Demo persona:** a fictional profile in the same schema, used by tests, CI and the demo.

## Stack

- Backend: Python, FastAPI, LangGraph.
- Frontend: React, Vite, TypeScript.
- LLM: provider-agnostic through LangChain chat models, configured per model. OpenAI-compatible routers work through `base_url`.
- Local stores: SQLite for LangGraph checkpoints, Chroma as the vector index. Both are rebuildable. The data repository is the source of truth.
- Later: Postgres (local Docker or an external database such as Supabase) as a second adapter for both stores behind the same interfaces, switched by connection URL: LangGraph's Postgres checkpointer for checkpoints, pgvector for the vector index.
- Tracing: Langfuse.

## First change: foundation and learning job match

- **Intake:** link, pasted text or PDF. Pages are fetched with a headless browser (Playwright), because plain HTTP fetches of job pages are unreliable. Intake is a ReAct tool loop: retry, fall back, look for an alternative source.
- **Triage graph** (fixed skeleton):
  1. Hard exclusions, deterministic, evaluated from rules in the user's policy pack. The rules themselves live only in the data repository.
  2. Structured feature extraction: role type, seniority, domain, tech stack, location, remote, company stage. The feature set is configurable per user.
  3. Scoring: LLM judge with retrieved, already rated postings as few-shot examples, including the user's reasons.
  4. Exploration slot: about 20 % of each list are deliberately low-scored postings, so the system does not only confirm itself.
- **Human in the loop:** LangGraph `interrupt()`, persisted through the SQLite checkpointer. The user rates a batch asynchronously. Labels go to the data repository and feed the next run.
- **Conversational agent:** a free ReAct agent over the same tools, for questions like "why was X rejected", "find more like Y", "rescore this batch with my new feedback".
- **Tools over prompts:** each capability is a tool usable by both the graph and the agent (`fetch_posting`, `check_exclusions`, `extract_features`, `find_similar_labeled`, `score_posting`, `research_company`).
- **Cold-start labels** (supplied by the exporter):
  - Postings the user confirms as interesting: positive.
  - Postings the user rejected, with a reason: negative.
  - Imported records the exporter marks as not reflecting preference: excluded, never positive.
  - Unrated leads and postings the old process discarded: unlabeled, rated once through the feedback UI.
- **Eval harness in this change:** precision@k on time-split held-out labels. Baseline is the old process, measured on a rated sample of the postings it discarded. From about 100 labels, a logistic regression on the extracted features competes with the LLM judge. A second eval compares triage as fixed graph against triage as free agent with the same tools (precision@k, cost, variance).
- **UI:** intake, feedback list with score and reasoning. Small in scope, but user-friendly and good-looking from the first version, because a stopgap UI tends to stay.

## Guiding principle

The mechanism is chosen per rule and case: prompt, retrieval, graph node, guardrail or decision model. Each choice is recorded (ADR or `design.md`) and backed by an eval. Start small, move rules over one at a time.

## Later changes

Each is its own OpenSpec change:

1. CV tailoring, with PDF rendering through JSON Resume themes.
2. Cover letter, with quality check and tone-of-voice rules.
3. Review UI: Markdown editor, preview, PDF view, diff between versions.
4. Sourcing from job alert mails and portals, including the Bundesagentur für Arbeit job search interface.
5. Postgres adapter for LangGraph checkpoints and the vector index (pgvector), local Docker or Supabase.

## ADR candidates

- Git repository as the user data store
- Legacy exporter outside the app
- Provider-agnostic LLM access through LangChain
- SQLite and Chroma locally, Postgres (checkpoints and pgvector) as the later adapter (low entry barrier, no Docker needed)
- Hybrid agent design: fixed triage graph with ReAct nodes, plus a free conversational agent over the same tools

## Process

- OpenSpec plans (explore when needed, then propose), Superpowers executes (TDD, worktree per branch), archive after merge. See `AGENTS.md`.
- Milestone gate after every change: the next one starts only on an explicit decision.
