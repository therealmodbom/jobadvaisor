# Design

## Context

The run of an alert mail, pasted or from the mailbox, is one component: `AlertRunView` → `RunPanel` → one `RunRow` per entry (`frontend/src/components/alert-run.tsx`). `RunPanel` gets the entries of the run, or, after „Trotzdem speichern“, the original report with the forced row overlaid (`forced` in `lib/alert-run.ts`). It counts outcomes over `own` (entries without `same_as`), splitting `failed` by `unclear`, and prints them as one sentence once the run has ended. `RunRow` prints the link as a `font-mono` span and the attempts through `AttemptList` (`components/attempts.tsx`), always open. `PickRow` (`components/alert-pick.tsx`) prints the link the same way; the mailbox pick list (`mailbox-pick.tsx`) and the pasted pick list (`views/AlertMailView.tsx`) both use it. `AttemptList` is shared with the single-link and several-links views (`IntakeView`) and shows every reason other than `ok` and `skipped` raw, in parentheses, marked `lang="en"`.

The look is the approved design: https://claude.ai/artifact/FLjijowheuanP61kDCif3c (eight boards from the real app, desktop and phone). Its rules:

- The filter row is the pool's filter row (`PoolView`: `role="group"`, `aria-pressed` buttons, `min-h-11`, `rounded-lg`, active `bg-primary`), placed below the progress bar and above the list; the status line below it in `text-sm text-muted-foreground`.
- „Prüfe Titel, Firma und Ort der neuen Anzeigen auf ihren Seiten.“ and the „again“ note stay as sentences under the heading; the summary sentence goes.
- „Details: n Versuche“ is a link-styled summary (primary, underlined) at the end of the row, after the buttons of a failed row.
- The link: the address in `font-mono text-sm`, primary and underlined, with the `ExternalLink` icon.
- At phone width the filter row wraps; accepted as is.

## Goals / Non-Goals

**Goals:** see proposal.md. Design-level: one definition of an entry's outcome shared by counts and filter, and no change to the run state, the polling or the API.

**Non-Goals:** keeping the filter across a reload; the filter resets to „Alle“ whenever `RunPanel` mounts. A switch of source keeps it, since `IntakeView` only hides the other sources.

## Decisions

