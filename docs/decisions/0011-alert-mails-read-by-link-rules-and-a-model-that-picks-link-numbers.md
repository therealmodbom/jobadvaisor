# 0011. Alert mails read by link rules, and a model that picks link numbers

## Status

Accepted, 2026-11-13.

## Context

The user pastes a job alert mail that lists several postings. For each posting the app needs a title and a link to the posting's page. Two facts make this hard:

- **The links are personal.** A link in an alert mail carries parameters for the recipient, and some are login tokens: anyone holding the link can sign in as the recipient. Such a link must not reach the model provider, the content guard's classifier or the trace store, and not the data repository ([ADR 0012](0012-links-from-a-mail-cleaned-by-an-allow-list.md)).
- **The sender is unknown.** A paste is a mail body without the sender's address, so a sender can be told only by the shape of its links. The mail is also untrusted content (posting-intake, "Untrusted content screened"), and the rendered HTML of one alert can run to around 90 KB.

There are two ways to find the posting links. A *rule* is code for one known sender: it recognizes a posting link by its host and path (for example `linkedin.com/jobs/view/<id>`), reads the posting's ID from it and rebuilds the plain URL. It is exact and free, but exists only for senders someone wrote it for. A *model* can read any mail, but it is slower, costs money and sees what it is given.

## Decision

- **Rules first, for known senders.** Three rules exist: LinkedIn, the Bundesagentur für Arbeit and a career-site platform used by many employers. If at least one link in the mail matches a rule, the mail counts as coming from a known sender. The rules then read the whole mail, and no model is called. Reason: a known sender needs no model, and nothing personal leaves the app.
- **A model for every other mail, and it never sees a link target.**
  - The mail is reduced to its visible text. Each link is replaced by a number, its text, and its host and path, for example `[Senior Developer](#3 example.com/jobs/…)`. No query reaches the model.
  - The model answers with link numbers and titles, such as "3: Senior Developer". The app takes the real, cleaned URL from its own copy of the mail.
  - A number the mail does not hold is dropped, and a URL the model writes is ignored.
  - The model reads a mail only after the content guard has screened it.

## Alternatives considered

- **A model on the whole mail, answering with URLs.** It is the shortest path and covers every sender, but every token reaches the model provider, the content guard's classifier and the trace store. The model can also invent or alter a URL, and the prompt grows to the size of the mail.
- **Rules keyed on the sender's address.** This would be exact, but a paste carries no sender address.

## Consequences

- The worst a wrong model answer can do is pick the wrong link number. The pick list shows every entry before anything is fetched, so the user can deselect it.
- A mail with at least one link a rule reads lists only the postings the rules read. A mail from an unknown sender that also holds one LinkedIn job link lists only that job. Alert mails come from one sender each, so this is accepted. The finder names the hosts of the links it did not read, and the view tells the user to paste that mail alone.
- With screening off, mails from unknown senders are not read at all.
- Adding a sender is code: a rule, a fictional fixture and an eval case.
- The finder records which rule read each mail, or that the model did, so a sender that keeps needing the model becomes visible (#109).
