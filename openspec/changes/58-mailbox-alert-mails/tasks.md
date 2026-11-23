# Tasks

## 1. Design

- [x] 1.1 Boards on the Design canvas (design.md → D7), approved by the owner on 2026-11-23: pick list variant A, settings page, password field, folder choice, source states and errors

## 2. Dependencies and configuration

- [ ] 2.1 Add `imapclient` and `cryptography` to `backend/pyproject.toml`, lock them, and verify that `uv sync --directory backend --frozen` installs both
- [ ] 2.2 Add `mailbox_key` to `Settings` and `SECRETS`, and `MAILBOX_KEY` with its generate command to `env.example`; verify that `tests/test_env_example.py` passes and that a test reads the key from the environment

## 3. Password store (D1)

- [ ] 3.1 Write `mailbox_secret.py` (`store`, `read`, `forget`, `PasswordUnreadable`), test first: a round trip, mode 600, no file means `None`, a wrong key raises `PasswordUnreadable`, the file never holds the plain text

## 4. Mailbox file and handled record (D3)

- [ ] 4.1 Add the `Mailbox` model with its JSON Schema (`data/models.py`, `data/schemas.py`) and verify that the schema test and the published schema include it, and that a repository without `mailbox.json` loads
- [ ] 4.2 Add `read_mailbox`, `write_mailbox` and `mark_handled` under `write_gate`, test first: a merge keeps marks written meanwhile, a changed `UIDVALIDITY` replaces the folder's UIDs, a Message-ID hash is the first 16 hex characters of SHA-256 over the trimmed lower-case ID, and no sender, subject or text is written

## 5. IMAP access (D2)

- [ ] 5.1 Write the fake IMAP client for tests, which records calls and fails on a select without `readonly=True` or a fetch item without `PEEK`; verify with a self-test
- [ ] 5.2 Write the `connect` factory (TLS with `ssl.create_default_context()`, 30 s timeout) and the reason mapping (D5), test first: a certificate error gives `certificate`, a timeout gives `unreachable`, a refused login gives `login`, and no reason holds the server text
- [ ] 5.3 Write the folder list with system folders and the searched-folder rule, test first against the spec scenarios („Folders of an account“, „Folder name outside ASCII“, „Folder created later“, „Server without folder flags“, „Chosen folder deleted“)
- [ ] 5.4 Write the candidate search (`SINCE`, handled UIDs and IDs dropped, oldest 200, `remaining`) and `mail_parts`, test first: the spec scenarios „Older mail“, „Mail moved“, „Folder renumbered“, „Large first check“, and an HTML, a plain-only and a quoted-printable mail

## 6. The check (D4)

- [ ] 6.1 Write `MailboxChecks.start` and `read` (one at a time, progress `found` and `read`, the finder per mail, oversized mails skipped, `FinderError` mails failed, empty mails marked handled at once), test first with the fake client and a stub finder against the spec scenarios of „Each mail through the finder“, „Handled mails“ and „One mailbox check at a time“
- [ ] 6.2 Write the failure paths (no password, password unreadable, unreachable, certificate, login, folder), test first: no login is attempted without a readable password, and no mail counts as handled after a failure
- [ ] 6.3 Write `finish` (alert run, then marks; busy run leaves everything unhandled; a second finish is refused), test first against „Mailbox entries added like alert entries“
- [ ] 6.4 Verify that a check never logs or answers the password: a test runs a whole check at DEBUG level with a known password and searches the log records and the state for it

## 7. API (D6)

- [ ] 7.1 Add `GET`/`PUT /mailbox` and `POST /mailbox/folders` to `create_app` (with the `connect` parameter), test first: the password never in an answer, an empty password keeps the stored one, 409 `no key`, the reasons as 502
- [ ] 7.2 Add `POST /mailbox/checks`, `GET /mailbox/checks/{id}` and `POST /mailbox/checks/{id}/finish`, test first: 202, 409 for a running check, 409 `not configured`, `since` required on the first check, 409 for a busy alert run, 404 for an unknown check

## 8. Frontend: settings page (D7)

- [ ] 8.1 Add the routes `#/einstellungen` and `#/einstellungen/<section>`, the gear as a link, and the page with the sections „Scoren“ and „Postfach“; move `SettingsForm` into „Scoren“ and remove the popover; verify with component tests (section by address, gear current, hint settings still save) and the scenario „Phone width“ in the browser
- [ ] 8.2 Build the section „Postfach“: fields, eye toggle, stored password as eight dots, no-key state with `WhyDisabled`, „Verbinden und Ordner laden“ and the folder choice; verify with component tests for each spec scenario of „Mailbox settings form“, „Password field“, „Mailbox settings without a key“ and „Folder choice“

## 9. Frontend: mailbox source (D7)

- [ ] 9.1 Extract `AlertRunView` from `AlertMailView` without a behaviour change; verify that `AlertMailView.test.tsx` passes unchanged
- [ ] 9.2 Add the source „Postfach“: not configured, summary, „Mails ab“, check start, progress, nothing new, the failure reasons and the unreadable password; verify with component tests for „Mailbox source“ and „Mailbox check progress and outcome“, including a reload during a check
- [ ] 9.3 Build the pick list grouped by mail (mail heads with the meta line, tri-state checkbox, „n von m ausgewählt“, collapse, „N Anzeigen hinzufügen“, „Nichts hinzufügen“) and hand the run to `AlertRunView`; verify with component tests for „Mailbox pick list grouped by mail“, „Select a mail's entries at once“ and „Collapse a mail“

## 10. Eval and regression (D8)

- [ ] 10.1 Write fictional `.eml` mails for the three rule senders and a regression test in the default pytest that runs them through `mail_parts` and `preview` with a model that fails when called; verify that the entries match
- [ ] 10.2 Write at least three fictional `.eml` eval cases of senders without a rule (hidden preheader, quoted-printable, multipart), let the alert-mail eval read `.eml`, and verify with `tests/test_eval_alert_mail.py` that the cases load (no paid run in this task)

## 11. Documentation and wrap-up

- [ ] 11.1 README: the mailbox as a way in next to the pasted alert mail, the key setup with its command, the app-password recommendation and the deployment's `secrets.env` entry; verify that every command in it runs
- [ ] 11.2 Update „Current state“ in `AGENTS.md` with this change, dropping the oldest entry
- [ ] 11.3 Add an e2e walkthrough (`test_mailbox_walkthrough.py`) over a demo copy with the fake IMAP client: set up the account, check, collapse a mail, clear a mail, add, then check again and see nothing new; verify with `uv run --directory backend pytest -m e2e`
- [ ] 11.4 Run the paid alert-mail eval on the `.eml` cases once, name its cost first, and record the figures in the PR next to the paste figures of the same model
- [ ] 11.5 Run the full suite, both linters and the frontend build, and click through the settings page and the source in the browser against a fake or test mailbox
- [ ] 11.6 Check whether the README images changed (header gear); retake them with `scripts/readme_images.py` if they did
