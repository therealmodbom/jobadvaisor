# 0012. Links from a mail cleaned by an allow-list, not a deny-list

## Status

Accepted, 2026-11-13.

## Context

The links of an alert mail carry recipient-specific parameters, and some are login tokens: a one-time sign-in token on a professional network's tracking path, a single-sign-on token on a talent platform. Anyone holding such a link can sign in as the recipient. A link is fetched, stored in the data repository, logged and shown, and a redirect can lead a clean link to an address that carries a token.

## Decision

A link keeps only what identifies the posting:

- a link a fixed rule reads is rebuilt from the posting's ID, without a query;
- any other link keeps only the query parameters whose name identifies a posting (`id`, `jobId` and a few spellings), and a fragment only when it is a hash route;
- a redirect from a mail link is followed only to an address that this cleaning would leave unchanged, checked before it is requested, so a redirect target's token is never sent.

## Alternatives considered

- **A deny-list of token parameter names.** It keeps working job links that carry their ID in the query, but every new sender brings parameter names the list does not know (observed: `otpToken`, `midToken`, `sso`, `upn`, `uid`, `eid`). Until the list is extended, the unknown names are fetched with the recipient's session and stored in the data repository.
- **Dropping the whole query of every link.** This is the safest option, but a job site that names the posting in the query (`?jobId=…`) then shows a search page, and that page could be stored as a posting.

## Consequences

- A sender whose mail holds only click-redirect links, with the target hidden in an opaque query, loses that query. Its postings show as not addable by their link and fall back to text or PDF. #109 is the path to a rule for such a sender.
- A job site that names the posting in a parameter outside the allow-list loses it. Its postings show as not addable, or a single one is fetched without its ID and fails or stores the wrong page. A further name is a one-line addition.
- A site that redirects a clean link through an address with tracking or session parameters fails that entry, which then falls back to text or PDF.
