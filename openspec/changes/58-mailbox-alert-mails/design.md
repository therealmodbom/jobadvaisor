# Design

## Context

See `proposal.md` → Why. The code this change builds on:

- **Finder.** `alert_mail.preview(intake, html, text, record)` reads one mail. It runs `find_postings` (the fixed rules first, then the content guard and the model), marks stored links as duplicates and login-walled hosts, and appends one line per mail to `alert-mails.jsonl` in the state directory. It raises `FinderError` when screening or the model fails. `POST /alert-mails/preview` wraps it for a pasted mail.
- **Adding entries.** `AlertRuns.start(entries)` (`intake/alert_runs.py`) adds chosen entries one after the other in the background, one run at a time. It raises `AlertRunBusyError(run_id)` while another run computes. `POST /alert-mails/runs` and `GET /alert-mails/runs/{id}` expose it.
- **Background checks.** `AvailabilityChecks` (`availability.py`) is the pattern for a check:
  - one at a time, its state in memory;
  - a `ThreadPoolExecutor` with one worker;
  - `start` answers the ID at once, and `read` reports progress;
  - the frontend keeps the ID in browser storage and polls.
- **Settings and secrets.** `Settings` (`settings.py`) reads every setting. Precedence: Keychain (only the fields in `SECRETS`), the environment, `.env`, `local.env`. `env.example` lists every field, which `tests/test_env_example.py` enforces. The container reads secrets from the host's `secrets.env` and keeps `STATE_DIRECTORY` on the persisted volume `/srv/jobadvaisor/state` (`deploy/compose.yaml`). `state_path(settings, root)` is the data repository's own directory inside it.
- **Data repository.**
  - Entities are Pydantic models (`data/models.py`), published as JSON Schemas (`data/schemas.py`, ADR 0006).
  - Writers in `data/writer.py` swap one file by rename under `write_gate`.
  - `pool.json` is the model for a small optional file: a missing file means the defaults.
  - The backup commits any changed file. A file outside the known folders counts as "other file".
- **Frontend.**
  - `AlertMailView` holds the paste field, the pick list (`PickRow`) and the run view (`RunPanel`, polling, `sessionStorage`) in one component.
  - `IntakeView` switches sources with `SOURCES` and keeps every source mounted.
  - `SettingsControl` (`components/settings.tsx`) is the gear's popover with `SettingsForm`.
  - `App.tsx` routes by hash (`VIEWS`, `#/importieren`, `#/anzeigen/<id>`).
  - `WhyDisabled` (`components/why.tsx`) is the info icon beside a disabled control.
- **Dependencies.** `imapclient` and `cryptography` are not installed (`backend/uv.lock`).

## Goals / Non-Goals

**Goals:**

- Reading the mailbox reuses the finder and the alert run unchanged. The only new input path is one MIME mail turned into its HTML or text part.
- The password exists in plain text only in memory, for the moment of a login.
- No mail is lost: an unfinished pick list, a restart or a failed mail leaves the mail unhandled.

**Non-Goals:** see `proposal.md` → Non-goals.

## Decisions

### D1 The password: Fernet ciphertext in the state directory, key from `MAILBOX_KEY`

Why this storage and not the alternatives: [ADR 0016](../../../docs/decisions/0016-mailbox-password-encrypted-in-the-state-directory.md).

- `mailbox_key` joins `SECRETS` in `settings.py`, so the Keychain (account `mailbox-key`), the environment, `.env` and the container's `secrets.env` all work. It holds a Fernet key: 32 url-safe base64 bytes, generated with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- A small module (`mailbox_secret.py`) has three operations:
  - `store(path, password, key)` writes `Fernet(key).encrypt(...)` to `<state_path>/mailbox-password` by rename, with mode 600.
  - `read(path, key)` returns the password, `None` when no file exists, or raises `PasswordUnreadable` on `InvalidToken` or a malformed key.
  - `forget(path)` removes the file.
- No key configured: `PUT /mailbox` with a password answers 409 `no key`. `GET /mailbox` answers `key_configured: false`.
- The password lives only in the local variable that passes it to `client.login`. It is never put on a model or a state object, and never into a log or an exception text.
- Every IMAP error maps to a fixed reason code (D5), never to its server text. The `imapclient` logger is kept at WARNING, because its DEBUG output logs protocol lines. A test runs a login at DEBUG level and asserts that the password is absent from the log and from every answer.

### D2 IMAP access through one narrow client

Why IMAPClient: [ADR 0017](../../../docs/decisions/0017-imapclient-over-imaplib.md).

`intake/mailbox.py` holds the account access behind a `connect(account, password)` factory, which `create_app` takes as a parameter so tests inject a fake. The real factory:

- builds `IMAPClient(host, port, ssl=True, ssl_context=ssl.create_default_context(), timeout=30)`. This verifies the certificate and the hostname. There is no plain or STARTTLS path.
- maps the connection errors (D5).

The app uses only these calls:

