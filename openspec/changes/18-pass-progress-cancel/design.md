# Design

## Context

A pass is the triage graph `load → exclude → [confirm_unscreened] → extract → score → store_scores` (`triage/graph.py`). It runs on `Runs`' one-worker executor (`triage/runs.py`) and is checkpointed in SQLite. `extract` and `score` each loop over the whole batch and return `results` only when the loop ends. `GET /pool/passes/{id}` (`api/app.py` `read_pass`) derives `total` and `done` from the snapshot's `results`, so it cannot move during a loop. It also counts excluded and held postings as done from the first step on (proposal → Why).

`exclude` can call the content guard's classifier once per unchecked posting, so checking is a per-posting loop too. `store_scores` reads the scores from before the pass for the quality measure, writes every score, and appends a `PoolPass` only when it scored anything.

`AlertRuns` (`intake/alert_runs.py`) is the sibling background job. It keeps its progress in memory per run and updates it after every entry. This design follows that pattern.

The look of the progress line and the cancel button is drawn in the Design artifact [Scoren: Fortschritt und Abbrechen (#18)](https://claude.ai/artifact/KkptMQDoopiQTJF77qLUQT) on the „JobAdvAIsor Design System“. It has two variants, each on desktop, as a sheet of every state, and on a phone:
- **A:** the phases as four steps with a bar for the current one, and the cancel button inside the progress band.
- **B:** one line with both counts, and the cancel button in place of the pass button while the pass runs.

The owner chose A on 2026-11-19 (task 0.1), with one condition: the band keeps its size in every phase. The boards of A were redrawn to that rule (see Decisions → The view).

## Goals / Non-Goals

**Goals:**
- Progress and the cancel check reach every per-posting loop of the pass without adding nodes. The only wiring change is one more branch after `exclude`.
- A cancelled pass ends in a state the checkpoint knows, not only the process.
- The progress shape is generic enough for #90 (Global progress indicator for running background jobs) to read later.

**Non-Goals:**
- No change to what a pass scores, to the order of its calls, or to the single score.
- No new dependency.

## Decisions

- **Progress and cancel live in memory, beside the checkpoint.** The reasons and the rejected per-posting checkpoint step are in [ADR 0013](../../../docs/decisions/0013-pass-progress-and-cancel-in-memory-beside-the-checkpoint.md).

- **Two hooks on `TriageContext`.** `progress: Callable[[dict], None]` gets the pass's progress after every posting and at every phase start. `cancelled: Callable[[], bool]` answers whether the user asked to stop. Both are dataclass fields with defaults (report nothing, never cancel), so `score_one`, the eval `graph_vs_agent` and the tests keep building the context as they do. `Runs` wraps the context from its factory with `dataclasses.replace(context, progress=..., cancelled=...)` for both `start` and `answer_unscreened`, since a resumed pass needs the same hooks. Alternative: a module-level registry keyed by the run ID, read by the nodes. Rejected, because the nodes would need the run ID from the config and the registry would be hidden global state, while the context is already the place for runtime-only inputs.

- **The progress shape.** It is `{"phase", "extract": {"done", "total"}, "score": {"done", "total"}}`, with `phase` one of `checking`, `extracting`, `scoring` and `storing`.
  - `load` and `exclude` report `checking`, `extract` reports `extracting`, `score` reports `scoring`, and `store_scores` reports `storing`.
  - `extract` and `score` are `null` while the phase is `checking`. From the start of `extract` on they always hold numbers, and `storing` keeps their final values.
  - `extract.total` is the number of pending postings when `extract` starts. It drops by one whenever `extract`'s second guard ruling gives a posting a result other than a model call: excluded, or `unscreened` for a posting the user did not continue with. `extract.done` counts every posting that was extracted or failed.
  - `score.total` is `extract.total` minus the postings whose extraction failed, so during extraction it shows the postings still on their way to scoring. `score.done` counts every posting scored or failed in `score`.
  - Excluded and held postings never enter either count.
  - Alternative: derive the counts in `read_pass` from `results`. Rejected, because `results` reaches the snapshot only when a node ends, which is the bug this change fixes.

- **Cancel is a flag checked before every posting.** `exclude`, `extract` and `score` ask `cancelled()` before each posting. A node that sees it stops its loop and returns its results so far, with `cancelled: True` in the state. `TriageState` gains `cancelled: bool`, named in its docstring, because LangGraph silently drops a key the state schema does not declare. It also carries `extract_failed: int`, which `store_scores` uses for the final counts, because a failed reading and a failed scoring share the status `failed`.
  - A pass cancelled in `exclude` goes to `END` through a new branch in `_after_exclude`. It asks no unscreened question and scores nothing.
  - A cancel can still land after `exclude`'s last check, while the graph is on its way to the unscreened interrupt. `Runs` closes that gap after the step, not inside the graph (see `Runs.cancel` below). `confirm_unscreened` accepts a third answer, `"cancel"`, besides `True` and `False`, and returns `cancelled: True`, so `_after_confirm` routes it to `END`.
  - `score` skips its loop and the index sync when the state is already cancelled.
  - `store_scores` stores what was scored and never asks the flag. A cancel that arrives while storing, or during the last posting of `score`, therefore ends as a complete pass (spec → Cancel while storing).
  - The postings the pass did not reach: `exclude` leaves them out of `results`, since it builds `results` from scratch, and `extract` and `score` leave them `pending` or `extracted`. Nothing is written for them.
  - Alternative: check only between phases. Rejected, because one phase of a large pass takes many minutes.

- **The status `cancelled`, not `aborted`.** `Runs._status` reports `cancelled` when the run has no next node and its state says `cancelled`. `aborted` keeps its meaning: the unscreened question was answered with abort, and nothing was stored. Alternative: reuse `aborted`. Rejected, because a cancelled pass may have stored scores, so the view must reload the pool and report a count, which it does not do for `aborted`.

- **`Runs.cancel(run_id)`.**
  - It raises `KeyError` for an ID that names a single score (prefix `score:`, which sits in `_computing` while it runs) or that `read()` does not know.
  - It raises `RunStateError` unless the run is computing.
  - Any pass ID the checkpoint knows is accepted on these terms, also one from before a restart. Such a pass is `awaiting_answer` or ended, so it gets the 409, not a 404.
  - The check and the add happen in one lock section. The context's `cancelled` hook reads the set of cancelled IDs, and `read()` reports `cancel_requested` while the run computes and its ID is in that set.
  - When a step ends (`_run`), `Runs` takes the lock and, in that one section, reads the snapshot and decides. Either it frees the slot and drops the ID from the set, or, when the step ended paused at the unscreened question while the ID is in the set, it keeps the slot and leaves the lock to resume the run with `Command(resume="cancel")`. The resumed step ends the pass `cancelled`, and its own end runs the same section again.
  - Since `cancel` checks `_computing` and adds the ID under the same lock, there is no gap between the decision and the release. A cancel that arrives before the section is seen there and resumed. One that arrives after it finds the slot free and gets the 409 for a pass that waits for the answer. Either way no 202 is lost.
  - The ID also leaves the set at the start of every later step (`_compute`), so an earlier request never carries over into a step resumed with „Trotzdem scoren“.
  - Alternative: clear the flag when the step ends and rely on the graph's checks alone. Rejected, because a cancel that arrives between the last check and the interrupt would answer 202 and then be lost.

- **API.** `POST /pool/passes/{id}/cancel` answers 202 `{pass_id}`, 404 `not found` for an unknown pass (a single score's `score:<id>` included, even while it computes), and 409 `pass not running` for a known pass that waits for the unscreened answer or has ended, before or after a restart. `GET /pool/passes/{id}` answers `{pass_id, status, started_at, error, progress, cancel_requested, scored, unscreened}`.
  - `progress` is the last reported progress, or `null` when this process holds none: before the first report, or after a restart.
  - `scored` counts the results with status `scored`. When a cancelled pass has ended, that is the number it stored.
  - `total` and `done` go away. The web UI is the only client.

- **The pass record.** `PoolPass` gets `cancelled: Literal[True] | None = None`, and `store_scores` sets it when the state says `cancelled`. The writer drops `None`, so the record of a pass that was not cancelled stays byte for byte as today. `counter` starts its window at the last pass whose variant is `"all"` or `None` and that is not cancelled. `schemas/pool.schema.json` is generated again. Alternative: `cancelled: bool = False`. Rejected, because `False` would be written into every new record, and the previous image, which forbids unknown fields, could then not read any pass recorded after the deploy. Alternative: a third `variant` value. Rejected, because the variant names what the pass set out to score, and `counter` treats a missing variant as „all“.

- **The view.**
  - `usePass` treats `cancelled` like `done`: it clears the stored pass, reloads the pool through `onDone`, and shows „Das Scoren wurde abgebrochen. N Anzeigen haben einen neuen Score.“ (with „1 Anzeige hat“ and „Keine Anzeige hat“). The text sits in the status region where „Das Scoren wurde abgebrochen.“ sits today, not in the `role="alert"` error box, and it clears when the next pass starts.
  - The cancel button shows while the pass computes (`working`), not while it asks the unscreened question and not in the phase `storing`. A press sends `POST …/cancel`. On the 202 the hook sets `cancel_requested: true` on its local state, as `answer` sets `status: 'running'`, so the button is disabled at once and not only after the next poll. While `cancel_requested` is set, the button stays disabled and the line says the pass stops after the current posting.
  - The progress band follows variant A. A head line holds the loader, „Scoren läuft: <phase>[, x von y]“ and a slot of fixed width for the cancel button. Below it sit always four steps („Anzeigen prüfen“, „Merkmale lesen · x von y“, „Scoren · x von y“, „Speichern“), each with a second line of fixed height for „fertig“, „läuft…“, „noch offen“, „am Ende“, „N fehlgeschlagen“ or a `<progress>` bar. Under the steps comes one hint line, whose text changes with the state: the default hint, „wird nach der aktuellen Anzeige beendet…“ after a cancel request, or the storing text. While storing, the button's slot stays empty but keeps its width.
  - So the band keeps its size from phase to phase. Only texts, ticks and bars change. While checking, and while `progress` is `null`, the steps show no counts.
  - The cancel request passes `send` an empty conflict text. A 409 means the pass ended or paused in between, and the next poll shows that. Any other failure shows „Das Scoren konnte nicht abgebrochen werden. Versuch es noch einmal.“
  - The new button needs no entry in the pool view's keyboard-shortcut exclusion. That list holds text fields and menus, and Enter on any button already keeps its own meaning. A view test pins that Enter on the focused cancel button cancels and does not jump to the next row.
  - The live region keeps text that does not change per poll. It announces the cancel request and the result once, not every count.
  - Texts and placement follow the Design artifact.

- **Eval.** No eval runs. The extractor and the judge get the same input as before, and the change only adds a check and a report between their calls.

- **Tests.**
  - Graph tests use fake models that record their calls. A cancel test uses a fake whose call sets the cancel flag on the n-th posting, so the order is fixed without `sleep`.
  - `Runs` and API tests use a fake model that blocks on a `threading.Event`, then cancel and release.
  - The progress test records every `progress` call and checks the counts after each posting, including an excluded posting, a held posting and a failed extraction.
  - The e2e walkthrough's scripted callable waits on a `threading.Event` the test releases, so the counts can be seen moving before the pass ends, and a cancel lands mid-pass.

## Risks / Trade-offs

- [A model call in flight cannot be interrupted, so a slow call delays the stop] → `cancel_requested` makes the view say the pass stops after the current posting, so the wait is explained.
- [A restart loses the live progress] → a restart already ends the running pass as `failed`, and the view shows that.
- [The progress callback runs on the pass thread while `read()` runs on a request thread] → `Runs` stores each report under its lock as a fresh copy, as `AlertRuns` does.
- [Overlap with other work on `PoolView.tsx` or `triage/graph.py`] → run the parallel-work check before the PR, and bring `origin/main` in with `git merge`.

## Migration Plan

Deploy as usual. Existing `pool.json` files stay valid, and the counter shows the same figures, since no stored record is cancelled. Rollback: the previous image rejects unknown fields, so a rollback after a cancelled pass was recorded also needs that record's `cancelled` field removed from `pool.json` in the data repository, for example by reverting that commit there.
