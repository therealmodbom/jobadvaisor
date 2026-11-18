# Design

## Context

`pool.next_pass` sets `rescore` as soon as `counter(...)["corrections"] > 0`, and `POST /pool/passes` repeats that rule server-side and takes no body. The hint (`counter(...)["hint"]`) uses the thresholds instead, so button and hint disagree (proposal → Why). `pass_batch(repository, scores, rescore)`, `Runs.start(rescore)` and `start_run(..., rescore)` already serve both variants, so the pass itself needs no new logic.

`store_scores` (`triage/graph.py`) appends a `PoolPass` to `pool.json` for every pass that scored anything, and `counter` starts its window at the last pass's `started_at`. Until now a pass without rescore could only run with zero corrections, so restarting the window there dropped nothing. With the new default rule it would drop corrections below the threshold. The user therefore decided on 2026-11-18 that only a pass over all postings restarts the window (spec → Counter window).

`next_pass` is part of three answers: `GET /pool`, `PUT /postings/{id}/rating` and `POST /postings/{id}/score`. The view replaces its `next_pass` from the latter two without reloading the pool.

The look is drawn in the Design artifact [Pass-Button (#38, #75)](https://claude.ai/artifact/E8m3ddpZwF4XKBMhEDhJra): variant A (a select beside the button) and variant B (split button), each on desktop and phone. The user chose B on 2026-11-18, which is task 0.1. The boards were built for the canvas „Pool: Score-Bereich und Sortierung“, which could not be published to from these sessions, so they are a separate artifact. One text on the boards changes with the window decision (see Decisions → Wording). No board shows the state where every posting has a score; the spec covers it (web-ui → Pass button, „Nothing without a score“).

## Goals / Non-Goals

**Goals:**
- One rule decides the default: the hint. No second threshold check anywhere.
- The server decides what a pass scores from the variant name alone and never trusts a count from the page.
- A wrong click in the menu costs nothing.

**Non-Goals:**
- No change to how a pass scores, pauses or reports progress.
- No ADR: the decisions below are local to this view and this counter, and none is hard to reverse.

## Decisions

- **`next_pass` is `{default, unscored, all}`.** `default` is `"all"` when `counter(...)["hint"] == "rescore"`, else `"unscored"`. `unscored` and `all` are the counts of `pass_batch(..., False)` and `pass_batch(..., True)` without excluded and held postings, the way `count` is computed today. Both counts are needed because the menu announces each variant before it is chosen. Alternative: keep `{count, rescore}` and add a second count. Rejected, because `rescore` would then mean the default and no longer what the pass does, and the old name invites the `> 0` reading again.
- **`POST /pool/passes` takes `{"variant": "unscored" | "all"}`, required.** A Pydantic body with a `Literal` answers 422 for a missing or unknown variant, like the other bodies in `app.py`. The handler no longer reads the repository, so the old fallback for a repository that does not load goes away, and that case still ends in a `failed` pass as today. Alternative: an optional body that falls back to the default. Rejected, because the user picked a variant on screen, and a silent fallback could start the expensive one.
- **The pass record stores its variant.** `PoolPass` gets `variant: Literal["unscored", "all"] | None = None`. `store_scores` writes `"all"` when the state's `rescore` is set, else `"unscored"`. `counter` starts its window at the last pass whose variant is `"all"` or `None`. `None` means a record from before this change, which counts as a pass over all postings, so a stored counter stays as it is after the deploy. `schemas/pool.schema.json` is generated again (`uv run python -m jobadvaisor.data.schemas`). Alternative: a boolean `rescore`. Rejected, because the variant names are the ones the API and the UI already use. Alternative: a separate window marker in `pool.json`. Rejected, because it would be a second source of truth beside the pass history.
- **Split button from two `Button`s plus a Radix dropdown menu.** The main part is the existing primary `Button` with the rounded corners on the left only, and the trigger is a 44 px primary `Button` with a chevron, a light divider and `aria-label` „Andere Variante wählen“. The menu is `DropdownMenu` from the installed `radix-ui` with a `RadioGroup` of two `RadioItem`s, as on the boards: the variant name with its count in bold, the cost line below it, and a check on the shown one. Radix brings the keyboard handling (Enter, Space, arrows, Escape), focus return to the trigger and the ARIA roles. Alternative: a hand-built menu. Rejected, because of the keyboard and focus handling it would need. Alternative: a native `select`. That was variant A, which the user did not choose.
- **The shown variant is `picked ?? next_pass.default`.** `picked` is component state, set by the menu. It is cleared on every pool load (the view's `load`, which also runs after a pass ends), and by an effect whenever `next_pass.default` changes, including when a rating or a single score changes it without a reload. This is open decision 2 of #38 (Pass-Button zählt nach einer Korrektur alles), answered on 2026-11-18: the default is computed again on every load. A hand-picked „Alle“ thus never offers a second full rescore after its own pass. Alternative: remember the default at the time of the pick and compare. Rejected, because a default that flips and flips back would bring the old pick back (spec → „Default change replaces the choice“).
- **Cost line and disabled state.** A pass makes two model calls per posting: `extract` (feature extraction) and `score` (the judge). A posting the content guard never checked adds a classifier call, but the pass asks about those postings before it goes on. Below the button: „N Anzeigen ohne Score, je zwei Modellaufrufe.“ for `unscored`, and „N Anzeigen, je zwei Modellaufrufe. Vorhandene Scores werden ersetzt.“ for `all`, with „1 Anzeige“ for one. The menu entries carry the same line. When the shown count is 0, the main part is disabled, and the existing visible reason (`#pass-why`, linked through `aria-describedby`) depends on the variant: „Es gibt keine Anzeigen ohne Score.“ for `unscored`, „Es gibt nichts zu scoren: Alle Anzeigen sind ausgeschlossen oder zurückgehalten.“ for `all`. The trigger stays enabled. While a pass computes, both parts are disabled with „Das Scoren läuft.“. The start sends the shown variant.
- **Wording.** Every text in this table changes, and nothing else does:

  | File | Today | New |
  |---|---|---|
  | `PoolView.tsx` | „Neue Anzeigen bewerten (N)“ | „Anzeigen ohne Score scoren (N)“ / „Alle Anzeigen neu scoren (N)“ |
  | `PoolView.tsx` | „Es läuft schon eine andere Bewertung. Warte, bis sie fertig ist.“ | „Es wird schon gescort. Warte, bis das fertig ist.“ |
  | `PoolView.tsx` | „Die Bewertung konnte nicht gestartet werden. …“ | „Das Scoren konnte nicht gestartet werden. …“ |
  | `PoolView.tsx` | „Gerade rechnet eine andere Bewertung. Antworte, wenn sie fertig ist.“ | „Gerade wird schon gescort. Antworte, wenn das fertig ist.“ |
  | `PoolView.tsx` | „Die Bewertung wartet auf deine Antwort“ | „Das Scoren wartet auf deine Antwort“ |
  | `PoolView.tsx` | „Bewerte sie trotzdem, … Dann wird nichts bewertet, …“ | „Score sie trotzdem, … Dann wird nichts gescort, …“ |
  | `PoolView.tsx` | „Trotzdem bewerten“ | „Trotzdem scoren“ |
  | `PoolView.tsx` | „Es gibt keine neuen Anzeigen zu bewerten.“ (+ „Es gibt nichts zu bewerten: …“) | „Es gibt keine Anzeigen ohne Score.“ / „Es gibt nichts zu scoren: …“ |
  | `PoolView.tsx` | „Eine Bewertung läuft.“, „Die Bewertung läuft.“ | „Das Scoren läuft.“ |
  | `PoolView.tsx` | „Korrekturen seit der letzten Bewertung der Anzeigen:“ | „Korrekturen seit dem letzten Neu-Scoren aller Anzeigen:“ |
  | `PoolView.tsx` | „neue Bewertung sinnvoll“ | „neu scoren sinnvoll“ |
  | `PoolView.tsx` | „Die Bewertung wurde abgebrochen.“ | „Das Scoren wurde abgebrochen.“ |
  | `PoolView.tsx` | „Bewertung läuft: x von y“, „Bewertung läuft“ | „Scoren läuft: x von y“, „Scoren läuft“ |
  | `PoolView.tsx` | „Der Stand der Bewertung ist gerade nicht abrufbar“, „… Die Bewertung rechnet vielleicht weiter.“ | „Der Stand des Scorens ist gerade nicht abrufbar“, „… Das Scoren läuft vielleicht weiter.“ |
  | `PoolView.tsx` | „Die Bewertung ist fehlgeschlagen“, „… starte die Bewertung noch einmal.“ | „Das Scoren ist fehlgeschlagen“, „… starte das Scoren noch einmal.“ |
  | `IntakeView.tsx` | „Die nächste Bewertung der Anzeigen nimmt sie mit.“ (twice) | „Das nächste Scoren nimmt sie mit.“ |
  | `IntakeView.tsx` | „Beim Bewerten der Anzeigen wirst du nach ihr gefragt, …“ | „Beim Scoren wirst du nach ihr gefragt, …“ |
  | `IntakeView.tsx` | „… bleibt aber bei jeder Bewertung außen vor.“ | „… bleibt aber beim Scoren außen vor.“ |
  | `PostingPage.tsx` | „Noch kein Score – starte in der Liste „Neue Anzeigen bewerten“.“ | „Noch kein Score – starte in der Liste „Anzeigen ohne Score scoren“.“ |
  | `ChatView.tsx` | „Frag, warum eine Anzeige niedrig bewertet ist, …“ | „Frag, warum eine Anzeige einen niedrigen Score hat, …“ (the rest, „wie du früher bewertet hast“, stays) |

  These stay, because they are about the user's own rating: the filters „Noch nicht bewertet“ and „Bewertet“, „Keine weitere unbewertete Anzeige.“, „Anteil ab 10 Bewertungen“, the sort labels „Deine Bewertung: …“, everything in `rating.tsx`, „Deine Bewertung“ and „Noch keine Bewertung“ on the posting page, and the agent description in `ChatView.tsx`. Two texts differ from the first boards. The counter label says „seit dem letzten Neu-Scoren aller Anzeigen“ instead of „seit dem letzten Scoren“, because the window now starts only at a pass over all postings. The cost line names two model calls per posting instead of one. The boards were updated to match.

## Risks / Trade-offs

- [Radix menus need pointer and layout APIs that jsdom lacks] → stub what the component tests need in the Vitest setup, drive the menu by keyboard in Vitest, and click it in the e2e test in a real browser.
- [A pending pass started before the deploy carries no variant] → it is stored as `"unscored"` or `"all"` from the state's `rescore`, which every pass already has.
- [The counter now spans several passes, so its share mixes ratings measured against scores of different passes] → each correction is still measured against the posting's latest score, as the spec defines.
- [Overlap with #122 (Pool: Gesamtzahl und gefilterte Anzahl) or #73 (Pool-Filter zeigen Trefferzahl) on `PoolView.tsx`] → check `git worktree list` and `gh pr list` before the PR, and bring `origin/main` in with `git merge`.

## Migration Plan

Deploy as usual. Existing `pool.json` files stay valid: their pass records carry no variant and count as passes over all postings, so the counter shows the same figures as before the deploy. Rollback: the previous image rejects unknown fields (`Entity` forbids extras), so after the first pass on the new version, a rollback also needs the `variant` fields removed from `pool.json` in the data repository, for example by reverting that commit there.
