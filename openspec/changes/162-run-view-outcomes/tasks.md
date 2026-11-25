# Tasks

## 0. Design gate

- [ ] 0.1 Design approved on the canvas https://claude.ai/artifact/FLjijowheuanP61kDCif3c (2026-11-25), and the prototype edits in `alert-run.tsx`, `alert-pick.tsx` and `attempts.tsx` reverted before task 1.1 (`git diff` empty for `frontend/src`)

## 1. Attempts behind „Details“ (#158)

- [ ] 1.1 `RunRow`: put the attempts of a closed and a failed row into `<details>` with the summary „Details: n Versuche“ after the row's text and buttons; a closed row says „Nichts gespeichert.“. Test first in `AlertMailView.test.tsx`: the web-ui scenarios „Collapsed by default“ (no attempt line visible, summary present), „Details opened“ (opening it with the keyboard shows the lines and sets `open`) and „Entry that could not be judged“ (explanation and buttons outside `details`); adjust the existing tests that read open attempts

## 2. Posting link (#120)

- [ ] 2.1 `OriginalLink` gains `name` (the visually hidden prefix „Anzeige „<name>“ öffnen, neuer Tab:“, or „Anzeige öffnen, neuer Tab:“ without one) and `className`; `PickRow` and `RunRow` render the entry's link through it in the mono style of the design. Test first: the scenarios „Link in the pick list“ (accessible name, `href`, `target="_blank"`, `rel` holds `noreferrer`, the checkbox still toggles) for the pasted and the mailbox pick list, and „Open the posting of an entry that could not be judged“ (the run row's link); verify that `PostingPage` and `ImportView` still render `OriginalLink` as before

## 3. German attempt reasons (#160)

- [ ] 3.1 `AttemptList` translates reasons by the table in `design.md`, keeps `HTTP <n>` and an unknown reason as they are, and marks only an unknown reason `lang="en"`. Test first in `components/attempts.test.tsx` (its existing test expects the raw `closed page (redirect)` and changes with it): every reason of the table (with a sample tail for the prefixes) shows German and none shows its English text, the scenarios „No posting text“, „Rate-limited“ and „Unknown reason“

## 4. Filter by outcome (#162)

- [ ] 4.1 `outcomeOf` and the outcome table; `RunPanel` replaces the summary sentence by the filter row and the status line (design: below the progress bar, above the list, shown while running too) and filters the rows, keeping each row's original index. Test first: the scenarios „Filters of a finished run“, „Back to all“, „Filter to the entries that could not be judged“ (rows keep their text and PDF buttons), „Repeat of a link“ and „Status line“ (`aria-pressed`, `role="status"` text)
- [ ] 4.2 While running: test first the scenario „A third unread entry ends“ (a polled state with one more failed entry adds the row and updates the button and the status line under an active filter) and that waiting and running rows show only under „Alle“
- [ ] 4.3 `pinned` row: set on „Ja, als neue Anzeige speichern“, cleared on a filter change, always included in a filtered list. Test first: the scenario „Stored anyway under „schon gespeichert““ (the row stays while running and after „Hinzugefügt“, the counts move by one) and that choosing another filter drops it

## 5. Whole-change checks

- [ ] 5.1 Update the e2e walkthroughs `test_alert_mail_walkthrough.py` (the summary sentence becomes the filter buttons) and `test_mailbox_walkthrough.py` (open „Details“ where attempts are read; choose „nicht beurteilbar“ and check the row's link opens in a new tab); verify that both pass
- [ ] 5.2 Run `uv run --directory backend pytest`, `uv run --directory backend ruff check`, `npm --prefix frontend test`, `npm --prefix frontend run build` and oxlint through `rtk proxy`, and click through a mailbox run of many entries in the browser: each filter while running and after, „Details“ by keyboard, the link in the pick list and the run, a forced row under „schon gespeichert“
- [ ] 5.3 README: check the alert-mail and mailbox section for the run's summary and attempts and update it if it describes them; verify that the README names no real posting or sender
