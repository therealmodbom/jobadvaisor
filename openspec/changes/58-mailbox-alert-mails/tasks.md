# Tasks

## 1. Design

- [x] 1.1 Boards on the Design canvas (design.md → D7), approved by the owner on 2026-11-23: pick list variant A, settings page, password field, folder choice, source states and errors

## 2. Dependencies and configuration

- [x] 2.1 Add `imapclient` and `cryptography` to `backend/pyproject.toml`, lock them, and verify that `uv sync --directory backend --frozen` installs both
- [x] 2.2 Add `mailbox_key` to `Settings` and `SECRETS`, and `MAILBOX_KEY` with its generate command to `env.example`; verify that `tests/test_env_example.py` passes and that a test reads the key from the environment

## 3. Password store (D1)

- [x] 3.1 Write `mailbox_secret.py` (`store`, `read`, `forget`, `PasswordUnreadable`, a key check that treats a malformed key as none), test first: a round trip, mode 600, no file means `None`, a wrong key raises `PasswordUnreadable`, a malformed key counts as no key, and the file never holds the plain text

## 4. Mailbox file and mail records (D3)

- [x] 4.1 Add the `Mailbox` model with its JSON Schema (`data/models.py`, `data/schemas.py`), `max_mails` included (1 to 1000, 200 when absent), and verify that the schema test and the published schema include it, that a repository without `mailbox.json` loads, and that 0 and 1001 are refused
- [x] 4.2 Add `read_mailbox` and the gated `update_mailbox`, with the handled and waiting marks, test first:
  - a mark written meanwhile survives a settings update;
  - a changed `UIDVALIDITY` replaces the folder's UIDs;
  - the Message-ID hash is the first 16 hex characters of SHA-256 over the trimmed lower-case ID;
  - a host or user change clears `since`, `last_check_at`, `handled` and `waiting`;
  - no sender, subject or text is written

## 5. IMAP access (D2, D5)

- [x] 5.1 Write the fake IMAP client for tests, which records calls and fails on a select without `readonly=True` or a fetch item without `PEEK`; verify with a self-test
- [x] 5.2 Write the `connect` factory (TLS with `ssl.create_default_context()`, 30 s timeout, `imapclient` logger at WARNING) and the one reason mapping, test first:
  - a certificate error gives `certificate`, a timeout gives `unreachable`, a refused login gives `login`, a non-TLS port and every other IMAP or SSL error give `protocol`;
  - no reason holds the server text;
  - the factory leaves the `imapclient` logger at WARNING
- [x] 5.3 Write the folder list and the searched-folder rule, test first against the spec scenarios „Folders of an account“, „Folder name outside ASCII“, „Parent folder that holds no mails“, „Folder created later“, „Server without folder flags“ and „Chosen folder deleted“, plus `\All`, `\Flagged` and `\Important` as system folders
- [ ] 5.4 Write the candidate search and `mail_parts`, test first:
  - `SINCE`; handled and waiting marks dropped; repeats deduplicated by ID hash; the `max_mails` oldest; `remaining`; nothing marked in this step;
  - the spec scenarios „Older mail“, „Mail in two folders“, „Mail moved“, „Folder renumbered“, „Large first check“, „Limit changed“ and „Blank HTML part“;
  - an HTML, a plain-only and a quoted-printable mail

## 6. The check (D4)

- [ ] 6.1 Write `MailboxChecks.start` and `read`, test first with the fake client and a stub finder:
  - one at a time; `total` and `read`; the finder per mail; a mail whose parts hold more than 2,000,000 characters offered with `oversized`, no finder call, nothing marked; a large attachment does not count;
  - `FinderError` mails failed and unmarked; screening-off mails waiting; held mails in `held` with their headers and marked; other empty mails marked at once;
  - `since` stored after login; `last_check_at` set on `done`; the `pending` check kept;
  - the spec scenarios of „Each mail through the finder“, „Handled mails“, „Mails waiting for screening“, „One mailbox check at a time“, and „Oversized mail“ and „Large attachment“ of „Oversized mails offered unread“;
  - measure a 200-mail check over the demo persona and record the time in the PR
- [ ] 6.2 Write the failure paths, test first:
  - `no key`, `no password`, `password unreadable`, `unreachable`, `certificate`, `login`, `folder` and `protocol`;
  - no login without a readable password and a valid key; no mail marked after a failure before reading; `since` not stored after a failed login;
  - a connection lost while reading ends `done` with the mails read so far and `interrupted`
- [ ] 6.3 Write `finish`, test first against „Mailbox entries added like alert entries“:
  - 0 to all offered entries, more than 100 included;
  - a link the check did not offer refused;
  - a busy run leaves everything unmarked;
  - a second finish refused;
  - only `mails` marked, unread oversized ones included, never `failed` or `not_screened`
- [ ] 6.4 Verify that a check never logs or answers the password: a test runs a whole check at DEBUG level with a known password and searches the log records and the state for it
- [ ] 6.5 Write `cancel`, test first against „Cancel a mailbox check“:
  - a cancel during reading stops after the current mail, ends `done` with `cancelled`, keeps the marks of the mails read and leaves the rest unmarked;
  - a cancel before the first mail reads none;
  - `cancel_requested` set while the current mail finishes;
  - a cancelled check's pick list finishes like any other;
  - `CheckNotRunningError` for a `done`, `failed` or `finished` check, `None` for an unknown ID
