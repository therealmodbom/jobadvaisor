# 0020. Unsettled links kept apart from their mail

## Status

Accepted, 2026-11-27. Supersedes the first two decisions of [ADR 0019](0019-a-mail-counts-as-handled-by-the-outcome-of-its-entries.md).

## Context

Under ADR 0019 a mail of a mailbox run counts as handled only when every link of it in the run ended stored, as a duplicate or closed. In practice a rate-limited link keeps its mail coming back in every check, the same link is fetched again each time, and the way out (deselecting the entry) fails because the next pick list does not show which entry failed (#175 (Unsettled links: a list of their own, so their mail counts as handled)). ADR 0019 rejected marking at finish because a failed or unreached link was then lost, since run state lives in memory only.

## Decision

A mail of a mailbox run counts as handled once its entries went into a run, whatever their outcome. Every link a run takes is written to a persisted list of unsettled links in the data repository before any mail is marked, and leaves it only once it ended stored, as a duplicate or closed. The list, not the mail, is where an unsettled link waits for the user.

## Alternatives considered

- **Keep marking by outcome (ADR 0019):** rejected, because a link that keeps failing holds its mail open forever and takes a place in every check.
- **Mark at finish without a list:** rejected, it is the loss ADR 0019 was written against.
- **Keep the list in the state directory:** rejected, because that directory holds stores rebuildable from the data repository, and this list is not: once the mail counts as handled, nothing else remembers the link.
- **Write the list when the run ends:** rejected, because a restart mid-run would lose the links of mails that already count as handled.
- **Mark the mails and write the list together when the run ends:** rejected, because a restart would bring back every mail of the run and fetch all its links again, which feeds the rate limiting.
- **Persist the run and resume it after a restart:** rejected, as in ADR 0019: a resume path for a rare case, where a row marked not reached tells the user enough.

## Consequences

- A mail never comes back for a link, so checks stop refetching failed links and stop spending places on old mails.
- One write to the data repository per ended entry, instead of one per run.
- Links from a pasted mail join the same list, so later steps (#169, #183, #166) work on one list whatever the source.
- ADR 0019's third and fourth decisions stand: entries the user did not select never hold a mail back, and no mailbox check starts while an alert run computes.
