# 0013. Pass progress and cancel kept in memory, beside the checkpoint

## Status

Accepted, 2026-11-19.

## Context

A scoring pass is a LangGraph graph run in a background thread and checkpointed in SQLite. Its nodes `exclude` and `score` each loop over the whole batch, and the state reaches the checkpoint only when a node ends. A poll therefore cannot see a single posting finish, and nothing can stop the loop. #18 (Cancel button and per-posting progress for a running scoring pass) asks for both: progress after every posting, and a cooperative cancel checked between postings.

## Decision

The pass keeps its nodes and their loops. It reports through two hooks it gets with its runtime context: a progress callback, called after every posting, and a cancel check, asked before every posting. The run manager holds both per run in memory. It merges the progress into the pass state it reports, and it sets the cancel flag when the user cancels. A node that sees the flag stops its loop and writes `cancelled` into the state, so the checkpoint still knows how the run ended.

## Alternatives considered

- **One checkpointed graph step per posting** (a node that handles one posting and loops back to itself). Progress would then be the checkpoint itself and would survive a restart, which would open the way to resuming a pass without redoing paid calls. It was rejected for two reasons. First, the SQLite saver stores the whole state in every checkpoint, and `results` holds every posting's result with the judge's reasoning, so a pass over N postings writes on the order of N² posting results: tens of megabytes for a full pass over a few hundred postings, growing with the square of the pool. Second, resuming is not wanted now, and a restart already ends a running pass as `failed`. Fanning the postings out with `Send` instead of a loop would run them concurrently, which belongs to the bounded concurrency of #81 (Scoring pass: phases and progress, and bounded concurrency after measuring), not to this decision.
- **LangGraph custom stream events**, consumed by the run manager while the UI keeps polling. They would carry the progress, but not the cancel: a running node can only learn of a cancel through something it is handed, so the cancel needs a context hook anyway. Progress takes the same path, which keeps one mechanism instead of two.

## Consequences

- A restart loses the live progress, as it already loses the running pass. The checkpoint still holds the results of the last finished node.
- The hooks have defaults that report nothing and never cancel. The evals and the tests that build a context directly keep working unchanged.
- If resuming after a restart is wanted later, the per-posting step becomes worth reconsidering, together with a state layout that does not copy every result into every checkpoint.
