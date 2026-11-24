# Proposal

## Why

Job alert mails reach the app only when the user opens each mail, copies it and pastes it into the intake view. With several alerts a day, that copying is the slowest step of the intake, and a mail that is never pasted loses its postings. The app should read the alert mails from the user's mailbox itself, on a button press, and offer their postings in the pick list that already exists ([#58 (Intake: read job alert mails from a configured mailbox)](https://github.com/therealmodbom/jobadvaisor/issues/58), part of [#2 (Job sourcing)](https://github.com/therealmodbom/jobadvaisor/issues/2)).

Configuring a mailbox needs a place for app-wide settings. Today the header's gear opens a small popover with the two settings of the pool's hint, so this change turns it into a settings page.

## What Changes

- **Settings page.** The header's gear leads to a page „Einstellungen“ (`#/einstellungen`). Its sections are listed on the left, and above the content at a phone's width. Each section has its own address.
  - „Scoren“ holds the two settings of the pool's hint, moved unchanged from the popover, which goes away.
  - „Postfach“ holds the mailbox account and the folder choice.
- **Mailbox account.** Any mailbox reachable over IMAP works: host, port (default 993), user and password. A provider that only allows OAuth is not supported.
  - Every connection uses TLS, with the server certificate verified.
  - „Verbinden und Ordner laden“ logs in and lists the account's folders.
  - The user picks „Alle Ordner“ or a selection. „Alle Ordner“ is a rule, so a folder created later is included. Folders the server marks as trash, junk, sent or drafts are left out of „Alle Ordner“ and unticked in a selection. A hint above the choice asks for folders holding job alert mails only.
- **Password.**
  - The password field is masked. An eye button shows the typed text.
  - A stored password shows as eight dots and is never sent back by the API, which only says whether one is stored.
  - The password is stored encrypted, in the state directory on the machine the backend runs on. The key comes from the host's configuration (`MAILBOX_KEY`, a secret like the model key), never from a file next to the encrypted password. Without a key the field is disabled, and an info icon gives the reason.
  - The password appears in no log, trace, error message, API answer or data repository file.
  - The form recommends an app password, which the provider can revoke on its own.
- **Checking the mailbox.** The intake view gets a source „Postfach“.
  - Without an account, the source points to the settings.
  - Before the first check, the user sets „Mails ab“, by default 30 days back, with a hint about the model cost. Older mails are never read. The date changes only with the account.
  - „Postfach prüfen“ starts a check in the background, one at a time. The check reports how many unhandled mails it found and how many it has read, at most 200 mails per check, oldest first.
  - Each mail goes through the existing finder: fixed rules first, the content guard and the model for other senders, and one line per mail in the record. Mails are read only. They are never moved, flagged or marked as read.
  - A mail that sits in several folders is read once. A mail over 4 MB is skipped and named.
  - A connection, login or folder failure ends the check with its reason. A connection lost midway keeps the mails read so far.
  - „Prüfen abbrechen“ stops a running check after the current mail. The mails read so far stay in the pick list, and the unread ones come again in the next check. A stored password the key can no longer decrypt asks for the password again.
  - Above the pick list, short notes name what the check did not offer: mails left for the next check, missing folders, oversized, failed or held mails, and mails not read while screening is off.
  - Changing the server, port or user name without a new password removes the stored password, so it never goes to another server. Changing the server or user name also starts the handled-mail record afresh.
- **Pick list grouped by mail.** The postings of all new mails appear in one list, grouped by mail.
  - Each mail head shows the sender, then subject, date and folder on one line (stacked on a phone).
  - It has a checkbox that selects or clears all selectable entries of that mail, showing a dash when only some are selected, the count „n von m ausgewählt“, and a button that collapses the mail.
  - „N Anzeigen hinzufügen“ starts the existing alert run. „Nichts hinzufügen“ adds none.
- **Handled mails.**
  - A mail counts as handled once the user has finished the pick list holding it, or right away when the finder returns no posting for it.
  - A mail that failed, or that no model could read because screening is off, is not handled. A mail of the second kind waits until screening is turned on.
  - A handled mail is never offered again, also after the server renumbered a folder or when the mail was moved to another searched folder.
  - Handled and waiting mails are recorded in the data repository by the folder's validity value and number and by a hash of the message ID. Sender, subject and text are not recorded.
