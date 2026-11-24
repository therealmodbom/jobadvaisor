# Design

## Context

See `proposal.md` → Why. The code this change builds on:

- **Finder.** `alert_mail.preview(intake, html, text, record)` reads one mail. It runs `find_postings` (the fixed rules first, then the content guard and the model), marks stored links as duplicates and login-walled hosts, and appends one line per mail to `alert-mails.jsonl` in the state directory.
  - It raises `FinderError` when screening or the model fails.
  - With no classifier configured, a mail no rule reads comes back empty with `model_skipped="screening off"`.
  - It loads the stored postings once per call.
  - `POST /alert-mails/preview` wraps it for a pasted mail and turns a blank HTML part into `None` first.
- **Adding entries.** `AlertRuns.start(entries)` (`intake/alert_runs.py`) adds chosen entries one after the other in the background, one run at a time. It raises `AlertRunBusyError(run_id)` while another run computes. `POST /alert-mails/runs` (1 to 100 entries) and `GET /alert-mails/runs/{id}` expose it.
- **Background checks.** `AvailabilityChecks` (`availability.py`) is the pattern for a check:
  - one at a time, its state in memory;
  - a `ThreadPoolExecutor` with one worker;
  - `start` answers the ID at once, and `read` reports progress;
  - the frontend keeps the ID in browser storage and polls.
- **Settings and secrets.** `Settings` (`settings.py`) reads every setting. Precedence: Keychain (only the fields in `SECRETS`), the environment, `.env`, `local.env`. `env.example` lists every field, which `tests/test_env_example.py` enforces. The container reads secrets from the host's `secrets.env` and keeps `STATE_DIRECTORY` on the persisted volume `/srv/jobadvaisor/state` (`deploy/compose.yaml`). `state_path(settings, root)` is the data repository's own directory inside it.
- **Data repository.**
  - Entities are Pydantic models (`data/models.py`), published as JSON Schemas (`data/schemas.py`, ADR 0006).
  - Writers in `data/writer.py` swap one file by rename under `write_gate`. `update_pool_settings` is the model for a gated read-modify-write.
  - `pool.json` is the model for a small optional file: a missing file means the defaults.
  - The backup commits any changed file. A file outside the known folders counts as "other file".
- **Error answers.** The global handler (`api/app.py`) answers an unhandled exception with its type and text, so every IMAP error must be mapped before it reaches it.
- **Frontend.**
  - `AlertMailView` holds the paste field, the pick list (`PickRow`, `Note`) and the run view (`RunPanel`, polling, `sessionStorage`) in one component.
  - `IntakeView` switches sources with `SOURCES` and keeps every source mounted.
  - `SettingsControl` (`components/settings.tsx`) is the gear's popover with `SettingsForm`.
  - `App.tsx` routes by hash (`VIEWS`, `#/importieren`, `#/anzeigen/<id>`). An unknown hash falls back to the pool view, whose `active` flag switches its key shortcuts on.
  - `WhyDisabled` (`components/why.tsx`) is the info icon beside a disabled control.
- **Dependencies.** `imapclient` and `cryptography` are not installed (`backend/uv.lock`).

## Goals / Non-Goals

**Goals:**

- Reading the mailbox reuses the finder and the alert run unchanged. The only new input path is one MIME mail turned into its HTML or text part.
- The password exists in plain text only in memory, for the moment of a login, and only for the account it was entered for.
- No mail is lost to an unfinished pick list, a restart before finishing, a failed mail, an interrupted connection or screening being off.

**Non-Goals:** see `proposal.md` → Non-goals.

## Decisions

### D1 The password: Fernet ciphertext in the state directory, key from `MAILBOX_KEY`

Why this storage and not the alternatives: [ADR 0016](../../../docs/decisions/0016-mailbox-password-encrypted-in-the-state-directory.md).

