"""Employer facts (size class, founding year) read from a company page at intake
(`company-facts` spec). Only typed values leave this module: every value is matched against the
company record's patterns, so no text from a third-party page can reach a model through it.
"""

import re
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from jobadvaisor.data.loader import load
from jobadvaisor.data.models import SIZE_CLASS_PATTERN, Company, company_id
from jobadvaisor.data.writer import read_company, write_company
from jobadvaisor.intake.fetch import (
    TIMEOUT_SECONDS,
    USER_AGENT,
    json_ld_documents,
    require_http,
)
from jobadvaisor.tools.extraction import UNKNOWN
from jobadvaisor.tools.research import employer_website, matching_postings

MIN_INTERVAL_SECONDS = 2.0
LOGIN_PATHS = ("/authwall", "/login", "/uas/login", "/checkpoint")  # a redirect there is a block
ABOUT_SIZE = "about-us__size"
ABOUT_FOUNDED = "about-us__foundedOn"
# LinkedIn's size classes by upper head count; the last one is open ended.
SIZE_CLASSES = [(10, "1-10"), (50, "11-50"), (200, "51-200"), (500, "201-500"),
                (1000, "501-1,000"), (5000, "1,001-5,000"), (10000, "5,001-10,000")]
OPEN_CLASS = "10,001+"
ORGANIZATION_TYPES = {"Organization", "Corporation"}


@dataclass(frozen=True)
class Facts:
    """What a page stated: `size_class` ("51-200", "10,001+") and `founded` (a four-digit year),
    each `None` when absent or not in the record's format. Falsy when it holds neither."""

    size_class: str | None = None
    founded: int | None = None

    def __bool__(self) -> bool:
        return self.size_class is not None or self.founded is not None


@dataclass(frozen=True)
class Reply:
    """One answered request: the HTTP `status`, the address after redirects and the body."""

    status: int
    url: str
    html: str


def fetch_page(url: str, http: httpx.Client | None = None) -> Reply:
    """GET `url` once, with the intake timeout and no retry, and report what came back, whatever
    the status. Raises `FetchError` for an address that is no http(s) URL and `httpx.HTTPError`
    for a transport failure (refused, timed out, redirect loop)."""
    require_http(url)
    with http or httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True,
                              headers={"User-Agent": USER_AGENT}) as client:
        response = client.get(url)
    return Reply(response.status_code, str(response.url), response.text)


class Throttle:
    """Spaces requests to one host by at least `interval` seconds: `wait(host)` sleeps until
    the host's last request lies that far back, and counts the request as made when it returns."""

    # ponytail: one process; a second app process would need a limit shared through a file
    def __init__(self, interval: float = MIN_INTERVAL_SECONDS,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.interval, self._clock, self._sleep = interval, clock, sleep
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, host: str) -> None:
        with self._lock:
            if (due := self._last.get(host, float("-inf")) + self.interval) > self._clock():
                self._sleep(due - self._clock())
            self._last[host] = self._clock()


THROTTLE = Throttle()


def look_up(root: Path, company: str, company_url: str | None = None, *,
            fetch: Callable[[str], Reply] = fetch_page, throttle: Throttle = THROTTLE,
            now: datetime | None = None) -> Company | None:
    """Look up `company`'s facts once and store them as its record under `root`; returns the
    stored record, or `None` when nothing was stored.

    Sources in order: the LinkedIn company page `company_url` (when the posting's page gave
    one), then the employer's website guessed from the company's stored postings; the second
    is asked only when the first gave no facts, so a record's facts come from one source. A
    completed lookup (HTTP 200, or 404/410 for a gone page) that found no facts stores a record
    without facts. A lookup that did not complete (transport error, 429, 5xx or any other
    status, a redirect to a login wall) stores nothing and asks no further source, so the next
    posting of the company tries again. `None` also for a company that is "unknown" or has no
    usable name, one with a record already, and one with no source to ask (no request is made).
    Never raises: the intake must not fail because a lookup did.
    """
    try:
        name = company.strip()
        cid = company_id(name)
        if name == UNKNOWN or not cid or read_company(root, cid) is not None:
            return None
        read = None  # (source, url) of the last page read to completion
        for source, url in _sources(root, name, company_url):
            throttle.wait(urlsplit(url).hostname or "")
            reply = fetch(url)
            if not _completed(reply):
                return None
            read = (source, url)
            if facts := (parse_linkedin if source == "linkedin" else parse_website)(
                    reply.html if reply.status == 200 else ""):
                return _store(root, cid, name, read, facts, now)
        return _store(root, cid, name, read, Facts(), now) if read else None
    except Exception:  # a lookup is best effort, whatever went wrong
        return None


