"""Intake-loop eval: success rate and mean tool calls on fixture pages served locally
(`design.md` → Evals). The loop's search is a fixed local index, since the cases test how the
loop uses results, not a search provider."""

import functools
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from statistics import mean

from langchain_core.language_models import BaseChatModel

from jobadvaisor.intake.ladder import DEFAULT_LOGIN_WALL_HOSTS, fetch_posting
from jobadvaisor.intake.loop import run_intake_loop
from jobadvaisor.settings import REPOSITORY_ROOT
from jobadvaisor.tools.guard import ContentGuard

PAGES = REPOSITORY_ROOT / "fixtures" / "intake" / "pages"


@dataclass(frozen=True)
class Case:
    """One intake case: `path` on the local server, or an absolute `url`; `expected` is the
    fixture page intake should end on, `None` when nothing should be found."""

    name: str
    expected: str | None
    path: str = ""
    url: str = ""
    hints: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Target:
    """A case resolved against the running server: the submitted URL, the URL of its
    alternative source if it has one, and the user's hints."""

    name: str
    url: str
    alternative_url: str | None
    hints: dict[str, str]


CASES = [
    Case("json_ld", "jsonld.html", path="jsonld.html"),
    Case("static", "static.html", path="static.html"),
    Case("script_rendered", "rendered.html", path="rendered.html"),
    Case("login_walled_with_alternative", "static.html",
         url="https://www.xing.com/jobs/backend-engineer-go-harbor-freight-4711",
         hints={"company": "Harbor Freight Analytics", "title": "Backend Engineer (Go)"}),
    Case("dead_link_with_alternative", "jsonld.html",
         path="jobs/lindqvist-instruments-senior-data-engineer.html",
         hints={"company": "Lindqvist Instruments", "title": "Senior Data Engineer"}),
    Case("unrecoverable", None, path="jobs/quillfeather-gmbh-platform-engineer.html",
         hints={"company": "Quillfeather GmbH", "title": "Platform Engineer"}),
]
SEARCH_INDEX = [  # keyword in the query → result title and fixture page
    ("harbor", "Backend Engineer (Go) – Harbor Freight Analytics careers", "static.html"),
    ("lindqvist", "Senior Data Engineer – Lindqvist Instruments", "jsonld.html"),
]


def run(model_for: Callable[[Target], BaseChatModel], guard: ContentGuard,
        model_name: str) -> dict:
    """Run every case through the ladder and, where it finds nothing, the intake loop with
    `model_for(target)` and `guard`. Reports per case success and loop tool calls, the success
    rate and the mean tool calls over all cases."""
    rows = []
    with serve_pages() as base:
        for case in CASES:
            target = Target(case.name, case.url or f"{base}/{case.path}",
                            f"{base}/{case.expected}" if case.expected else None, case.hints)
            try:
                result = fetch_posting(target.url, DEFAULT_LOGIN_WALL_HOSTS)
                if result.page is None:
                    result = run_intake_loop(target.url, result.attempts,
                                             DEFAULT_LOGIN_WALL_HOSTS, model_for(target), guard,
                                             search=_search(base), hints=case.hints)
                error = None
            except Exception as exc:  # one failing case must not end the eval
                result, error = None, f"{type(exc).__name__}: {exc}"
            page = result.page if result else None
            found = page.url.rsplit("/", 1)[-1] if page else None
            calls = sum(a.step.startswith("loop:") for a in result.attempts) if result else 0
            rows.append({"case": case.name, "success": error is None and found == case.expected,
                         "found": found, "tool_calls": calls, "error": error})
    return {"eval": "intake", "metric": "success rate and mean tool calls",
            "data": "local fixture pages: JSON-LD, static, script-rendered, login-walled with "
                    "an alternative, dead link with an alternative, unrecoverable",
            "model": model_name,
            "success_rate": round(mean(row["success"] for row in rows), 3),
            "mean_tool_calls": round(mean(row["tool_calls"] for row in rows), 2),
            "cases": rows}


def _search(base: str) -> Callable[[str], str]:
    def search(query: str) -> str:
        hits = [f"{title} — {base}/{page}" for keyword, title, page in SEARCH_INDEX
                if keyword in query.lower()]
        return "\n".join(hits) or "No results."
    return search


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@contextmanager
def serve_pages() -> Iterator[str]:
    """A local server for `fixtures/intake/pages` while the block runs; yields its base URL.
    Paths without a file answer 404."""
    server = ThreadingHTTPServer(("127.0.0.1", 0),
                                 functools.partial(_QuietHandler, directory=str(PAGES)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
