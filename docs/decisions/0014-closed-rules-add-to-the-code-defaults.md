# 0014. Closed rules add to the code defaults

## Status

Accepted, 2026-11-20.

## Context

The availability check of issue [#40 (Track whether a posting is still open)](https://github.com/therealmodbom/jobadvaisor/issues/40) finds a posting closed when its link answers HTTP 404 or 410, or when a closed rule matches. A rule names a host and one marker: a text that the address of a redirect contains, or a text that the page contains.

The rules fall into two kinds:

- **Host-wide rules.** These match a job platform's response for every posting it hosts. For example, LinkedIn answers a request for an expired job page with a redirect to a search page whose address contains `trk=expired_jd_redirect`.
- **Site-specific rules.** These match one employer's career site. For example, a site may show a fixed notice on a filled position. Such a rule matters only to a user whose postings come from that site.

Platforms change their responses over time, so the set of rules changes as well.

The repository already has one list of this shape: `login_wall_hosts`. Its defaults live in the code, and a policy pack that sets the field replaces them completely.

## Decision

The default closed rules live in the code. The policy pack's `closed_rules` add to them and never replace them.

## Alternatives considered

- **Replace, as `login_wall_hosts` does.** A user who added one rule of their own would silently lose every default, including the LinkedIn rule, and with it every default a later release adds. For login walls, replacing lets a user unblock a host that the defaults list. A closed rule has no such use: a wrong default rule misreads the platform's response for every user, so it is a defect, fixed in the code.
- **Rules only in the code.** Every site-specific rule would then need a release. It could also put details of the user's own job search into a public repository.
- **Rules only in the policy pack.** Every host-wide rule would then be copied into every data repository and kept current by hand. A new user would start without the LinkedIn rule.

## Consequences

- A user cannot switch off a default rule. If one is ever wrong, the fix is a release.
- A release that adds a default reaches every user without a change to their data repository.
- `login_wall_hosts` and `closed_rules` behave differently on purpose. The docstrings of both fields say which one replaces and which one adds.
