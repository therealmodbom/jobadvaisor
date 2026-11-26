# Tasks

## 0. Design gate

- [x] 0.1 Design approved on the canvas https://claude.ai/artifact/FLjijowheuanP61kDCif3c (2026-11-25), and the prototype edits in `alert-run.tsx`, `alert-pick.tsx` and `attempts.tsx` reverted before task 1.1 (`git diff` empty for `frontend/src`)

## 1. Attempts behind „Details“ (#158)

- [x] 1.1 `RunRow`: put the attempts of a closed and a failed row into `<details>` with the summary „Details: n Versuche“ („1 Versuch“ for one) after the row's text and buttons; a closed row says „Nichts gespeichert.“, a failed row without attempts keeps „Diese Anzeige konnte nicht gelesen werden.“ and has no „Details“. Test first in `AlertMailView.test.tsx`: the web-ui scenarios „Collapsed by default“ (attempt lines `not.toBeVisible()`, summary present), „Details opened“ (a click on the summary makes the lines visible and sets `open`; the keyboard is covered in task 5.1), „Entry that could not be judged“ (explanation and buttons outside `details`) and „Failed row without attempts“; change the existing tests that read open attempts to check visibility, and the test at `AlertMailView.test.tsx:696` that a closed row has no link

## 2. Posting link (#120)

- [x] 2.1 `OriginalLink` gains `name` (the visually hidden prefix „Anzeige „<name>“ öffnen, neuer Tab:“, or „Anzeige öffnen, neuer Tab:“ without one) and `className`; `PickRow` and `RunRow` render the entry's link through it in the mono style of the design. `rel` becomes `noopener noreferrer`; an address that is not http(s) stays plain text in both rows. Test first: the scenarios „Link in the pick list“ (accessible name, `href`, `target="_blank"`, `rel="noopener noreferrer"`, the checkbox still toggles) for the pasted and the mailbox pick list, „Open the posting of an entry that could not be judged“ (the run row's link), and an entry with a non-http address showing the address as text; update the `rel` assertion in `ImportView.test.tsx:613`, and verify that `PostingPage` and `ImportView` otherwise render `OriginalLink` as before
- [x] 2.2 `IntakeResult` links „Anzeige ansehen“ to `#/anzeigen/<posting_id>` beside „Anzeige öffnen“ (#80). Test first in `IntakeView.test.tsx`: the scenarios „New posting“ and „Posting already stored“ (link by role and name, `href`) for a link add

## 3. German attempt reasons (#160)

- [x] 3.1 `AttemptList` translates reasons by the table in `design.md`, keeps `HTTP <n>` and an unknown reason as they are, and marks only an unknown reason `lang="en"`. Test first in `components/attempts.test.tsx` (its existing test expects the raw `closed page (redirect)` and changes with it): every reason of the table (with a sample tail for the prefixes) shows German and none shows its English text, the scenarios „No posting text“, „Rate-limited“ and „Unknown reason“; update `IntakeView.test.tsx:320-321`, which expects the raw `closed page (redirect)` and `closed page (page text)`

## 4. Filter by outcome (#162)

- [x] 4.1 `outcomeOf` and the outcome table; `RunPanel` replaces the summary sentence by the filter row and the status line (design: below the progress bar, above the list, shown while running too) and filters the rows, keeping each row's original index. Test first: the scenarios „Filters of a finished run“, „Back to all“, „Filter to the entries that could not be judged“ (rows keep their text and PDF buttons), „Repeat of a link“ and „Status line“ (`aria-pressed`, `role="status"` text); move the summary assertions in `AlertMailView.test.tsx` and `MailboxView.test.tsx:509` to the filter buttons
- [x] 4.2 While running: test first the scenario „A third unread entry ends“ (a polled state with one more failed entry adds the row and updates the button and the status line under an active filter) and that waiting and running rows show only under „Alle“
- [x] 4.3 `pinned` row set: each „Ja, als neue Anzeige speichern“ adds its row, a filter change clears it, a filtered list always includes its rows, the status line counts the rows shown, and the active filter's button stays at count 0. Test first: the scenarios „Stored anyway under „schon gespeichert““ (the row stays while running and after „Hinzugefügt“, the counts move by one), „Last entry of the active filter stored anyway“ („0 schon gespeichert“ stays pressed, the status line says 1 entry is shown, the button disappears after choosing „Alle“), „Focus after confirming“ (`document.activeElement` is the row's outcome line after the confirm, while running and after „Hinzugefügt“, with and without a filter) and „Two rows stored anyway in a row“, and that choosing another filter drops the rows

## 5. Whole-change checks

- [x] 5.1 Update the e2e walkthroughs: `test_alert_mail_walkthrough.py` opens „Details“ with the keyboard (Enter on the focused summary) before it reads attempts, and reads the filter buttons instead of the summary sentence; `test_mailbox_walkthrough.py` chooses „nicht beurteilbar“ and checks that the row's link has the posting's address and opens in a new tab; verify that both pass
- [x] 5.2 Run `uv run --directory backend pytest`, `uv run --directory backend ruff check`, `npm --prefix frontend test`, `npm --prefix frontend run build` and `npm --prefix frontend run lint`, and click through a mailbox run of many entries in the browser: each filter while running and after, „Details“ by keyboard, the link in the pick list and the run, a forced row under „schon gespeichert“
- [x] 5.3 README: check the alert-mail and mailbox section for the run's summary and attempts and update it if it describes them; verify that the README names no real posting or sender