- **The key.** `mailbox_key` joins `SECRETS` in `settings.py`, so the Keychain (account `mailbox-key`), the environment, `.env` and the container's `secrets.env` all work. It holds a Fernet key: 32 url-safe base64 bytes, generated with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. A key that `Fernet` rejects counts as no key: `key_configured` is false, and every operation answers `no key`.
- **The module.** `mailbox_secret.py` has three operations:
  - `store(path, password, key)` writes `Fernet(key).encrypt(...)` to `<state_path>/mailbox-password` by rename, with mode 600.
  - `read(path, key)` returns the password, `None` when no file exists, or raises `PasswordUnreadable` on `InvalidToken`.
  - `forget(path)` removes the file. `PUT /mailbox` calls it when the account changes without a new password (D3).
- **Without a key.** `PUT /mailbox` with a password answers 409 `no key`. A check, or `POST /mailbox/folders`, fails with `no key` before it reads the password file.
- **Keeping it out of every output.**
  - The password lives only in the local variable that passes it to `client.login`. It is never put on a model or a state object, and never into a log or an exception text.
  - Every IMAP error maps to a fixed reason code (D5), never to its server text.
  - The real `connect` factory sets the `imapclient` logger to WARNING, because its DEBUG output logs protocol lines. A test asserts that level.
  - A second test runs a login at DEBUG level and asserts that the password is absent from the log and from every answer.

### D2 IMAP access through one narrow client

Why IMAPClient: [ADR 0017](../../../docs/decisions/0017-imapclient-over-imaplib.md).

`intake/mailbox.py` holds the account access behind a `connect(account, password)` factory, which `create_app` takes as a parameter so tests inject a fake. The real factory:

- builds `IMAPClient(host, port, ssl=True, ssl_context=ssl.create_default_context(), timeout=30)`. This verifies the certificate and the hostname. There is no plain or STARTTLS path.
- maps every error (D5).

The app uses only these calls:

- `login` and `logout`;
- `list_folders()`, which returns the names decoded:
  - A folder flagged `\Noselect` or `\NonExistent` is left out.
  - The flags `\Trash`, `\Junk`, `\Sent`, `\Drafts`, `\All`, `\Flagged` and `\Important` mark a system folder. The last three are virtual folders that show mails again from other folders.
- `select_folder(name, readonly=True)`, which answers `UIDVALIDITY`;
- `search(["SINCE", since])`;
- `fetch(uids, ["BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)]", "INTERNALDATE", "RFC822.SIZE"])` to find the candidates;
- `fetch(uid, ["BODY.PEEK[]"])` to read one mail.

The read-only select and `BODY.PEEK` together guarantee that no flag changes (requirement „The mailbox is read only“). The fake client records every call and fails a test on a select without `readonly=True` or a fetch item without `PEEK`.

### D3 The mailbox file and the mail record

`mailbox.json` in the data repository, model `Mailbox` (schema version 1):

```json
{"schema_version": "1", "host": "imap.example.org", "port": 993, "user": "name@example.org",
 "folders": {"all": true} | {"names": ["Posteingang", "Jobs"]},
 "since": "2026-10-24", "last_check_at": "2026-11-22T18:04:00Z",
 "handled": {"uids": {"Posteingang": {"validity": 1700000000, "uids": [101, 102]}},
             "ids": ["3f2a9c0d1b7e4a56"]},
 "waiting": {"uids": {}, "ids": []}}
```

- A missing file means no mailbox is configured.
- **Writes.** Every change goes through one gated read-modify-write, `update_mailbox(root, change)` under `write_gate`, like `update_pool_settings`. That covers the settings, the start date, `last_check_at`, the handled marks and the waiting marks. No two writers can drop each other's changes.
- **Which record holds a mail.** A mail is in a record when its `(folder, UIDVALIDITY, UID)` is in `uids`, or when the hash of its Message-ID is in `ids`.
  - The hash is the first 16 hex characters of the SHA-256 of the Message-ID, trimmed and lower-cased. It recognises a mail that was moved or renumbered, without storing the ID, which names the sender's domain.
  - A mail without a Message-ID relies on its UID alone.
  - When a folder's `UIDVALIDITY` changed, its old UIDs mean nothing: the next mark for that folder replaces them.
