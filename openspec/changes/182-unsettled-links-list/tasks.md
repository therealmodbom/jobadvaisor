# Tasks

## 1. The file and its writer (D1, D2)

- [ ] 1.1 `UnsettledLink` and `UnsettledLinks` in `data/models.py` (fields and states per design D1, attempts as `{step, outcome}`), `unsettled-links` in `ENTITIES` of `data/schemas.py`, and `schemas/unsettled-links.schema.json` regenerated (`uv run --directory backend python -m jobadvaisor.data.schemas`). Test first: a valid file round-trips, an unknown state and a naive datetime are refused, and `tests/test_schemas.py` passes with the new file
- [ ] 1.2 `read_unsettled_links(root)` and `update_unsettled_links(root, change)` in `data/writer.py`, after `read_mailbox`/`update_mailbox`. Test first: a missing file reads as an empty list (the data-repository scenario „No unsettled links file“), an invalid file raises `DataRepositoryError`, an invalid result raises `ValueError` and leaves the file as it was, and the update runs under `write_gate` (a held gate blocks it)

## 2. `AlertRuns` keeps the list (D3, D4, D6)

- [ ] 2.1 `start(entries, *, source)` claims the slot, then writes the list outside its lock: leftover `waiting` rows turn `not_reached`, and each distinct link (`normalize_url`) is upserted `waiting` with `tries` and `added_at` kept, `title` and `source` overwritten. A failed write frees the slot and re-raises. Test first: the posting-intake scenarios „Waiting during the run“, „List cannot be written“ (no run, `current()` is `None`, nothing submitted), „Next run after a restart“, and two entries with one link giving one row
- [ ] 2.2 After each fetched entry, one `change`: `stored`/`duplicate`/`closed` drop the row; `failed` sets `unread` or `unclear`, `tries + 1`, `last_tried_at`, `attempts` (step and outcome only) and `reason`; an entry with `same_as` writes nothing; a write that raises is logged and the run goes on. Test first: „Failed link kept“, „Stored link leaves the list“, „First try“, „Tried again“, a failed entry with only a `reason`, a repeat counting one try, and a failing write that leaves the row `waiting` while the run finishes
- [ ] 2.3 End of the run (last entry, cancel, crash): every `waiting` row turns `not_reached`; drop `on_end` from `start` and `_run`. Test first: „Cancelled run“, „Not reached again“, a crash mid-run, and the existing end-hook tests in `tests/` removed or rewritten against the list
- [ ] 2.4 `AlertRuns.unsettled()` (a `waiting` row reads `not_reached` while no run computes, `in_run` while one does, order by `last_tried_at` else `added_at`, newest first) and `AlertRuns.remove(url)` (`LinkInRunError` for a `waiting` row while a run computes, decided inside the `change`; `KeyError` without a row; match by `normalize_url`). Test first: „Restart during a run“ (a fresh `AlertRuns` over a file with `waiting` rows), „Remove a link“, „Remove during the run“, „Unknown link“, and that a removal leaves `mailbox.json` and the postings untouched

## 3. Marking in `finish` (D5)

- [ ] 3.1 `MailboxChecks.finish` starts the run with `source="mailbox"`, then marks every mail of the pick list that is not `read_failed` (handled, or waiting when no model read it); remove `later`, `_marks_at_end`, `ENDED_WELL` and the `account` parameter of `mark_mails` with its tests. Test first: the posting-intake scenarios „Every entry stored“ (marked before the first entry ends, with a blocking fake intake), „One entry failed“, „Failing entry left out“ (the next check does not offer the mail, the link is in the list), „Restart during the run“, „Mails of a cancelled mailbox run“, „Entries added“, „Another run computes“ (nothing marked, no row written) and „List cannot be written“ (nothing marked); rewrite the tests that expect a mail to come back for a failed or unreached link

## 4. API (D7)

- [ ] 4.1 `GET /unsettled-links` and `DELETE /unsettled-links` (body `{url}`, 404 `not found`, 409 `link in run`, answers the list), and `POST /alert-mails/runs` passing `source="paste"`. Test first in the API tests: the list after a pasted run with one failed entry (scenario „Pasted mail“), a removal, both errors, and that no answer holds a sender, subject or mail text (scenario „File after a run“ checked on the written file)

## 5. Design gate (D8)

- [ ] 5.1 Design artifact on the JobAdvAIsor Design System: the tab „Offene Links“ with its badge, the navigation item with its badge, a row in each state (`Wartet` with the in-run note, „Nicht gelesen“ with „Details“, „Nicht beurteilbar“, „Nicht erreicht“), the empty list, the run report's pointer to „Offene Links“, and a phone's width. Stop for the owner's review; the review confirms the navigation badge, the word for a not reached link and whether the badge counts waiting links. Spec and design follow any change (`/opsx:sync` after a delta edit) before task 6.1

## 6. Frontend

- [ ] 6.1 `lib/unsettled-links.ts`: the types, `useUnsettledLinks()` (reads on mount and on the window event `unsettled-links-changed`) and `notifyUnsettledLinks()`; `useAlertRun` dispatches the event when a run leaves `running`. Test first: the hook reads again on the event, and a run that ends dispatches it
- [ ] 6.2 Route `#/offene-links` in `App.tsx` (like `#/importieren`), the source „Offene Links“ in `IntakeView`, and the badge on the tab and the navigation item (hidden at 0, the number in the accessible name by visually hidden text). Test first: the web-ui scenarios „Open links after a run“, „No open link“ and „Reload“, and that choosing another source leaves the route
- [ ] 6.3 `UnsettledLinksView`: rows with title, `OriginalLink`, outcome, source, tries, both dates and `AttemptDetails`; the empty text; „Entfernen“ with the `role="status"` announcement and the focus move; the in-run info icon instead of the button. Test first: „List after a run“, „Empty list“, „Remove a link“ (row gone, status text, badges at 2, focus on the next row, and on the heading after the last), „Link still in the run“
- [ ] 6.4 Texts: `MAILBOX_WORDS` and `PASTE_WORDS` (`again`, `lost`, `crash`, `cancelled`) and their doc comments per design D8, and the note below the mailbox pick list in `components/mailbox-pick.tsx`. Test first: the web-ui scenarios „Failed entries after a mailbox run“ (link to `#/offene-links`, no „wieder an“), „Mailbox run no longer known“, „Pasted run with a failed entry“ and „Note below the pick list“; update the tests in `MailboxView.test.tsx` and `AlertMailView.test.tsx` that read the old sentences

## 7. Whole-change checks

- [ ] 7.1 e2e: `test_mailbox_walkthrough.py`'s disputed link no longer brings its mail back. The next check does not offer it, the link shows under „Offene Links“ as „Nicht beurteilbar“, and „Entfernen“ removes it. Extend `test_alert_mail_walkthrough.py` by one failed pasted link that shows in the list. Verify that both pass after a frontend build (`uv run --directory backend pytest -m e2e`)
- [ ] 7.2 Run `uv run --directory backend ruff check`, `uv run --directory backend pytest`, `npm --prefix frontend run lint` (through `rtk proxy`), `npm --prefix frontend test` and `npm --prefix frontend run build`. Click through in the browser: a mailbox run with failed links, the badge, the tab, a removal, a reload, and a restart of the server during a run, after which the links read „Nicht erreicht“
- [ ] 7.3 Run `uv run --directory backend python ../scripts/readme_images.py` and verify `docs/images/` is unchanged, since the demo persona has no open link. Update the README's mailbox section and `AGENTS.md` (Current state: add this change, drop the oldest entry), and verify neither names a real posting or sender
