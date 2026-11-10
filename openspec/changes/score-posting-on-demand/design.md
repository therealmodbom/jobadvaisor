# Design

## Context

See proposal.md for why. Today a score is written only by the pass's `store_scores` node (`triage/graph.py`); the pass's `load` takes only postings without a verdict (`pool.pass_batch`). The judge (`tools/scoring.score_posting`) reads posting, profile, policy pack and examples; it never reads the extracted features, and the stored `Score` does not hold them. `Runs` (`triage/runs.py`) computes one pass at a time and raises `RunBusyError` for a second one. The correction counter (`pool.counter`) compares every `rating` label since the last pass's start with the posting's current score, whoever wrote it.

## Goals / Non-Goals

**Goals:**
- One scoring path shared by pass and single score, so both send the judge the same input.
- A single score and a pass never write at the same time.

**Non-Goals:**
- A run model, progress polling or checkpoints for single scores.
- A cost figure computed from the configured judge model.

## Decisions

**Shared scoring step.** The pass's `score` node and the single score both call one function that takes the context and a posting ID, fetches the posting's similar rated postings (its own ID excluded) and calls the judge. The index is synced once per pass and once per single score, before that call. Alternative: a one-posting pass through the graph. Rejected: it would take its batch from `pass_batch`, which drops rated postings, and record a pass, which resets the counter's window.

**No extraction.** The single score skips the extractor: the judge does not read features, so the score is the same without it and costs one call instead of two.

**Same gates as the pool.** The single score refuses a posting the exclusion rules match (`check_exclusions`) and applies `_guard_ruling`: a held posting is refused; an unchecked one is checked now when a classifier is configured, else refused; a checked one keeps its stored result, so a re-score does not call the guard again. The pool shows no score for excluded or held rows, so a score computed for them would be invisible there. The UI disables the button for these postings before any click: pool rows already carry `state` `excluded` or `held`; for the unchecked case each row gains `unscreened` (the posting has no guard result), and `GET /pool` and `GET /postings/{id}` gain `screening` (a classifier is configured, `guard.classifier is not None`, as the intake answer already reports it). Beside a disabled button sits a visible info icon (lucide `Info`, already a dependency), focusable, with the reason in a small popover shown on hover and focus (Tailwind `group-hover`/`group-focus-within`, no tooltip library) and linked by `aria-describedby`.

**Synchronous, in the pass's slot.** `Runs` gets a method that computes a single score in the calling thread while holding the same `_computing` slot a pass holds (key `score:<posting_id>`). A pass started meanwhile gets `RunBusyError`, and a single score requested during a pass gets it too. The API route is a sync FastAPI route, so it blocks a worker thread for one judge call and nothing else. Alternatives: a separate lock (the two would not see each other), or submitting to the pass executor and waiting (same effect, more code).

**API.** `POST /postings/{id}/score`, no body. 200 answers the `GET /postings/{id}` body plus `counter` and `next_pass`, so the page replaces its data and the pool updates its row and counter from one answer. Errors in the `{error, detail}` shape: 404 unknown posting; 409 with `error` `scoring in progress`, `excluded` (detail names the rules), `held` or `unscreened`; 502 `scoring failed` when the judge fails. The UI maps each `error` to its own German message.

**Counter.** It stays as is: a score from the button counts like a pass's score, since the posting's own rating never reaches its judge (`find_similar_labeled` skips its ID). No pass is appended, so the window does not move. `store_scores`'s docstring argument that a pass never rescores rated postings stays true for the pass itself.

**UI.** One hook for the call's state (idle, computing, failed with a message), used by the posting page and by each pool row, and one button component that shows "Score berechnen" or "Neu berechnen", the cost line "1 KI-Aufruf, etwa 0,0003 $ mit dem Demo-Modell" and the computing state. Disabled cases as above. The pool takes the answer's row but keeps its own `exploration` flag, since the posting page's row always carries `false`. The posting page keeps the old score visible, marked "wird neu berechnet", while computing. The hint for a rated posting without a score replaces the pass hint only for rows with a verdict.

**Docstring fix.** `start_pass`'s docstring says rated postings are rescored after a correction; `pass_batch` and the spec say unrated ones. The docstring is corrected.

**Eval.** No new LLM-backed behavior: the single score sends the judge the same input through the same shared step a pass uses, which the scoring eval (`evals/scoring.py`, precision@k on labels held out by time, demo persona) measures. No eval run is needed for this change.

## Risks / Trade-offs

- [A slow judge holds the request open] → the button shows progress; a proxy timeout shows as a failure with retry. Background runs come only if this proves annoying.
- [The cost line is fixed text for the demo model] → `ponytail:` comment at the constant; derive it from the configured model when another judge becomes the default.
- [The first single score after many new ratings embeds them all] → the same happens at a pass's start; embedding costs are small next to a judge call.
- [Two rows pressed quickly] → the second gets `scoring in progress` and its row says so, with retry.
- [An unchecked posting stays unscorable without a classifier] → the info icon says so; the pass's unscreened question remains the path for unrated ones.