- **Side effects the user should know:**
  - The app stores the mailbox password, encrypted, on the backend's machine.
  - The data repository, and so its backup remote, holds the mailbox host, the user name, the folder choice and the handled-mail record.
  - Every mail from a sender without a fixed rule costs one model call, plus one screening call.
  - The text of every searched mail that no rule reads goes to the screening classifier, the model provider and the trace. That includes newsletters and private mail in a searched folder. A folder selection limits it.

## Non-goals

- OAuth logins (Gmail or Microsoft accounts without app passwords).
- A periodic or automatic check: only the button.
- Moving, flagging, deleting or marking mails on the server.
- More than one mailbox.
- IMAP without TLS. STARTTLS on port 143 is also out: port 993 with implicit TLS.
- A key file path or Docker secrets for `MAILBOX_KEY`: the key comes from the same configuration as every other secret.
- Moving the login-walled hosts list to the settings page ([#148 (Move the login-walled hosts list to the settings page)](https://github.com/therealmodbom/jobadvaisor/issues/148)).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `posting-intake`: adds the following requirements.
  - Connection and folders: „Mailbox over IMAP with TLS“, „Mailbox folders listed“, „Folders a check searches“, „One mail read once per check“, „The mailbox is read only“.
  - Which mails a check reads: „Mails from the start date on“, „Handled mails“, „Mails waiting for screening“, „Handled mails are skipped“, „Each mail through the finder“, „Oversized mails skipped“, „At most 200 mails per check“.
  - Running a check: „One mailbox check at a time“, „A failed check names its reason“, „An interrupted check keeps what it read“, „Cancel a mailbox check“.
  - The password and the account: „Mailbox password stored encrypted“, „The mailbox password is never revealed“, „The password stays with its account“, „A new account starts fresh“, „Unreadable stored password“.
  - Adding: „Mailbox entries added like alert entries“.
- `web-ui`: replaces „Settings in the header“ with „Settings page“, and modifies „Intake view“ (the mailbox source). Adds the following requirements.
  - Settings: „Mailbox settings form“, „Password field“, „Mailbox settings without a key“, „Folder choice“.
  - The mailbox source: „Mailbox source“, „Mailbox check progress and outcome“, „Cancel button of a mailbox check“, „Mailbox check report“, „Mailbox pick list kept when adding is refused“.
  - The pick list: „Mailbox pick list grouped by mail“, „Select a mail's entries at once“, „Collapse a mail“.
- `data-repository`: modifies „Documented schema per entity“ (the mailbox entity). Adds „Mailbox settings stored without the password“.
- `deployment`: adds „Mailbox key from the host“.

## Impact

- **Backend:**
  - New `intake/mailbox.py`: IMAP access over IMAPClient, the folder rules, the check runner and the handled-mail record.
  - New `secrets_store.py` (or similar): encrypt and decrypt the password with Fernet.
  - `settings.py`: `mailbox_key` in `SECRETS`.
  - `data/models.py` and `data/schemas.py`: the `Mailbox` entity and `mailbox.json`.
  - `api/app.py`: `GET`/`PUT /mailbox`, `POST /mailbox/folders`, `POST /mailbox/checks`, `GET /mailbox/checks/{id}` and `POST /mailbox/checks/{id}/finish`.
- **Frontend:**
  - The settings page with sections. `components/settings.tsx` becomes the „Scoren“ section.
  - The „Postfach“ section, the „Postfach“ source with its check and grouped pick list, `api.ts`, and the routing in `App.tsx`.
- **Dependencies:** `imapclient` (BSD-3-Clause) and `cryptography` (Apache-2.0 or BSD-3-Clause).
- **Configuration:** `MAILBOX_KEY` in `env.example`, the README and the deployment's `secrets.env`.
- **ADRs:** 0016 (the mailbox password encrypted in the state directory, with the key from the host) and 0017 (IMAPClient over `imaplib`).
- **Design:** the Design canvas linked from `design.md`.
