# 0019. A mail counts as handled by the outcome of its entries

## Status

Accepted, 2026-11-25. The first decision and the marking at the end of the run in the second are superseded by [ADR 0020](0020-unsettled-links-kept-apart-from-their-mail.md): a mail counts as handled once its entries went into a run, and its unsettled links are kept in a persisted list. The rejection of a persisted run and the other two decisions stand.

## Context

A mailbox check offers the postings of its mails in a pick list. Finishing the pick list started the alert run and marked every mail of the list handled in the same step, before any entry had an outcome. Run state lives in memory only. An entry that failed, was rate-limited or was never reached because the run crashed or the app restarted was therefore lost: its mail was never offered again (#159 (Postings shown as closed after a single 404 are lost), #153 (Cancel a running alert run)).

## Decision

- A mail with entries in the run is marked handled when the run ends, and only when every link of its entries in the run ended stored, as a duplicate or closed. Marking at finish, as before, was rejected because it is the cause of the loss.
- The end of the run marks, not a persisted run that resumes after a restart. A restart, a crash or a cancel leaves the affected mails unmarked, and the next check offers them again, with their stored entries shown as stored. Persisting the run state was rejected: it is a store and a resume path for a case that the next check already covers.
- Entries the user did not select never hold a mail back. Holding a mail until every entry it lists is stored was rejected: an entry that keeps failing would bring its mail back forever, and deselecting it is how the user lets go of it.
- No mailbox check starts while an alert run computes. Skipping the in-flight mails in a check was rejected: the pick list of such a check could not be finished during the run anyway, and the refusal is a single check where the skip needs its own record.

## Consequences

- A posting is lost only when the user deselects it or adds nothing from its mail.
- A mail whose entries keep failing comes back in every check and takes one of its places, oldest first, until the user deselects the entry.
- „Postfach prüfen“ waits for a computing alert run, also one started from a pasted mail.
