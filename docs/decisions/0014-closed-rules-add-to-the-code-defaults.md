# 0014. Closed rules add to the code defaults

## Status

Accepted, 2026-11-20.

## Context

#40 (Track whether a posting is still open) recognises a closed posting by HTTP 404 or 410, and by closed rules. A rule names a host and one marker: a text that the address of a redirect contains, or a text that the page contains. Some of these rules describe how a platform behaves for everyone. LinkedIn redirects an expired job page to a search page with `trk=expired_jd_redirect`. Others are only known to one user, for example the phrase one employer's career site shows on a filled position. Platforms change their behaviour, so the list grows over time.

The repository already has one list of this shape: `login_wall_hosts`. Its defaults live in the code, and a policy pack that sets the field replaces them completely.

## Decision

The default closed rules live in the code. The policy pack's `closed_rules` add to them and never replace them.

## Alternatives considered

- **Replace, as `login_wall_hosts` does.** A user who added one rule of their own would silently lose every default, including the LinkedIn rule, and with it every default a later release adds. For login walls, replacing lets a user unblock a host that the defaults list. A closed rule has no such use: a wrong default is a bug for everyone and is fixed in the code.
- **Rules only in the code.** Every rule known to only one user would then need a release. It could also put details of the user's own job search into a public repository.
- **Rules only in the policy pack.** Platform behaviour would then be copied into every data repository and kept current by hand. A new user would start without the LinkedIn rule.

## Consequences

- A user cannot switch off a default rule. If one is ever wrong, the fix is a release.
- A release that adds a default reaches every user without a change to their data repository.
- `login_wall_hosts` and `closed_rules` behave differently on purpose. The docstrings of both fields say which one replaces and which one adds.
