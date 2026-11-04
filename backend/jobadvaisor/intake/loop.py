"""Ladder step 3, the intake loop (`design.md` → Intake): a ReAct agent (role `intake`) that
looks for the same posting at another source, typically the employer's careers page.

The model only chooses where to look and which fetched page holds the posting; the stored
text always comes from the fetched page itself, never from the model's output. Every tool
result is screened before the model sees it.
"""

import threading
from collections.abc import Callable

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from jobadvaisor.intake.fetch import (
    FetchError,
    Page,
    download_plain,
    download_rendered,
    html_text,
    page_from_html,
    page_links,
)
from jobadvaisor.intake.ladder import Attempt, LadderResult, is_login_walled
from jobadvaisor.tools.guard import WITHHELD, ContentGuard
from jobadvaisor.tools.prompts import DATA_RULE, data_block

MAX_TOOL_CALLS = 6
MAX_PAGE_CHARACTERS = 4000
MAX_LINKS = 40
INSTRUCTIONS = (
    "A job posting's link could not be read. Find the same posting at another source, "
    "typically the employer's own careers page or its applicant-tracking system (for example "
    "boards.greenhouse.io/<company>, jobs.ashbyhq.com/<company>, jobs.lever.co/<company> or "
    "<company>.jobs.personio.de). The link itself, or what the user says about the posting, "
    "often names the role and the employer. Follow links on the pages you fetch. You have at "
    f"most {MAX_TOOL_CALLS} tool calls besides report_posting. When a page you fetched holds "
    "the full posting, call report_posting with that page's URL and stop. If you cannot find "
    "it, stop without calling report_posting. "
    + DATA_RULE.format(tag="link") + " " + DATA_RULE.format(tag="page")
    + " " + DATA_RULE.format(tag="results") + " " + DATA_RULE.format(tag="hints")
)


def run_intake_loop(url: str, attempts: list[Attempt], walled_hosts: list[str],
                    model: BaseChatModel, guard: ContentGuard, *,
                    search: Callable[[str], str] | None = None,
                    hints: dict[str, str] | None = None,
                    plain: Callable[[str], tuple[str, str]] = download_plain,
                    rendered: Callable[[str], tuple[str, str]] = download_rendered
                    ) -> LadderResult:
    """Let the `intake` model look for the posting behind `url` with at most `MAX_TOOL_CALLS`
    fetch and search calls, after the ladder's `attempts`. Returns the page the model reported
    (one a tool fetched, with posting text and not withheld) or `None`, with every attempt.
    `search` returns result text for a query; without it the loop gets no search tool, so no
    call of the cap goes to "unavailable". `hints` are fields the user supplied (title,
    company, location), passed as data. `plain` and `rendered` download a URL as
    `(final URL, HTML)` and are replaced in tests."""
    attempts = list(attempts)
    candidates: dict[str, Page] = {}
    reported: list[str] = []
    budget, lock = [MAX_TOOL_CALLS], threading.Lock()

    def reserve() -> bool:
        """Take one call of the cap; parallel tool calls of one turn run in threads."""
        with lock:
            if budget[0] == 0:
                return False
            budget[0] -= 1
            return True

    def screen(text: str) -> str | None:
        """`guard.third_party(text)`, or `None` when screening itself fails (fail closed)."""
        try:
            return guard.third_party(text)
        except Exception:
            return None

    def fetch(step: str, download: Callable[[str], tuple[str, str]], target: str) -> str:
        if not reserve():
            return "tool budget exhausted; stop now"
        if is_login_walled(target, walled_hosts):
            attempts.append(Attempt(step, target, "login-walled host, not fetched"))
            return "login-walled host, not fetched"
        try:
            final_url, html = download(target)
        except FetchError as error:
            attempts.append(Attempt(step, target, str(error)))
            return f"fetch failed: {error}"
        except Exception as error:  # a malformed third-party link must not end intake
            attempts.append(Attempt(step, target, f"fetch failed: {type(error).__name__}"))
            return f"fetch failed: {type(error).__name__}"
        try:
            page = page_from_html(final_url, html)
        except FetchError:
            page = None
        links = "\n".join(f"- {text or '(no text)'}: {href}"
                          for text, href in page_links(final_url, html)[:MAX_LINKS])
        view = (f"URL: {final_url}\n\n"
                f"{(page.text if page else html_text(html))[:MAX_PAGE_CHARACTERS]}"
                f"\n\nLinks:\n{links}")
        if (screened := screen(view)) is None:
            attempts.append(Attempt(step, target, "screening failed"))
            return WITHHELD
        if screened == WITHHELD:
            attempts.append(Attempt(step, target, "withheld by the content guard"))
            return WITHHELD
        attempts.append(Attempt(step, target, "ok" if page else "no posting text"))
        if page:
            candidates[target] = candidates[final_url] = page
        return data_block("page", view)

    @tool
    def fetch_plain(url: str) -> str:
        """Fetch a web page over plain HTTP; returns its text and links."""
        return fetch("loop:fetch_plain", plain, url)

    @tool
    def fetch_rendered(url: str) -> str:
        """Render a web page in a browser, for pages that build their text with scripts;
        returns its text and links."""
        return fetch("loop:fetch_rendered", rendered, url)

    @tool
    def search_alternative_source(query: str) -> str:
        """Search the web; returns result titles, snippets and URLs."""
        if not reserve():
            return "tool budget exhausted; stop now"
        try:
            found = search(query)
        except Exception:  # a failing provider is one failed attempt, not the end of intake
            attempts.append(Attempt("loop:search_alternative_source", query, "search failed"))
            return "search failed"
        if (results := screen(found)) is None:
            attempts.append(Attempt("loop:search_alternative_source", query, "screening failed"))
            return WITHHELD
        attempts.append(Attempt("loop:search_alternative_source", query,
                                "withheld by the content guard" if results == WITHHELD else "ok"))
        return results if results == WITHHELD else data_block("results", results)

    @tool
    def report_posting(url: str) -> str:
        """Report the URL of a fetched page that holds the full posting."""
        if url not in candidates:
            return "not a fetched page with posting text; fetch it first"
        reported.append(url)
        return "recorded; stop now"

    tools = [fetch_plain, fetch_rendered] + ([search_alternative_source] if search else [])
    agent = create_agent(model, tools + [report_posting], system_prompt=INSTRUCTIONS,
                         middleware=[ModelCallLimitMiddleware(run_limit=MAX_TOOL_CALLS + 3,
                                                              exit_behavior="end")])
    tried = "\n".join(f"- {a.step}: {a.outcome}" for a in attempts) or "- none"
    known = "\n".join(f"{name}: {value}" for name, value in (hints or {}).items())
    agent.invoke({"messages": [HumanMessage(
        f"{data_block('link', url)}\n\n"
        + (f"What the user says about the posting:\n{data_block('hints', known)}\n\n"
           if known else "")
        + f"Attempts so far:\n{tried}")]})
    page = candidates.get(reported[-1]) if reported else None
    return LadderResult(page, attempts)
