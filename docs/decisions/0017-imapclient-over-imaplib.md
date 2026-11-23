# 0017. IMAPClient over the standard library's imaplib

## Status

Accepted, 2026-11-23.

## Context

Issue [#58 (Intake: read job alert mails from a configured mailbox)](https://github.com/therealmodbom/jobadvaisor/issues/58) asks for an existing library for IMAP and MIME parsing rather than a custom one. The mailbox access needs:

- a TLS login with certificate verification;
- the folder list with the server's special-use flags (trash, junk, sent, drafts);
- readable folder names, which IMAP transmits in modified UTF-7 (`Entw&APw-rfe` for „Entwürfe“);
- a read-only select;
- a search by date;
- fetching the folder's validity value, each mail's number and Message-ID header, and the full mail without setting the seen flag.

MIME parsing is covered by the standard library's `email` package either way.

## Decision

The app uses IMAPClient (BSD-3-Clause, release 4.3.0 of November 2026, Python 3.8 and later) for IMAP, and the standard library's `email` package for MIME.

## Alternatives considered

- **The standard library's `imaplib`.**
  - No new dependency.
  - IMAPClient wraps it, and `imaplib` alone answers with raw protocol lines. The app would have to parse the LIST answer and its flags itself, decode modified UTF-7 folder names, and parse FETCH answers with literals.
  - That is the self-built IMAP layer the issue rules out, and its parsing would be the least tested code in the feature.
- **`aioimaplib` (asynchronous).** The check runs in a background thread like the other runs. An asynchronous client brings no benefit and has a smaller user base.

## Consequences

- A new dependency, `imapclient`, pinned in `uv.lock`.
- Tests replace the IMAPClient object with a fake that answers the few calls the app makes, so the default test run never reaches a mailbox.
