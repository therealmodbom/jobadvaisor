# 0014. Closed rules add to the code defaults

## Status

Accepted, 2026-11-20.

## Context

The availability check of issue [#40 (Track whether a posting is still open)](https://github.com/therealmodbom/jobadvaisor/issues/40) finds a posting closed when its link answers HTTP 404 or 410, or when a closed rule matches. A closed rule names a host and exactly one marker:

- a redirect marker, a substring of the address a redirect points to;
- a page text marker, a phrase in the page's visible text.

The rules fall into two groups by where their host occurs:

- **Job platform rules.** Their host carries postings found by many users of the app. For example, LinkedIn answers a request for an expired job page with a redirect to a search page, and the address of that search page contains `trk=expired_jd_redirect`.
- **Employer site rules.** Their host is one employer's career site, which only the data repositories holding that employer's postings link to. For example, a career site can show a fixed notice on a filled position.

A host can change its responses, so the rules for it change over time.

The repository already has one per-host list with defaults in the code: `login_wall_hosts`. A policy pack that sets this field replaces the defaults completely.

## Decision

The default closed rules live in the code. The policy pack's `closed_rules` add to them and never replace them.

## Alternatives considered

- **Replace the defaults, as `login_wall_hosts` does.**
  - A policy pack holding one rule would drop every default, including the LinkedIn rule and every default a later release adds, and nothing would report the loss.
  - Replacing has a use for login walls: a policy pack can leave out a default host, and intake then fetches that host again.
  - It has no such use for closed rules. A default rule that gives a wrong result does so for every data repository with postings on its host, and a fix in the code corrects it for all of them.
- **Rules only in the code.** Every employer site rule would then need a release, and the public repository would hold host names taken from one user's postings.
- **Rules only in the policy pack.** Every job platform rule would then have to be copied into each data repository and updated there by hand. A new data repository would start without the LinkedIn rule.

## Consequences

- A policy pack cannot switch off a default rule. A wrong default rule is fixed by a release.
- A release that adds a default rule applies it to every data repository without a change to it.
- `login_wall_hosts` and `closed_rules` merge differently on purpose. The docstrings of both fields say which one replaces the defaults and which one adds to them.
