# 0011. Alert mails read by link rules, and a model that picks link numbers

## Status

Accepted, 2026-11-13.

## Context

A job alert mail lists several postings, each behind one or more links. Its links carry recipient-specific parameters, and some of those are login tokens: a one-time sign-in token on a professional network's tracking path, or a single-sign-on token on a talent platform. Anyone holding such a link can sign in as the recipient. A pasted mail is a body only, without the sender's address or the plain-text MIME part, so the sender can be recognised only by the shape of the mail's links. The mail is untrusted content (posting-intake, "Untrusted content screened"), and the rendered HTML of one alert can run to around 90 KB.

## Decision

- **Fixed link rules for known senders.** A rule recognises a posting link by its host and path, names the posting's ID, and rebuilds the posting's URL from that ID, without a query. A mail with at least one link a rule reads is read by the rules alone, and no model is called. The first rules cover a professional network's job alert, the Bundesagentur für Arbeit job search, and a career-site platform used by many employers, whose job paths and query keys are the same on every employer's host.
- **A model for every other mail, picking link numbers.**
  - The mail is reduced to its visible text, with each link replaced by a number, its text, and its host and path. No query reaches the model, whether it sits in a link, in a URL printed in the text, or in a link's text. Path segments that look like tokens are masked.
  - The model answers with link numbers and titles. A number the mail does not hold is dropped, and a URL the model writes is ignored.
  - Links to unsubscribe, settings, search, profile, privacy and help pages are removed before numbering, and so are links that are not http(s) or point to a private host.
  - The model reads a mail only when the content guard has screened it. With screening off, only the rules read mails.
- **Allow-list cleaning for links no rule reads.** Such a link keeps only the query parameters whose name identifies a posting (`id`, `jobId` and a few spellings of those), and a fragment only when it is a hash route holding no `=`. It loses every other parameter.
  - A redirect from a mail link is followed only to an address that the allow-list cleaning would leave unchanged, also when a rule reads it, since a rule's own address can carry a token too. Each address is checked before it is requested, in the plain and in the browser fetch, so a redirect target's token is never sent. Filtering only the stored address would come too late: the fetch would already have requested the target.
  - When two postings the model found clean to the same link, both are listed and marked as not addable by their link, rather than merged.

## Alternatives considered

- **A model on the whole mail, answering with URLs.** It is the shortest path and covers every sender, but every token reaches the model provider, the content guard's classifier and the trace store. The model can also invent or alter a URL, and the prompt grows to the size of the mail.
- **Rules keyed on the sender's address.** This would be exact, but a paste carries no sender address.
- **A deny-list of token parameter names.** It keeps working job links that carry their ID in the query, but every new sender brings parameter names the list does not know (observed: `otpToken`, `midToken`, `sso`, `upn`, `uid`, `eid`). Until the list is extended, the unknown names are fetched with the recipient's session and stored in the data repository.
- **Dropping the whole query of every link.** This is the safest option, but a job site that names the posting in the query (`?jobId=…`) then shows a search page, and that page could be stored as a posting.

## Consequences

- A sender whose mail holds only click-redirect links, with the target hidden in an opaque query, loses that query. Its postings show as not addable by their link, and fall back to text or PDF. #109 is the path to a rule for such a sender.
- A job site that names the posting in a query parameter outside the allow-list loses that parameter. Its postings show as not addable, or a single one is fetched without its ID and fails or stores the wrong page. The pick list shows the cleaned link, so the user can deselect it.
- A mail with at least one link a rule reads is read by the rules alone. A mail from an unknown sender that also holds one LinkedIn job link lists only that job. Alert mails come from one sender each, so this is accepted.
- With screening off, mails from unknown senders are not read at all.
- A site that redirects a clean job link through an address with tracking or session parameters fails that entry, which then falls back to text or PDF.
- Adding a sender is code: a rule, a fictional fixture and an eval case.
- The finder records which rule read each mail, or that the model did, with the hosts of its links, so a sender that keeps needing the model becomes visible (#109).