- [ ] 6.6 Write `read_oversized`, test first against „Oversized mail read on request“:
  - its entries join the offer and can be finished;
  - a `FinderError` leaves it readable again and unmarked after finishing; `screening off` marks it `waiting`; held or empty marks it handled;
  - refused for an unknown key, a mail that is not oversized or already read, and a check not `done`;
  - the kept parts dropped after the read and when the check is finished or replaced;
  - while a read runs, `finish`, a second read, `start` and an account change raise `ReadInProgressError`, and `reading` is cleared after a failed read too (a test holds the stub finder on an event)

## 7. API (D6)

- [ ] 7.1 Add `GET`/`PUT /mailbox` and `POST /mailbox/folders` to `create_app` (with the `connect` parameter), test first:
  - the password never in an answer; an empty password keeps the stored one;
  - `max_mails` answered, stored, and 422 outside 1 to 1000;
  - a host, port or user change without a password forgets it (spec „Server changed“);
  - a host or user change resets the records and answers 409 during a check;
  - 409 `no key`, also for a malformed key;
  - the reasons as 502, never with exception text;
  - `check_id` names a running or pending check
- [ ] 7.2 Add `POST /mailbox/checks`, `GET /mailbox/checks/{id}`, `POST /mailbox/checks/{id}/cancel`, `POST /mailbox/checks/{id}/mails/{key}/read` and `POST /mailbox/checks/{id}/finish`, test first: 202, 409 for a running check, 409 `not configured`, `since` required on the first check, 409 for a busy alert run, 422 for an entry not offered, 404 for an unknown check, cancel 202 or 409 `check not running`, read 200, 404, 409 `not oversized` or `read in progress`, or 502 without exception text, 409 `read in progress` for finish, start and an account change during a read, and no kept mail text in any answer

## 8. Frontend: settings page (D7)

- [ ] 8.1 Add the routes `#/einstellungen` and `#/einstellungen/<section>`, the gear as a link, and the page with the sections „Scoren“ and „Postfach“; move `SettingsForm` into „Scoren“ and remove the popover; verify with component tests (section by address, gear current, hint settings still save, spec scenario „Pool keys off“) and the scenario „Phone width“ in the browser
- [ ] 8.2 Build the section „Postfach“: fields, eye toggle, stored password as eight dots, the empty field after an account change, the no-key state with `WhyDisabled`, „Verbinden und Ordner laden“, the folder hint, the folder choice and „Höchstens Mails pro Prüfung“; verify with component tests for each spec scenario of „Mailbox settings form“, „Password field“, „Mailbox settings without a key“, „Folder choice“ and „Mails per check setting“

## 9. Frontend: mailbox source (D7)

- [ ] 9.1 Extract `AlertRunView` from `AlertMailView` without a behaviour change; verify that `AlertMailView.test.tsx` passes unchanged
- [ ] 9.2 Add the source „Postfach“: not configured, summary, „Mails ab“ with the cost hint, check start, progress, „Prüfen abbrechen“ and the cancelled note, nothing new, the failure reasons, the unreadable password, and attaching to `check_id` from `GET /mailbox`; verify with component tests for „Mailbox source“, „Mailbox check progress and outcome“ and „Cancel button of a mailbox check“, including a reload and a second tab during a check
- [ ] 9.3 Build the report notes and the pick list grouped by mail (mail heads with the meta line and the per-mail notes, tri-state checkbox, „n von m ausgewählt“, collapse, the oversized mail head with its read on ticking, „N Anzeigen hinzufügen“, „Nichts hinzufügen“) and hand the run to `AlertRunView`; verify with component tests for „Mailbox check report“, „Mailbox pick list kept when adding is refused“, „Mailbox pick list grouped by mail“, „Oversized mail in the pick list“, „Reading an oversized mail from the pick list“, „Select a mail's entries at once“ and „Collapse a mail“

## 10. Eval and regression (D8)

- [ ] 10.1 Write fictional `.eml` mails for the three rule senders and a regression test in the default pytest that runs them through `mail_parts` and `preview` with a model that fails when called; verify that the entries match
- [ ] 10.2 Write at least three fictional `.eml` eval cases of senders without a rule (hidden preheader, quoted-printable, multipart), let the alert-mail eval read `.eml`, and verify with `tests/test_eval_alert_mail.py` that the cases load (no paid run in this task)

## 11. Documentation and wrap-up

- [ ] 11.1 README: the mailbox as a way in next to the pasted alert mail, the key setup with its command, the app-password recommendation, what leaves the machine for unknown senders, and the deployment's `secrets.env` entry; verify that every command in it runs
- [ ] 11.2 Update „Current state“ in `AGENTS.md` with this change, dropping the oldest entry
- [ ] 11.3 Add an e2e walkthrough (`test_mailbox_walkthrough.py`) over a demo copy with the fake IMAP client: set up the account, check, collapse a mail, clear a mail, add, then check again and see nothing new; verify with `uv run --directory backend pytest -m e2e`
- [ ] 11.4 Run the paid alert-mail eval on the `.eml` cases once, name its cost first, and record the figures in the PR
- [ ] 11.5 Run the full suite, both linters and the frontend build, and click through the settings page and the source in the browser against a fake or test mailbox
- [ ] 11.6 Check whether the README images changed (header gear); retake them with `scripts/readme_images.py` if they did
