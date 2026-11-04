# 0005. Hybrid agent design: fixed triage graph plus a free agent over the same tools

## Status

Accepted, 2026-10-05. Partly superseded by the change `rated-pool`: the pass no longer pauses for ratings and ends in `store_scores`, and the exploration pick is a mark in the pool.

## Context

Triage has to be reproducible, cheap per posting and measurable: hard exclusions before any model call, then extraction, scoring and the exploration pick, then a pause for ratings. Other steps are open-ended, such as finding a posting's text during intake when the first fetch fails. Users also ask free-form questions ("why was this rejected", "find more like this one", "rescore this batch").

## Decision

Triage is a fixed LangGraph `StateGraph`: `load` → `exclude` → `extract` → `score` → `select` → `await_ratings` → `write_labels`. Open-ended steps outside the graph, such as the intake loop behind `fetch_posting`, are bounded ReAct agents. Free-form questions go to a separate conversational ReAct agent. Graph and agent share one set of tools (`fetch_posting`, `check_exclusions`, `extract_features`, `find_similar_labeled`, `score_posting`, `research_company`). The agent gets no label-writing tool.

The fixed graph is the skeleton, not a ban on loops. A node may later become a bounded ReAct loop where a single pass is not enough, for example scoring that gathers more evidence and weighs it before deciding. Each such step follows the kickoff brief's guiding principle: the mechanism is chosen per case and backed by an eval result. The first change ships the graph without such a node.

## Alternatives considered

- **Triage as one free agent** over the same tools. Not rejected on principle: the graph-versus-agent eval compares both on precision@k, cost per posting and variance across repetitions. The fixed graph is the default until that eval says otherwise.

## Consequences

- Exclusions run deterministically before any model call, and the exploration pick is reproducible from its stored seed. Model calls are not. `interrupt()` and checkpoints fit naturally into the graph.
- Shared tools mean graph and agent cannot drift apart in behavior, and each tool has one eval.
- The agent cannot change labels silently, because no tool lets it write them.
- Two orchestration styles must be maintained and evaluated separately.
- The decision is revisited when the graph-versus-agent eval reports, and per node whenever a step is proposed as a ReAct loop.
