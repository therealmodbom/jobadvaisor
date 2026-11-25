"""The fetch ladder (`design.md` → Intake): the Bundesagentur adapter, the plain fetch and the
rendered fetch, in that order. Hosts behind a login wall are never fetched."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from jobadvaisor.data.models import ClosedRule, PolicyPack
from jobadvaisor.intake import fetch
from jobadvaisor.intake.bundesagentur import fetch_bundesagentur, reference_number
from jobadvaisor.intake.fetch import (
    CLOSED_REDIRECT,
    CLOSED_TEXT,
    DEFAULT_CLOSED_RULES,
    FetchError,
    Page,
    fetch_plain,
    fetch_rendered,
    host_matches,
)

DEFAULT_LOGIN_WALL_HOSTS = ["xing.com"]  # linkedin.com serves a guest view, cut in `fetch`
# `DEFAULT_CLOSED_RULES` (LinkedIn's redirect marker) lives in `fetch`, which reads it as the
# default of its `closed_rules` context variable; `closed_rules` below adds the policy pack's.


@dataclass(frozen=True)
class Attempt:
    """One ladder step tried on one URL: `outcome` is "ok", "skipped" or the failure reason."""

    step: str
    url: str
    outcome: str


GONE_OUTCOMES = {"HTTP 404", "HTTP 410", CLOSED_REDIRECT, CLOSED_TEXT}
CLOSED_OUTCOMES = (CLOSED_REDIRECT, CLOSED_TEXT)  # a closed page: no further step is tried


def disputed(outcome: str) -> bool:
    """Whether an attempt's `outcome` leaves the question of the page open: an HTTP status
    other than 200, 404 and 410 (the server answered, but not about the page), or a connection
    or browser failure. "no posting text", a refused redirect and a closed marker do not."""
    status = outcome.removeprefix("HTTP ")
    if status != outcome and status.isdigit():
        return int(status) not in (200, 404, 410)
    return outcome.startswith(("connection failed", "browser failed"))


def _on(attempts: list[dict], url: str) -> list[str]:
    return [a["outcome"] for a in attempts if a["url"] == url]


def is_gone(attempts: list[dict], url: str) -> bool:
    """Whether `attempts` (the dicts of a `PostingNotFoundError`) show the page at `url` itself
    gone: redirecting to a closed rule's marker or showing a closed notice, or answering 404 or
    410 with no other attempt on `url` disputed (`disputed`). An attempt on another address (a
    redirect target, an alternative source) does not count."""
    outcomes = _on(attempts, url)
    return any(o in CLOSED_OUTCOMES for o in outcomes) or (
        any(o in GONE_OUTCOMES for o in outcomes) and not any(map(disputed, outcomes)))


def gone_disputed(attempts: list[dict], url: str) -> bool:
    """Whether `url` answered 404 or 410 but `disputed` keeps it from counting as gone: the
    link could not be judged. False when a closed marker settles it."""
    return any(o in GONE_OUTCOMES for o in _on(attempts, url)) and not is_gone(attempts, url)


@dataclass(frozen=True)
class LadderResult:
    """The page of the first step that yielded posting text, or `None`, and every attempt."""

    page: Page | None
    attempts: list[Attempt]


def login_wall_hosts(policy_pack: PolicyPack) -> list[str]:
    """The policy pack's `login_wall_hosts`, or `DEFAULT_LOGIN_WALL_HOSTS` when it has none."""
    configured = policy_pack.login_wall_hosts
    return list(DEFAULT_LOGIN_WALL_HOSTS if configured is None else configured)


def closed_rules(policy_pack: PolicyPack) -> list[ClosedRule]:
    """`DEFAULT_CLOSED_RULES` followed by the policy pack's `closed_rules`. Unlike
    `login_wall_hosts`, the policy pack's rules add to the defaults and never replace them
    (ADR 0014). The result is what a caller sets as the `fetch.closed_rules` context variable."""
    return [*DEFAULT_CLOSED_RULES, *(policy_pack.closed_rules or [])]


@contextmanager
def closed_rules_of(policy_pack: PolicyPack) -> Iterator[None]:
    """Run the `with` body with the `fetch.closed_rules` context variable set to
    `closed_rules(policy_pack)` for the current thread, and restore it afterwards. Wrap the
    fetches of a thread (intake, the agent's tools, the availability check) in it: a context
    variable set in one thread is not seen by another."""
    token = fetch.closed_rules.set(closed_rules(policy_pack))
    try:
        yield
    finally:
        fetch.closed_rules.reset(token)


def is_login_walled(url: str, hosts: list[str]) -> bool:
    """Whether `url`'s host is one of `hosts` or a subdomain of one."""
    return any(host_matches(url, listed) for listed in hosts)


def fetch_posting(url: str, walled_hosts: list[str], *,
                  adapter: Callable[[str], Page] | None = None,
                  plain: Callable[[str], Page] | None = None,
                  rendered: Callable[[str], Page] | None = None) -> LadderResult:
    """Run the ladder's fetch steps on `url` and stop at the first that yields posting text:
    the Bundesagentur adapter for its job-detail URLs, the plain fetch, then the rendered
    fetch. A login-walled host skips the last two. A closed page (`CLOSED_OUTCOMES`) ends the
    ladder at once, since the rendered fetch would only follow the same redirect. `adapter`,
    `plain` and `rendered` replace the real fetchers in tests."""
    steps = [("bundesagentur", adapter or fetch_bundesagentur)] if reference_number(url) else []
    walled = is_login_walled(url, walled_hosts)
    if not walled:
        steps += [("plain", plain or fetch_plain), ("rendered", rendered or fetch_rendered)]
    attempts = []
    for step, fetcher in steps:
        try:
            page = fetcher(url)
        except FetchError as error:
            attempts += [Attempt(step, url, text) for text in (*error.earlier, str(error))]
            if str(error) in CLOSED_OUTCOMES:
                break
            continue
        attempts.append(Attempt(step, url, "ok"))
        return LadderResult(page, attempts)
    if walled:
        attempts.append(Attempt("login_wall", url, "skipped"))
    return LadderResult(None, attempts)