- **One outcome function.** `outcomeOf(entry)` maps an entry to `stored`, `duplicate`, `closed`, `unread`, `unclear` or none (waiting, running); an ordered table gives each its German word. The counts, the filter buttons and the filtered rows all use it, so the split of `failed` by `unclear` lives in one place. The counts stay over `own`; the filtered rows drop `same_as` rows, so a filter shows exactly its count.
- **Filter state in `RunPanel`.** `useState<Outcome | null>` (null: „Alle“), no key. `RunPanel` unmounts when the run is left (`onOver` shows the pick list or the source) and while polling has failed (`pollFailed` shows the retry instead), so a new run, and a run after a failed poll, starts at „Alle“; a forced run of one row keeps the same `RunPanel` mounted, so the filter survives it. Rejected: lifting the filter into `useAlertRun` or session storage, which only a reload would need, and a reload resetting to „Alle“ is fine.
- **The forced rows stay.** `RunPanel` keeps a set of `pinned` row indices: each confirm of „Ja, als neue Anzeige speichern“ adds its row, a filter change clears the set. A filtered list includes the pinned rows whatever their outcome, the status line counts the rows the list shows (pinned ones included), and the filter row always offers the active filter, even at count 0, so the active button never disappears under the user. Rejected: deriving it from `forced.index`, which outlives the user's attention (it is restored after a reload) and would keep a row in a filter it no longer matches long after.
- **Rows keep their index.** The filtered list maps over `entries` with their original index, so `onForce` still passes the right `{ index, base: entries }` with the unfiltered entries as base.
- **Native `<details>`.** The attempts go into `<details><summary>Details: n Versuche</summary><AttemptList/></details>` („1 Versuch“ for one), as `PostingText` already does: keyboard operation and the expanded state come from the browser, and closed is the default. A failed row without attempts keeps today's sentence „Diese Anzeige konnte nicht gelesen werden.“ and has no „Details“. Text in a closed `<details>` still counts as text content, so tests check visibility (`not.toBeVisible()` before opening, visible after); the jsdom user-event does not open a `summary` by key, so component tests click and the Playwright walkthrough uses the keyboard. Rejected: a button with `aria-expanded` and state, which is more code for the same behavior. Only the run rows change; the other intake views keep their attempt lists open (proposal, Non-goals).
- **Link through `OriginalLink`.** `OriginalLink` (`components/posting.tsx`) already opens http(s) links in a new tab with the `ExternalLink` icon; its `rel` becomes `noopener noreferrer`, as #120 names it (`noreferrer` alone already implies `noopener`). It renders nothing for an address that is not http(s); the rows then show the address as plain text, as today, so it never vanishes. It gains an optional `name`, rendered as a visually hidden prefix „Anzeige „<name>“ öffnen, neuer Tab:“ before the visible label (a nameless entry: „Anzeige öffnen, neuer Tab:“), and an optional `className`, which `PickRow` and `RunRow` use for the mono address. The accessible name then contains the visible text, as WCAG 2.5.3 asks. Rejected: a second link component next to it.
- **German reasons by table.** `AttemptList` translates the reason through an ordered list of exact texts and prefixes; the variable tail of a prefix match (an exception name, a browser message) is dropped. `HTTP <n>` passes through. An unknown reason passes through unchanged and keeps `lang="en"`; a known one loses it. The texts, as the backend raises them today:

  | Reason (raised in) | German |
  |---|---|
  | `no posting text` (`fetch.py`, `bundesagentur.py`, `loop.py`) | kein Anzeigentext gefunden |
  | `no job-board detail URL` (`bundesagentur.py`) | kein Link zur Anzeige in der Jobbörse |
  | `unparseable answer` (`bundesagentur.py`) | Antwort nicht lesbar |
  | `connection failed: …` (`fetch.py`, `bundesagentur.py`) | keine Verbindung |
  | `browser failed: …` (`fetch.py`) | Abruf im Browser gescheitert |
  | `fetch failed: …` (`loop.py`) | Abruf gescheitert |
  | `too many redirects` (`fetch.py`) | zu viele Weiterleitungen |
  | `invalid URL` (`fetch.py`) | ungültiger Link |
  | `redirect with personal parameters` (`fetch.py`) | Weiterleitung mit persönlichen Daten, nicht gefolgt |
  | `redirect to a non-public address` (`fetch.py`) | Weiterleitung an eine nicht öffentliche Adresse, nicht gefolgt |
  | `closed page (redirect)` (`fetch.py`) | Weiterleitung auf eine geschlossene Stelle |
  | `closed page (page text)` (`fetch.py`) | Seite meldet die Stelle als geschlossen |
  | `login-walled host, not fetched` (`loop.py`) | Seite mit Login-Pflicht, nicht abgerufen |
  | `screening failed` (`loop.py`) | Inhaltsprüfung gescheitert |
  | `withheld by the content guard` (`loop.py`) | vom Inhaltsfilter zurückgehalten |
  | `search failed` (`loop.py`) | Websuche gescheitert |

  The regression test lists these reasons and checks that none shows through untranslated. Rejected: German reasons from the backend, which would change the API, its tests and the list import for a display concern.
- **Status line.** A `<p role="status">` under the filter row: „Zeigt alle n Anzeigen“ or „Zeigt k von n Anzeigen: <Ergebnis>“ („Zeigt 1 von n Anzeigen“ for one), k being the rows shown. Under a filter it changes only when an entry of that outcome ends or the filter changes, so a running run does not announce every poll.

No ADR: the rejected alternatives are local implementation choices, not a significant decision.

## Risks / Trade-offs

- [A backend reason added later shows in English] → the fallback keeps it visible, and the test's list is the place to add it; `design.md` names the files that raise reasons.
- [The filter resets on reload] → accepted; the counts show at once what to choose again.
- [Tests and the e2e walkthrough read the summary sentence and the open attempts (`AlertMailView.test.tsx`, `test_alert_mail_walkthrough.py`)] → they move to the filter buttons and open „Details“ where they read attempts.

## Migration Plan

Frontend only; nothing to migrate. Rollback is a revert.