- `login` and `logout`;
- `list_folders()`: the names come back decoded, and the flags `\Trash`, `\Junk`, `\Sent` and `\Drafts` mark a system folder;
- `select_folder(name, readonly=True)`, which answers `UIDVALIDITY`;
- `search(["SINCE", since])`;
- `fetch(uids, ["BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)]", "INTERNALDATE", "RFC822.SIZE"])` to find the candidates;
- `fetch(uid, ["BODY.PEEK[]"])` to read one mail.

The read-only select and `BODY.PEEK` together guarantee that no flag changes (requirement „The mailbox is read only“). The fake client records every call and fails a test on a select without `readonly=True` or a fetch item without `PEEK`.

### D3 The mailbox file and the handled-mail record

`mailbox.json` in the data repository, model `Mailbox` (schema version 1):

```json
{"schema_version": "1", "host": "imap.example.org", "port": 993, "user": "name@example.org",
 "folders": {"all": true} | {"names": ["Posteingang", "Jobs"]},
 "since": "2026-10-24", "last_check_at": "2026-11-22T18:04:00Z",
 "handled_uids": {"Posteingang": {"validity": 1700000000, "uids": [101, 102]}},
 "handled_ids": ["3f2a9c0d1b7e4a56"]}
```

- A missing file means no mailbox is configured.
- `read_mailbox` and `write_mailbox` follow `read_pool` and `write_pool`. `mark_handled(root, mails)` re-reads the file under `write_gate` and merges, so a check thread and a `PUT /mailbox` never overwrite each other.
- A mail is handled when its `(folder, UIDVALIDITY, UID)` is in `handled_uids`, or when the hash of its Message-ID is in `handled_ids`.
  - The hash is the first 16 hex characters of the SHA-256 of the Message-ID, trimmed and lower-cased. It recognises a mail that was moved or renumbered, without storing the ID, which names the sender's domain.
  - A mail without a Message-ID relies on its UID alone.
  - When a folder's `UIDVALIDITY` changed, its old UIDs mean nothing: the next mark for that folder replaces them.
- `since` is set by the first `POST /mailbox/checks` and changes only through `PUT /mailbox`. Every check searches `SINCE since`. There is no moving cursor, so an unfinished pick list loses nothing.

Rejected: keeping the record in the state directory. The state directory is not backed up, so a new server would offer every mail since `since` again, at the model's cost. Decided 2026-11-23.

### D4 The check

`MailboxChecks` (in `intake/mailbox.py`) copies the shape of `AvailabilityChecks`: one worker, one computing check, state in memory, `CheckBusyError(check_id)`.

1. **Account.** Read `mailbox.json`, then decrypt the password. When it is missing or unreadable, the check fails at once with `no password` or `password unreadable`, and no login is attempted.
2. **Folders.** Connect, log in and list the folders. The searched folders are all folders except the system folders, or the chosen names. A chosen name missing on the server goes into `missing_folders`.
3. **Candidates.** Per folder: select it read-only, search `SINCE`, drop the handled UIDs, then fetch Message-ID, INTERNALDATE and size, and drop the handled IDs. All folders' candidates are sorted by INTERNALDATE. The 200 oldest are read, and `remaining` counts the rest. `found` is set here, and progress counts `read`.
4. **Read each mail.**
   - Fetch it with `BODY.PEEK[]` and parse it with `email.message_from_bytes(raw, policy=email.policy.default)`.
   - `mail_parts(message)` returns `(html, text)` from `get_body(("html",))` and `get_body(("plain",))`.
   - A part over 2,000,000 characters (the paste limit) puts the mail into `skipped`.
   - Else `preview(intake, html, text, record)` runs, the same call as the paste.
   - Sender, subject and date come from the headers for display only and are never stored.
   - A `FinderError` puts the mail into `failed` (not handled), and the check goes on.
   - A mail answered with no entry, held or not, is marked handled at once.
5. **End.** Log out. The state is `done` with `mails` (each with its `key`, display headers and preview answer), `skipped`, `failed`, `missing_folders` and `remaining`. Or it is `failed` with `reason` (D5).

`finish(check_id, entries)`:

- For a `done` check, it calls `AlertRuns.start(entries)` when there are entries. An `AlertRunBusyError` propagates, and nothing is marked handled.
- Otherwise it marks every mail of the check as handled, sets `last_check_at` and answers the run ID or `None`.
- A finished check cannot be finished again, so a double click starts one run.

The same posting in two mails of one check appears twice in the pick list. The alert run stores it once and reports the second as a duplicate by link, which is the existing behaviour.

### D5 Reasons

The API answers English reason codes, and the frontend turns them into German text, as `AlertMailView.readFailure` does:

- `unreachable`: DNS failure, refused connection or timeout.
- `certificate`: `ssl.SSLCertVerificationError`.
- `login`: `LoginError`.
- `folder`: a select that fails for a folder that exists.
- `no password`.
- `password unreadable`.
- `no key`.

The server's own message is never shown and never logged at INFO or above, because a server may echo the user name.

### D6 API

