# 0011. Alert mails read by link rules, and a model that picks link numbers

## Status

Accepted, 2026-11-13.

## Context

A job alert mail lists several postings, each behind one or more links. Its links carry recipient-specific parameters, some of them login tokens, so a link must never reach a model provider, the content guard's classifier or the trace store as it stands ([ADR 0012](0012-links-from-a-mail-cleaned-by-an-allow-list.md)). A pasted mail is a body only, without the sender's address, so the sender can be identified only by the shape of its links. The mail is untrusted content (posting-intake, "Untrusted content screened"), and the rendered HTML of one alert can run to around 90 KB.

## Decision

- **Fixed link rules for known senders.** A rule recognises a posting link by its host and path, names the posting's ID, and rebuilds the posting's URL from that ID. A mail with at least one link a rule reads is read by the rules alone, and no model is called.
- **A model for every other mail, and it only picks link numbers.** The mail is reduced to its visible text, with each link replaced by a number. The model answers with link numbers and titles. A number the mail does not hold is dropped, and a URL the model writes is ignored. The model reads a mail only after the content guard has screened it.

## Alternatives considered

- **A model on the whole mail, answering with URLs.** It is the shortest path and covers every sender, but every token reaches the model provider, the content guard's classifier and the trace store. The model can also invent or alter a URL, and the prompt grows to the size of the mail.
- **Rules keyed on the sender's address.** This would be exact, but a paste carries no sender address.

## Consequences

- A mail with at least one link a rule reads lists only the postings the rules read. A mail from an unknown sender that also holds one LinkedIn job link lists only that job. Alert mails come from one sender each, so this is accepted.
- With screening off, mails from unknown senders are not read at all.
- Adding a sender is code: a rule, a fictional fixture and an eval case.
- The finder records which rule read each mail, or that the model did, so a sender that keeps needing the model becomes visible (#109).
