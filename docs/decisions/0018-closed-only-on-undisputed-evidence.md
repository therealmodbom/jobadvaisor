# 0018. A link counts as closed only on undisputed evidence

## Status

Accepted, 2026-11-25.

## Context

Intake treats a link as closed when an attempt on it answers 404 or 410, redirects to a closed rule's marker or shows a closed notice. It counted one such answer, whatever the other attempts on the same link said. In a run after a mailbox check, LinkedIn answered most requests with 429, 5xx or 202, and a single 404 among them made hundreds of entries "closed". Hand checks found most of them really closed, so the 404 is often right. But nobody can tell which ones are right, and a wrong one is lost, because its mail is not offered again (#159 (Postings shown as closed after a single 404 are lost)).

## Decision

- A closed redirect or a closed notice on the link stays conclusive on its own. Both are pages the server built to say that the posting is gone. This keeps the existing evidence instead of asking for more for every closed outcome.
- A 404 or 410 on the link counts only when no other attempt on that link was disputed: answered with another HTTP status than 200, 404 or 410, or ended in a connection or browser failure. Counting only 429, 5xx and transport errors as disputes was rejected: LinkedIn's bot answers also come as 202 and other codes, and a narrow list would keep the defect for them.
- A disputed link is a failed link, not a third outcome kind beside "closed" and "failed". It looks for another source and offers the failed entry's ways forward. The run marks it as one that could not be judged. A separate outcome kind was rejected, because every consumer (the run, the import report, the single-link view) would need a branch for something that behaves like a failure.
- The rule lives in the one function every intake path calls, so the list import follows it too. A run-only rule was rejected: the import would keep skipping disputed rows as gone, and two rules for the same word would drift.
- Confirming a 404 with a second spaced request, waiting for `Retry-After`, and skipping the intake loop while rate-limited (options 4, 3 and 5 of #159) were not taken. Each adds requests or waiting to every entry. Spacing the run's requests per host (the same change) removes most of the disputes at their cause.

## Consequences

- Fewer false "closed" outcomes. In exchange, some really closed postings end "nicht beurteilbar" while a host rate-limits. Their mails come back, and a later check judges them again.
- A disputed import row now goes through the intake loop before it is reported failed, which costs model calls that a row skipped as gone did not.
- A server that answers a closed posting with 404 to one request and 403 to the next is never judged closed. A closed rule's redirect or text marker for that host is the way to make it conclusive.
