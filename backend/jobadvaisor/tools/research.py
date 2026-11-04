"""`research_company`: what the user's own data and the employer's website say about a company,
without a paid search provider (decision, 2026-10-11; `design.md` → Shared tools).

Every text passes the content guard before it is returned, since the caller hands it to a model.
"""

import re
from collections.abc import Callable
from urllib.parse import urlsplit

from jobadvaisor.data.loader import DataRepository
from jobadvaisor.intake.fetch import FetchError, download_plain, html_text
from jobadvaisor.intake.ladder import is_login_walled, login_wall_hosts
from jobadvaisor.tools.guard import WITHHELD, ContentGuard
from jobadvaisor.tools.prompts import data_block

NOTHING_FOUND = ("nothing found for {company}: no stored posting names it and no company "
                 "website could be read")
MAX_POSTINGS = 3
MAX_EXCERPT = 1500
MAX_PAGE_CHARACTERS = 4000
BOARD_HOSTS = ["arbeitsagentur.de", "greenhouse.io", "ashbyhq.com", "lever.co", "personio.de",
               "linkedin.com"]
JOB_SUBDOMAIN = re.compile(r"^(?:careers?|jobs?|karriere|apply)\.")


def research_company(company: str, repository: DataRepository, guard: ContentGuard, *,
                     website: str | None = None,
                     plain: Callable[[str], tuple[str, str]] = download_plain,
                     search: Callable[[str], str] | None = None) -> str:
    """What is known about `company`, as data blocks a model may read, or `NOTHING_FOUND`.

    Sources, in order: up to `MAX_POSTINGS` stored postings whose company contains `company`
    (case-insensitive; through `guard.posting`, so a flagged or unscreened one is withheld);
    the employer website, `website` when given, else derived from those postings' URLs (one
    fetch with `plain`); and `search` when a provider is configured. Third-party text is
    screened; a failed screening withholds the text (fail closed).
    """
    sections = []
    matches = matching_postings(company, repository)
    for posting_id in matches[:MAX_POSTINGS]:
        sections.append(_stored_posting(repository, guard, posting_id))
    if target := website or employer_website(repository, matches):
        sections.append(_fetched_website(target, guard, plain))
    if search is not None:
        sections.append(_searched(company, guard, search))
    return "\n\n".join(sections) or NOTHING_FOUND.format(company=company)


def matching_postings(company: str, repository: DataRepository) -> list[str]:
    """IDs of postings naming `company`: exact matches first, then the newest (IDs start with
    the date they were added)."""
    wanted = company.casefold().strip()
    if not wanted:
        return []
    found = sorted((posting_id for posting_id, posting in repository.postings.items()
                    if wanted in posting.company.casefold()), reverse=True)
    exact = [posting_id for posting_id in found
             if repository.postings[posting_id].company.casefold() == wanted]
    return exact + [posting_id for posting_id in found if posting_id not in exact]


def _stored_posting(repository: DataRepository, guard: ContentGuard, posting_id: str) -> str:
    try:
        posting = guard.posting(repository, posting_id)
    except Exception:  # a failed screening withholds, never passes text unscreened
        posting = None
    if posting is None:
        return f"Stored posting {posting_id}: {WITHHELD}"
    return (f"Stored posting {posting_id}:\n" + data_block("posting", (
        f"Title: {posting.title}\nCompany: {posting.company}\nLocation: {posting.location_raw}\n"
        f"URLs: {', '.join(posting.urls) or 'none'}\n\n{posting.text[:MAX_EXCERPT]}")))


def employer_website(repository: DataRepository, matches: list[str]) -> str | None:
    """The employer's home page guessed from its postings' URLs: the first host that is no
    known job board, no login-walled host and not used by another company's postings, with
    a leading `careers.`/`jobs.`-style label dropped."""
    # ponytail: host heuristic; an employer posting only on boards has no website here
    companies = {posting_id: posting.company.casefold()
                 for posting_id, posting in repository.postings.items()}
    own = {companies[posting_id] for posting_id in matches}
    shared = {_host(url) for posting_id, posting in repository.postings.items()
              if companies[posting_id] not in own for url in posting.urls}
    boards = BOARD_HOSTS + login_wall_hosts(repository.policy_pack)
    for posting_id in matches:
        for url in repository.postings[posting_id].urls:
            host = _host(url)
            if host and host not in shared and not is_login_walled(url, boards):
                return f"https://{JOB_SUBDOMAIN.sub('', host)}/"
    return None


def _fetched_website(url: str, guard: ContentGuard,
                     plain: Callable[[str], tuple[str, str]]) -> str:
    try:
        final_url, html = plain(url)
    except FetchError as error:
        return f"Company website {url}: fetch failed: {error}"
    except Exception as error:  # a malformed link must not end the research
        return f"Company website {url}: fetch failed: {type(error).__name__}"
    text = f"URL: {final_url}\n\n{html_text(html)[:MAX_PAGE_CHARACTERS]}"
    if (screened := _screen(guard, text)) == WITHHELD:
        return f"Company website {url}: {WITHHELD}"
    return f"Company website {url}:\n" + data_block("page", screened)


def _searched(company: str, guard: ContentGuard, search: Callable[[str], str]) -> str:
    try:
        found = search(f"{company} company")
    except Exception:  # a failing provider leaves the other sources
        return "Web search: search failed"
    if (screened := _screen(guard, found)) == WITHHELD:
        return f"Web search: {WITHHELD}"
    return "Web search:\n" + data_block("results", screened)


def _screen(guard: ContentGuard, text: str) -> str:
    """`guard.third_party(text)`, withholding when screening itself fails."""
    try:
        return guard.third_party(text)
    except Exception:
        return WITHHELD


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")