- **`handled`.** Never read again.
- **`waiting`.** Mails no model read because screening is off. A check skips them while screening is off. The first check with a classifier configured treats them as candidates again and removes them from `waiting` when it marks them.
- **`since`.** The first check stores it right after a successful login, from the date the source sent. Every check searches `SINCE since`. There is no moving cursor, so an unfinished pick list loses nothing.
- **Account change.** A `PUT /mailbox` that changes `host` or `user`:
  - clears `since`, `last_check_at`, `handled` and `waiting`;
  - drops an unfinished check;
  - answers 409 `check in progress` while a check runs.

  A change of `host`, `port` or `user` without a new password also calls `forget` (D1).

Rejected: keeping the record in the state directory. The state directory is not backed up, so a new server would offer every mail since `since` again, at the model's cost. Decided 2026-11-23.

### D4 The check

`MailboxChecks` (in `intake/mailbox.py`) copies the shape of `AvailabilityChecks`: one worker, one computing check, state in memory, `CheckBusyError(check_id)`. It also keeps the last `done` check whose pick list is not finished, as `pending`. A new check replaces it.

1. **Account.**
   - Read `mailbox.json`.
   - Fail at once, with no login attempted: `no key` for a missing or invalid key, `no password` for a missing password, `password unreadable` for one the key cannot decrypt.
2. **Folders.**
   - Connect, log in and list the folders. The searched folders are all listed folders except the system folders, or the chosen names.
   - A chosen name missing on the server goes into `missing_folders`.
   - Store `since` now if it is unset.
3. **Candidates.**
   - Per folder: select it read-only, search `SINCE`, drop the UIDs in `handled` and in `waiting` (the latter only while screening is off).
   - Fetch Message-ID, INTERNALDATE and size, and drop the IDs in those records.
   - Drop repeats within the check by ID hash.
   - Nothing is marked in this step, so a failure here leaves every record as it was.
   - Sort all folders' candidates by INTERNALDATE, oversized ones included. The 200 oldest are read. `total` is their number, and `remaining` counts the rest.
4. **Read each mail** (progress `read`):
   - A mail over 4,000,000 bytes (`RFC822.SIZE`) is never downloaded: only its display headers are fetched with `BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)]`, and it goes into `skipped`, marked handled.
   - Else fetch it with `BODY.PEEK[]` and parse it with `email.message_from_bytes(raw, policy=email.policy.default)`.
   - `mail_parts(message)` returns `(html, text)` from `get_body(("html",))` and `get_body(("plain",))`. A blank HTML part becomes `None`, as on the paste path.
   - A part over 2,000,000 characters puts the mail into `skipped`, marked handled.
   - Else `preview(intake, html, text, record)` runs, the same call as the paste.
   - Sender, subject and date come from the headers for display only and are never stored.
   - A `FinderError` puts the mail into `failed`, not marked, and the check goes on.
   - An answer with `model_skipped == "screening off"` puts the mail into `not_screened` and marks it `waiting`.
   - An answer with `held` puts the mail into `held`, marked handled at once.
   - Any other answer without entries is marked handled at once and not reported.
   - A mail with entries goes into `mails`, the pick list.
5. **End.**
   - Log out and set `last_check_at`. The state is `done` with `mails` (each with its `key`, display headers and preview answer), `skipped`, `failed`, `held`, `not_screened`, `missing_folders` and `remaining`. Each entry of `skipped`, `failed`, `held` and `not_screened` carries the mail's display headers (sender, subject, date) and folder, so the report can name it.
   - A connection error before step 4 makes the check `failed` with `reason` (D5).
   - A connection error during step 4 makes it `done` with what it read so far, `interrupted: <reason>`, and the unread mails left unmarked.