def _sources(root: Path, company: str, company_url: str | None) -> Iterator[tuple[str, str]]:
    """The pages to ask, in order, the website only when the generator is asked for it."""
    if company_url:
        yield "linkedin", company_url
    repository = load(root)
    if website := employer_website(repository, matching_postings(company, repository)):
        yield "website", website


def _completed(reply: Reply) -> bool:
    """Whether the request answered: HTTP 200 not redirected to a login wall, or a gone page."""
    if reply.status in (404, 410):
        return True
    return reply.status == 200 and not urlsplit(reply.url).path.startswith(LOGIN_PATHS)


def _store(root: Path, cid: str, name: str, read: tuple[str, str], facts: Facts,
           now: datetime | None) -> Company:
    source, url = read
    company = Company(schema_version="1", name=name, size_class=facts.size_class,
                      founded=facts.founded, source=source, source_url=url,
                      fetched_at=now or datetime.now(UTC))
    write_company(root, cid, company)
    return company


def parse_linkedin(html: str) -> Facts:
    """The facts in the about block of a LinkedIn company page: the `<dd>` inside the elements
    marked `data-test-id="about-us__size"` ("51-200 employees") and `"about-us__foundedOn"`
    ("2019"). A value that does not fit the record's patterns is dropped, so is a missing
    block; broken markup yields what was read before it."""
    parser = _AboutParser()
    parser.feed(html)
    parser.close()
    size = re.fullmatch(rf"({SIZE_CLASS_PATTERN[1:-1]})\s*employees", parser.values.get(
        ABOUT_SIZE, ""))
    return Facts(size[1] if size else None, _year(parser.values.get(ABOUT_FOUNDED)))


def parse_website(html: str) -> Facts:
    """The facts in the first schema.org `Organization` (or `Corporation`) of a page's JSON-LD
    that states any: `foundingDate` (its leading four-digit year) and `numberOfEmployees` (a
    count, or a `QuantitativeValue` with a `value`), mapped to LinkedIn's size classes. A range
    (`minValue`/`maxValue`) states no count and is dropped."""
    for node in _organizations(json_ld_documents(html)):
        facts = Facts(_size_class(node.get("numberOfEmployees")),
                      _year(node.get("foundingDate")))
        if facts:
            return facts
    return Facts()


def _year(value: object) -> int | None:
    match = re.match(r"\d{4}(?!\d)", value.strip()) if isinstance(value, str) else None
    return int(match[0]) if match and int(match[0]) >= 1000 else None


def _size_class(value: object) -> str | None:
    if isinstance(value, dict):
        value = value.get("value")
    if isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
        value = int(value)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        return None
    return next((name for limit, name in SIZE_CLASSES if value <= limit), OPEN_CLASS)


def _organizations(node: object):
    """Every dict in a JSON-LD document (lists and `@graph` followed) typed as an organization."""
    if isinstance(node, list):
        for item in node:
            yield from _organizations(item)
    elif isinstance(node, dict):
        kinds = node.get("@type")
        if ORGANIZATION_TYPES & set(kinds if isinstance(kinds, list) else [kinds]):
            yield node
        yield from _organizations(node.get("@graph", []))


class _AboutParser(HTMLParser):
    """Collects the text of the first `<dd>` under each about-block marker, by marker. A `<dd>`
    ends at its end tag, the next `<dd>` or the next marker, since the markup may omit tags."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.values: dict[str, str] = {}
        self._key: str | None = None
        self._in_dd = False
        self._text = ""

    def _flush(self) -> None:
        if self._in_dd and self._key and self._key not in self.values:
            self.values[self._key] = " ".join(self._text.split())
        self._in_dd, self._text = False, ""

    def handle_starttag(self, tag, attrs):
        marker = dict(attrs).get("data-test-id")
        if marker in (ABOUT_SIZE, ABOUT_FOUNDED):
            self._flush()
            self._key = marker
            self._in_dd = tag == "dd"
        elif tag == "dd" and self._key:
            self._flush()
            self._in_dd = True

    def handle_endtag(self, tag):
        if tag == "dd":
            self._flush()

    def handle_data(self, data):
        if self._in_dd:
            self._text += data

    def close(self):
        super().close()
        self._flush()
