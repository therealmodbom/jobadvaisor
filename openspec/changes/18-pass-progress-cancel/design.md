# Design

## Context

On `main` a pass is the triage graph `load → exclude → [confirm_unscreened] → extract → score → store_scores` (`triage/graph.py`). It runs on `Runs`' one-worker executor (`triage/runs.py`) and is checkpointed in SQLite. `extract` and `score` each loop over the whole batch and return `results` only when the loop ends. `GET /pool/passes/{id}` (`api/app.py` `read_pass`) derives `total` and `done` from the snapshot's `results`, so it cannot move during a loop. It also counts excluded and held postings as done from the first step on (proposal → Why).

`extract` reads features that nothing in the pass uses: `score_posting` gets the posting, the profile, the policy pack and the examples, and `Score` has no field for features (proposal → Why).

`exclude` can call the content guard's classifier once per unchecked posting, so checking is a per-posting loop too. `store_scores` reads the scores from before the pass for the quality measure, writes every score, and appends a `PoolPass` only when it scored anything.

`AlertRuns` (`intake/alert_runs.py`) is the sibling background job. It keeps its progress in memory per run and updates it after every entry. This design follows that pattern.

The look of the progress and the cancel button is drawn in the Design artifact [Scoren: Fortschritt und Abbrechen (#18)](https://claude.ai/artifact/KkptMQDoopiQTJF77qLUQT) on the „JobAdvAIsor Design System“. Its boards A (desktop, every state, phone) hold the chosen design. Two earlier rounds of A drew the progress as a band below the pass button, first with four steps and then with three. After the owner's review on 2026-11-19 everything moved into the row of the pass button, and the pass button itself became the cancel button. Boards B keep the variant that was not chosen.

## Goals / Non-Goals

**Goals:**
- Progress and the cancel check reach every per-posting loop of the pass. The pass makes one model call per scored posting.
- A cancelled pass ends in a state the checkpoint knows, not only the process.
- The progress shape is generic enough for #90 (Global progress indicator for running background jobs) to read later.

**Non-Goals:**
- No change to which postings a pass scores, to the judge's input, or to the single score.
- No stored features (#126 (Extract features once per posting and store them)).
- No new dependency.

## Decisions

- **The pass does not read features.** The node `extract` goes, and the graph is `load → exclude → [confirm_unscreened] → score → store_scores`. `_after_exclude` and `_after_confirm` route to `score`. `TriageContext` loses `extractor`, and `api/app.py` stops building the extractor model for a pass. The extractor stays for the agent's tool and the evals. Alternative: keep the extraction and run it per posting right before its score. Rejected, because it still pays a call whose result is dropped; #126 brings the extraction back once something reads it, and stores it.
  - `extract` held the second guard ruling, which a paused pass needs after it resumes: the posting may have been flagged, or screening turned on, while the question waited. `score` takes it over unchanged. Before judging a pending posting it asks `_guard_ruling` again. A ruling other than `unscreened` for a posting the user continued with replaces the posting's result, and no model call is made for it.
  - `results` entries of status `scored` hold `score`, `reasoning` and `example_ids`, no `features`. `TriageState` does not carry `extract_failed`.
  - A checkpoint written before the deploy whose next node is `extract` (a pass the restart ended mid-extraction) has no matching node in the new graph. `_status` must still report it `failed`, not `done`. A test builds such a checkpoint with a graph that still has the node, reads it with the new graph, and pins the status. When `snapshot.next` comes back empty for it, `_status` reports `failed` whenever `results` still holds a `pending` or `extracted` entry.
  - A pass paused at the unscreened question before the deploy resumes into `score`, because `confirm_unscreened` and its routing keep their names.

- **Progress and cancel live in memory, beside the checkpoint.** The reasons and the rejected per-posting checkpoint step are in [ADR 0013](../../../docs/decisions/0013-pass-progress-and-cancel-in-memory-beside-the-checkpoint.md).

- **Two hooks on `TriageContext`.** `progress: Callable[[dict], None]` gets the pass's progress after every posting and at every phase start. `cancelled: Callable[[], bool]` answers whether the user asked to stop. Both are dataclass fields with defaults (report nothing, never cancel), so `score_one`, the eval `graph_vs_agent` and the tests keep building the context as they do. `Runs` wraps the context from its factory with `dataclasses.replace(context, progress=..., cancelled=...)` for both `start` and `answer_unscreened`, since a resumed pass needs the same hooks. Alternative: a module-level registry keyed by the run ID, read by the nodes. Rejected, because the nodes would need the run ID from the config and the registry would be hidden global state, while the context is already the place for runtime-only inputs.

- **The progress shape.** It is `{"phase", "score": {"done", "total"}}`, with `phase` one of `checking`, `scoring` and `storing`.
  - `load` and `exclude` report `checking`, `score` reports `scoring`, and `store_scores` reports `storing` when it has something to store.
  - `score` is `null` while the phase is `checking`. From the start of `score` on it always holds numbers, and `storing` keeps the final values.
  - `score.total` is the number of pending postings when `score` starts. It drops by one whenever the second guard ruling gives a posting a result other than a model call. `score.done` counts every posting scored or failed.
  - Excluded and held postings never enter the count. A failure is not reported in the progress; the posting keeps no new score.
  - Alternative: derive the count in `read_pass` from `results`. Rejected, because `results` reaches the snapshot only when a node ends, which is the bug this change fixes.

- **Cancel is a flag checked before every posting.** `exclude` and `score` ask `cancelled()` before each posting. A node that sees it stops its loop and returns its results so far, with `cancelled: True` in the state. `TriageState` gains `cancelled: bool`, named in its docstring, because LangGraph silently drops a key the state schema does not declare.
  - A pass cancelled in `exclude` goes to `END` through a new branch in `_after_exclude`. It asks no unscreened question and scores nothing.
  - A cancel can still land after `exclude`'s last check, while the graph is on its way to the unscreened interrupt. `Runs` closes that gap after the step, not inside the graph (see `Runs.cancel` below). `confirm_unscreened` accepts a third answer, `"cancel"`, besides `True` and `False`, and returns `cancelled: True`, so `_after_confirm` routes it to `END`.
  - `store_scores` stores what was scored and never asks the flag. A cancel that arrives while storing, or during the last posting of `score`, therefore ends as a complete pass (spec → Cancel while storing).
  - The postings the pass did not reach: `exclude` leaves them out of `results`, since it builds `results` from scratch, and `score` leaves them `pending`. Nothing is written for them.
  - Alternative: check only between phases. Rejected, because one phase of a large pass takes many minutes.

- **The status `cancelled`, not `aborted`.** `Runs._status` reports `cancelled` when the run has no next node and its state says `cancelled`. `aborted` keeps its meaning: the unscreened question was answered with abort, and nothing was stored. Alternative: reuse `aborted`. Rejected, because a cancelled pass may have stored scores, so the view must reload the pool and report a count, which it does not do for `aborted`.

- **`Runs.cancel(run_id)`.**
  - It raises `KeyError` for an ID that names a single score (prefix `score:`, which sits in `_computing` while it runs) or that `read()` does not know.
  - It raises `RunStateError` unless the run is computing.
  - Any pass ID the checkpoint knows is accepted on these terms, also one from before a restart. Such a pass is `awaiting_answer` or ended, so it gets the 409, not a 404.
  - The check and the add happen in one lock section. The context's `cancelled` hook reads the set of cancelled IDs, and `read()` reports `cancel_requested` while the run computes and its ID is in that set.
  - When a step ends (`_run`), `Runs` takes the lock and, in that one section, reads the snapshot and decides. Either it frees the slot and drops the ID from the set, or, when the step ended paused at the unscreened question while the ID is in the set, it keeps the slot and leaves the lock to resume the run with `Command(resume="cancel")`. The resumed step ends the pass `cancelled`. It is tried once: if it fails (the context factory cannot load the data repository, say), its end section frees the slot and `_errors` keeps the reason, instead of resuming again and again.
  - Since `cancel` checks `_computing` and adds the ID under the same lock, there is no gap between the decision and the release. A cancel that arrives before the section is seen there and resumed. One that arrives after it finds the slot free and gets the 409 for a pass that waits for the answer. Either way no 202 is lost.
  - The ID also leaves the set when a step claims the slot (`_claim`, in the same lock section that adds it to `_computing`, so a cancel arriving right after is never discarded), so an earlier request never carries over into a step resumed with „Trotzdem scoren“.
  - Alternative: clear the flag when the step ends and rely on the graph's checks alone. Rejected, because a cancel that arrives between the last check and the interrupt would answer 202 and then be lost.

- **API.** `POST /pool/passes/{id}/cancel` answers 202 `{pass_id}`, 404 `not found` for an unknown pass (a single score's `score:<id>` included, even while it computes), and 409 `pass not running` for a known pass that waits for the unscreened answer or has ended, before or after a restart. `GET /pool/passes/{id}` answers `{pass_id, status, started_at, error, progress, cancel_requested, scored, unscreened}`.
  - `progress` is the last reported progress, or `null` when this process holds none: before the first report, or after a restart.
  - `scored` counts the results with status `scored`. When a cancelled pass has ended, that is the number it stored.
  - `total` and `done` go away. The web UI is the only client.

- **The pass record.** `PoolPass` gets `cancelled: Literal[True] | None = None`, and `store_scores` sets it when the state says `cancelled`. The writer drops `None`, so the record of a pass that was not cancelled stays byte for byte as today. `counter` starts its window at the last pass whose variant is `"all"` or `None` and that is not cancelled. `schemas/pool.schema.json` is generated again. Alternative: `cancelled: bool = False`. Rejected, because `False` would be written into every new record, and the previous image, which forbids unknown fields, could then not read any pass recorded after the deploy. Alternative: a third `variant` value. Rejected, because the variant names what the pass set out to score, and `counter` treats a missing variant as „all“.

- **The view.**
  - `usePass` treats `cancelled` like `done`: it clears the stored pass, reloads the pool through `onDone`, and shows „Das Scoren wurde abgebrochen. N Anzeigen haben einen neuen Score.“ (with „1 Anzeige hat“ and „Keine Anzeige hat“). The text sits in the status region where „Das Scoren wurde abgebrochen.“ sits today, not in the `role="alert"` error box, and it clears when the next pass starts.
  - **Everything stays in the row of the pass button.** While a pass computes (`working`, including storing, not while it asks the unscreened question), the split button gives way to one outline button „Scoren abbrechen“ of exactly its width. Both share one grid cell: the split button stays in the layout, `invisible` and out of the tab order, and reserves the width, so the progress block and the counter do not move sideways when a pass starts or ends. The cost line under the split button is not shown while the cancel button is.
  - **The progress block** sits right of the button, before the correction counter, with a fixed width of 340 px from `sm` and the full width below. It has three lines of fixed height: a head line (one line, 24 px) with the loader and „Scoren läuft: Anzeigen prüfen…“, „Scoren läuft: x von y“ or „Scores werden gespeichert“; a `<progress>` bar (empty while checking and while `progress` is `null`, `done`/`total` while scoring, full while storing) on a track in the border colour, so the empty bar stays visible on the page background; and a hint line of two lines' height whose text changes with the state: the default hint, „Wird nach der aktuellen Anzeige beendet.“ after a cancel request, or „Das Speichern lässt sich nicht mehr abbrechen.“ while storing. The block therefore keeps one height at every width and in every phase. The row may change height when a pass starts or ends, not from one phase to the next. The e2e walkthrough measures the row in all four running states (checking, scoring, cancel requested, storing) at 360, 390, 640, 768, 1024 and 1280 px.
  - **The cancel button.** A press sends `POST …/cancel`. On the 202 the hook sets a separate `cancelling` flag, kept until the next `start`, so the button is inert at once and not only after the next poll. Patching `cancel_requested` on the local pass state would not hold: a poll already in flight when the 202 arrives answers without it and overwrites the patch. While `cancelling` or the polled `cancel_requested` is set, the button reads „Wird beendet…“ in the muted foreground colour. While storing it keeps its label „Scoren abbrechen“ and is inert too. In both states it is `aria-disabled`, with a guard in its click handler, instead of `disabled`, so it keeps keyboard focus, `aria-describedby` points at the hint line that gives the reason, and a further Enter does not fall through to the pool's shortcuts. The reason is visible text beside the button, so it needs no info icon.
  - **No double press.** After each swap (split button to cancel button when a pass starts, cancel button back to split button when it ends) the button that appeared ignores presses for 1 s. It is `aria-disabled` for that second, with the guard in its click handler. When the button that went away had focus, focus moves to the one that took its place, so a held Enter or a double click lands on an inert button instead of the page. This covers both slips the swap invites: a double click on start that would cancel the pass at once, and a cancel click that lands just as the pass ends and would start a new, paid pass. The confirm step stays out, as decided for the cancel.
  - The cancel request passes `send` an empty conflict text. A 409 means the pass ended or paused in between, and the next poll shows that. Any other failure shows „Das Scoren konnte nicht abgebrochen werden. Versuch es noch einmal.“
  - The cancel button needs no entry in the pool view's keyboard-shortcut exclusion. That list holds text fields and menus, and Enter on any button already keeps its own meaning. A view test pins that Enter on the focused cancel button cancels and does not jump to the next row.
  - The live region keeps text that does not change per poll. It announces the cancel request and the result once, not every count.
  - The cost line says „je ein Modellaufruf“, since a pass now calls the model once per posting.
  - Texts and placement follow the Design artifact.

- **Eval.** No eval runs. The judge gets the same input as before, and the change only drops a call whose result nothing read, and adds a check and a report between the judge's calls.

- **Tests.**
  - Graph tests use fake models that record their calls. A cancel test uses a fake whose call sets the cancel flag on the n-th posting, so the order is fixed without `sleep`. A test pins that a pass makes no extraction call.
  - `Runs` and API tests use a fake model that blocks on a `threading.Event`, then cancel and release.
  - The progress test records every `progress` call and checks the count after each posting, including an excluded posting, a held posting, a posting flagged while the question waited, and a failed score.
  - The e2e walkthrough's scripted callable waits on a `threading.Event` the test releases, so the count can be seen moving before the pass ends, and a cancel lands mid-pass.
  - View tests pin the swap delay with fake timers: a second press within 1 s of the start sends no cancel, and a press within 1 s of the end starts no pass.

## Risks / Trade-offs

- [A model call in flight cannot be interrupted, so a slow call delays the stop] → `cancel_requested` makes the view say the pass stops after the current posting, so the wait is explained.
- [A restart loses the live progress] → a restart already ends the running pass as `failed`, and the view shows that.
- [The progress callback runs on the pass thread while `read()` runs on a request thread] → `Runs` stores each report under its lock as a fresh copy, as `AlertRuns` does.
- [A posting whose score fails is not named in the progress] → it keeps no new score, which the ranking shows; a failure count waits until someone asks for it.
- [Overlap with other work on `PoolView.tsx` or `triage/graph.py`] → run the parallel-work check before the PR, and bring `origin/main` in with `git merge`.

## Migration Plan

Deploy as usual. Existing `pool.json` files stay valid, and the counter shows the same figures, since no stored record is cancelled. A pass the deploy's restart ended reads as `failed`, as before, also when it ended in the old `extract` node (Decisions → The pass does not read features). Rollback: the previous image rejects unknown fields, so a rollback after a cancelled pass was recorded also needs that record's `cancelled` field removed from `pool.json` in the data repository, for example by reverting that commit there.