`finish(check_id, entries)`:

- It accepts only a `done` check that is not finished yet, and only entries whose cleaned URL is one the check offered. It takes 0 entries up to all of them.
- When there are entries, it calls `AlertRuns.start(entries)`. An `AlertRunBusyError` propagates, and nothing is marked.
- Otherwise it marks handled exactly the mails in `mails`, never `failed` or `not_screened`. It sets the check to `finished` and answers the run ID or `None`.
- A second finish answers 409, so a double click starts one run.

The same posting in two mails of one check appears twice in the pick list. The alert run stores it once and reports the second as a duplicate by link, which is the existing behaviour.

### D5 Reasons

The API answers English reason codes, and the frontend turns them into German text, as `AlertMailView.readFailure` does:

- `unreachable`: DNS failure, refused connection or timeout.
- `certificate`: `ssl.SSLCertVerificationError`.
- `login`: `LoginError`.
- `folder`: a select that fails for a folder that is listed.
- `protocol`: every other `ssl.SSLError`, `OSError`, `imaplib.IMAP4.error` or `IMAPClientError`, for example a port without TLS.
- `no key`.
- `no password`.
- `password unreadable`.

The mapping lives in one function around every IMAP call, so no IMAP exception reaches the global handler. The server's own message is never shown and never logged at INFO or above, because a server may echo the user name.

### D6 API

| Route | Answer |
|---|---|
| `GET /mailbox` | `{configured, host, port, user, folders, since, last_check_at, password: "missing"\|"stored"\|"unreadable", key_configured, check_id}`. `check_id` names the running check, or the `pending` one, else null. Never the password. |
| `PUT /mailbox` | Body: `{host, port, user, password?, folders?}`. An absent or empty `password` keeps the stored one, unless the account changes (D3). It answers like `GET`. Errors: 409 `no key` when a password comes without a valid key, 409 `check in progress` on an account change during a check, or 422. |
| `POST /mailbox/folders` | Logs in with the stored account: `{folders: [{name, system}]}`. Errors: 502 `{error: <reason>}`, 409 `no key`, `no password` or `password unreadable`. |
| `POST /mailbox/checks` | Body: `{since?}`, required while `since` is unset. 202 `{check_id}`. Errors: 409 `check in progress` with `check_id`, or 409 `not configured`. |
| `GET /mailbox/checks/{id}` | `{check_id, status: running\|done\|failed\|finished, reason, interrupted, total, read, remaining, mails, skipped, failed, held, not_screened, missing_folders}`, or 404. |
| `POST /mailbox/checks/{id}/finish` | Body: `{entries: [{url, title}]}`: 0 or more, each cleaned like `POST /alert-mails/runs` and checked against the check's offer. 202 `{run_id \| null}`. Errors: 409 `alert run in progress` with `run_id`, 409 `check not done`, or 422 for an entry the check did not offer. |

„Verbinden und Ordner laden“ is `PUT /mailbox` followed by `POST /mailbox/folders`.

### D7 Frontend

- **Routing.** `#/einstellungen` and `#/einstellungen/<section>` (`scoren`, `postfach`; the default is `scoren`) open `SettingsPage`.
  - The gear becomes a link with the accessible name „Einstellungen“ and `aria-current="page"` there.
  - `SettingsControl` and its popover go away. `SettingsForm` moves into the section „Scoren“ unchanged, and `onSaved` still reloads the pool's hint.
  - No main navigation item is current on the settings page, and the pool view is not `active`, so its key shortcuts are off.
- **Section „Postfach“** (`components/mailbox-settings.tsx`):
  - the fields and the action „Verbinden und Ordner laden“;
  - the password input with an eye toggle (`type` password or text, `aria-pressed`);
  - a stored password as the placeholder `••••••••`, labelled „Passwort · gespeichert“;
  - without a valid key, the disabled field with `WhyDisabled`;
  - after connecting, the folder hint, then the folder choice as two radios and a checkbox list.
