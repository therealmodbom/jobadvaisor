"""The fetch ladder (`design.md` → Intake): the Bundesagentur adapter, the plain fetch and the
rendered fetch, in that order. Hosts behind a login wall are never fetched."""

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from jobadvaisor.data.models import PolicyPack
from jobadvaisor.intake.bundesagentur import fetch_bundesagentur, reference_number
from jobadvaisor.intake.fetch import FetchError, Page, fetch_plain, fetch_rendered

DEFAULT_LOGIN_WALL_HOSTS = ["xing.com"]  # linkedin.com serves a guest view, cut in `fetch`


@dataclass(frozen=True)
class Attempt:
    """One ladder step tried on one URL: `outcome` is "ok", "skipped" or the failure reason."""

    step: str
    url: str
    outcome: str


GONE_OUTCOMES = {"HTTP 404", "HTTP 410"}


def is_gone(attempts: list[dict], url: str) -> bool:
    """Whether `attempts` (the dicts of a `PostingNotFoundError`) show the page at `url` itself
    answering 404 or 410 (`GONE_OUTCOMES`): the link is gone, not merely unreachable. An
    attempt on another address (a redirect target, an alternative source) does not count."""
    return any(a["url"] == url and a["outcome"] in GONE_OUTCOMES for a in attempts)


@dataclass(frozen=True)
class LadderResult:
    """The page of the first step that yielded posting text, or `None`, and every attempt."""

    page: Page | None
    attempts: list[Attempt]


def login_wall_hosts(policy_pack: PolicyPack) -> list[str]:
    """The policy pack's `login_wall_hosts`, or `DEFAULT_LOGIN_WALL_HOSTS` when it has none."""
    configured = policy_pack.login_wall_hosts
    return list(DEFAULT_LOGIN_WALL_HOSTS if configured is None else configured)


def is_login_walled(url: str, hosts: list[str]) -> bool:
    """Whether `url`'s host is one of `hosts` or a subdomain of one."""
    host = (urlsplit(url).hostname or "").lower()
    return any(host == listed or host.endswith("." + listed) for listed in hosts)


def fetch_posting(url: str, walled_hosts: list[str], *,
                  adapter: Callable[[str], Page] | None = None,
                  plain: Callable[[str], Page] | None = None,
                  rendered: Callable[[str], Page] | None = None) -> LadderResult:
    """Run the ladder's fetch steps on `url` and stop at the first that yields posting text:
    the Bundesagentur adapter for its job-detail URLs, the plain fetch, then the rendered
    fetch. A login-walled host skips the last two. `adapter`, `plain` and `rendered` replace
    the real fetchers in tests."""
    steps = [("bundesagentur", adapter or fetch_bundesagentur)] if reference_number(url) else []
    walled = is_login_walled(url, walled_hosts)
    if not walled:
        steps += [("plain", plain or fetch_plain), ("rendered", rendered or fetch_rendered)]
    attempts = []
    for step, fetch in steps:
        try:
            page = fetch(url)
        except FetchError as error:
            attempts.append(Attempt(step, url, str(error)))
            continue
        attempts.append(Attempt(step, url, "ok"))
        return LadderResult(page, attempts)
    if walled:
        attempts.append(Attempt("login_wall", url, "skipped"))
    return LadderResult(None, attempts)