| Route | Answer |
|---|---|
| `GET /mailbox` | `{configured, host, port, user, folders, since, last_check_at, password: "missing"\|"stored"\|"unreadable", key_configured}`, never the password |
| `PUT /mailbox` | Body: `{host, port, user, password?, folders?, since?}`. An absent or empty `password` keeps the stored one. It answers like `GET`, or 409 `no key` when a password comes without a key, or 422. |
| `POST /mailbox/folders` | Logs in with the stored account: `{folders: [{name, system}]}`. 502 `{error: <reason>}`, 409 `no password` or `password unreadable`. |
| `POST /mailbox/checks` | Body: `{since?}`, required while `since` is unset. 202 `{check_id}`. 409 `check in progress` with `check_id`, or 409 `not configured`. |
| `GET /mailbox/checks/{id}` | `{check_id, status: running\|done\|failed\|finished, reason, found, read, mails, skipped, failed, missing_folders, remaining}`, or 404. |
| `POST /mailbox/checks/{id}/finish` | Body: `{entries: [{url, title}]}`, cleaned and validated like `POST /alert-mails/runs`. 202 `{run_id \| null}`. 409 `alert run in progress` with `run_id`, or 409 `check not done`. |

„Verbinden und Ordner laden“ is `PUT /mailbox` followed by `POST /mailbox/folders`.

### D7 Frontend

- **Routing.** `#/einstellungen` and `#/einstellungen/<section>` (`scoren`, `postfach`; the default is `scoren`) open `SettingsPage`.
  - The gear becomes a link with the accessible name „Einstellungen“ and `aria-current="page"` there.
  - `SettingsControl` and its popover go away. `SettingsForm` moves into the section „Scoren“ unchanged, and `onSaved` still reloads the pool's hint.
  - No main navigation item is current on the settings page.
- **Section „Postfach“** (`components/mailbox-settings.tsx`):
  - the fields and the action „Verbinden und Ordner laden“;
  - the password input with an eye toggle (`type` password or text, `aria-pressed`);
  - a stored password as the placeholder `••••••••`, labelled „Passwort · gespeichert“;
  - without a key, the disabled field with `WhyDisabled`;
  - after connecting, the folder choice as two radios and a checkbox list.
- **Source „Postfach“** (`views/MailboxView.tsx`, a new entry in `SOURCES` after „Alert-Mail“):
  - It reads `GET /mailbox`. Not configured: a notice with the link „Postfach einrichten“. Configured: a summary line with a link to the settings, „Mails ab“ while `since` is unset, and „Postfach prüfen“.
  - The check ID stays in `sessionStorage`, and the view polls like the alert run.
  - The pick list groups by mail. Each head has a tri-state checkbox (`indeterminate` set from a ref), „n von m ausgewählt“, and a collapse button with `aria-expanded` and `aria-controls`. The rows reuse `PickRow`.
- **Shared run view.** The run part of `AlertMailView` moves into an exported `AlertRunView`, with its polling, the stored-anyway rows and `sessionStorage`. `AlertMailView` and `MailboxView` both use it, so a run started from the mailbox shows exactly like one from a paste.
- **Design.** The Design canvas [Postfach: Auswahlliste A oder B](https://claude.ai/artifact/DQFSqGkSPBcyqQ6wpSw932) holds the approved boards, approved on 2026-11-23:
  - page „Auswahlliste“, variant A: one list, mail head with checkbox, count and collapse, and one meta line on desktop;
  - page „Einrichten und prüfen“: the settings page, the password field, the folder choice, the source states and the errors.

  Variant B on the first page was rejected.

### D8 Eval and regression tests

The mailbox gives the finder a mail's original `text/html` MIME part, where a paste gives the clipboard's re-serialised HTML. For known senders the rules read links, which are the same in both. For other senders the model reads `model_view` of that HTML. A MIME part can hold text a rendered copy drops, such as hidden preheaders and tracking blocks, so the model input changes.

- **Eval.**
  - Data: fictional `.eml` cases of senders without a rule in `fixtures/intake/alert-mails/` (at least three: a newsletter-style HTML mail with a hidden preheader, a quoted-printable mail and a multipart mail with both parts), each with its `<case>.json`.
  - `backend/jobadvaisor/evals/alert_mail.py` reads `.eml` through the same `mail_parts`.
  - Metrics: the existing `postings_found` and `links_correct`.
  - It is a paid run, done once at the change's wrap-up and compared with the paste figures of the same model.
- **Regression (default pytest, no model).** Fictional `.eml` mails of the three rule senders go through `mail_parts` and `preview` with a model that fails the test when it is called. They pin the entries and show that charset and transfer encoding are decoded.

## Risks / Trade-offs

- **A server without SPECIAL-USE flags.** With „Alle Ordner“, trash and junk are searched too. Junk mail goes through the content guard and the rules like any mail, so the worst case is model cost. The user can switch to a selection.
- **The cost of the first check.** Up to 200 unknown-sender mails is up to 200 model and screening calls. „Mails ab“ (30 days back by default) and the cap bound it. The hint under „Mails ab“ names the cost.
- **Root on the backend machine.** It reads the key and the password (ADR 0016). The app password limits the damage.
- **A long check cannot be cancelled.** This is accepted for now (Non-goals). The progress line shows it is working.

## Open Questions

None.