- **Source „Postfach“** (`views/MailboxView.tsx`, a new entry in `SOURCES` after „Alert-Mail“):
  - It reads `GET /mailbox`. Not configured: a notice with the link „Postfach einrichten“. Configured: a summary line with a link to the settings, „Mails ab“ with the cost hint while `since` is unset, and „Postfach prüfen“.
  - It attaches to `check_id` from `GET /mailbox`, so another tab or a reload finds a running or unfinished check, and polls like the alert run.
  - The report notes use `AlertMailView`'s `Note`.
  - The pick list groups by mail. Each head has a tri-state checkbox (`indeterminate` set from a ref), „n von m ausgewählt“, and a collapse button with `aria-expanded` and `aria-controls`. The rows reuse `PickRow`.
- **Shared run view.** The run part of `AlertMailView` moves into an exported `AlertRunView`, with its polling, the stored-anyway rows and `sessionStorage`. `AlertMailView` and `MailboxView` both use it, so a run started from the mailbox shows exactly like one from a paste.
- **Design.** The Design canvas [Postfach: Auswahlliste A oder B](https://claude.ai/artifact/DQFSqGkSPBcyqQ6wpSw932) holds the approved boards, approved on 2026-11-23:
  - page „Auswahlliste“, variant A: one list, mail head with checkbox, count and collapse, and one meta line on desktop;
  - page „Einrichten und prüfen“: the settings page, the password field, the folder choice, the source states and the errors.

  Variant B on the first page was rejected. The report notes reuse the existing note style and have no board of their own.

### D8 Eval and regression tests

The mailbox gives the finder a mail's original `text/html` MIME part, where a paste gives the clipboard's re-serialised HTML. For known senders the rules read links, which are the same in both. For other senders the model reads `model_view` of that HTML. A MIME part can hold text a rendered copy drops, such as hidden preheaders and tracking blocks, so the model input changes.

- **Eval.**
  - Data: fictional `.eml` cases of senders without a rule in `fixtures/intake/alert-mails/` (at least three: a newsletter-style HTML mail with a hidden preheader, a quoted-printable mail and a multipart mail with both parts), each with its `<case>.json`.
  - `backend/jobadvaisor/evals/alert_mail.py` reads `.eml` through the same `mail_parts`.
  - Metrics: the existing `postings_found` and `links_correct`.
  - It is a paid run, done once at the change's wrap-up. Its figures are reported for the `.eml` cases on their own. They are not compared with the paste cases, which are different mails.
- **Regression (default pytest, no model).** Fictional `.eml` mails of the three rule senders go through `mail_parts` and `preview` with a model that fails the test when it is called. They pin the entries and show that charset and transfer encoding are decoded.

## Risks / Trade-offs

- **A server without SPECIAL-USE flags.** With „Alle Ordner“, trash and junk are searched too. Junk mail goes through the content guard and the rules like any mail, so the worst case is model cost. The user can switch to a selection.
- **What leaves the machine.** The text of every searched mail that no rule reads goes to the screening classifier, the model provider and the trace, newsletters and private mail included. A folder selection limits it. The proposal names it as a side effect.
- **The cost of the first check.** Up to 200 unknown-sender mails is up to 200 model and screening calls. „Mails ab“ (30 days back by default), the cap and the hint bound it.
- **One repository load per mail.** `preview` loads the stored postings for each mail, so a 200-mail check loads them 200 times. That is acceptable at today's pool size. Task 6.1 measures a 200-mail check over the demo persona. Passing the postings in once is the upgrade if it is slow.
- **A restart during the alert run.** The mails are handled once the run has started. A restart before the run ends loses the entries not yet added, as it does for a pasted mail. Pasting or re-adding those links recovers them.
- **Root on the backend machine.** It reads the key and the password (ADR 0016). The app password limits the damage.
- **A long check cannot be cancelled.** This is accepted for now (Non-goals). The progress line shows it is working.

## Open Questions

None.
