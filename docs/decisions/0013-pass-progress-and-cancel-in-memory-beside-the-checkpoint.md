# 0013. Pass progress and cancel kept in memory, beside the checkpoint

## Status

Accepted, 2026-11-19.

## Context

A scoring pass is a LangGraph graph run in a background thread and checkpointed in SQLite. Its nodes `extract` and `score` each loop over the whole batch, and the state reaches the checkpoint only when a node ends. A poll therefore cannot see a single posting finish, and nothing can stop the loop. #18 (Cancel button and per-posting progress for a running scoring pass) asks for both: progress after every posting, and a cooperative cancel checked between postings.

## Decision

The pass keeps its nodes and their loops. It reports through two hooks it gets with its runtime context: a progress callback, called after every posting, and a cancel check, asked before every posting. The run manager holds both per run in memory. It merges the progress into the pass state it reports, and it sets the cancel flag when the user cancels. A node that sees the flag stops its loop and writes `cancelled` into the state, so the checkpoint still knows how the run ended.

## Alternatives considered

- **One checkpointed graph step per posting** (a node that handles one posting and loops back to itself). Progress would then be the checkpoint itself and would survive a restart, which would open the way to resuming a pass without redoing paid calls. It was rejected for three reasons. First, the SQLite saver stores the whole state in every checkpoint, and `results` holds the features of every posting, so a pass over N postings writes on the order of N² posting results: hundreds of megabytes for a full pass over a few hundred postings. Second, every posting becomes one graph step, so a large pass exceeds LangGraph's default recursion limit of 25 unless every invocation raises it. Third, resuming is not wanted now, and a restart already ends a running pass as `failed`.
- **LangGraph custom stream events.** They report progress as it happens, but only to a caller that consumes the stream. The web UI polls, and a push channel to it is out of scope.

## Consequences

- A restart loses the live progress, as it already loses the running pass. The checkpoint still holds the results of the last finished node.
- The hooks have defaults that report nothing and never cancel. The evals and the tests that build a context directly keep working unchanged.
- If resuming after a restart is wanted later, the per-posting step becomes worth reconsidering, together with a state layout that does not copy every result into every checkpoint.
