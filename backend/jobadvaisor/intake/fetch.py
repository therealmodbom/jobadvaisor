"""The fetch ladder's general fetchers (`design.md` → Intake): a plain HTTP fetch reading
schema.org `JobPosting` JSON-LD, and Playwright Chromium for script-rendered pages."""

import json
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from html.parser import HTMLParser
from typing import TYPE_CHECKING
from urllib.parse import urldefrag, urljoin, urlsplit

import httpx

from jobadvaisor.data.models import ClosedRule
from jobadvaisor.intake.links import navigation_allowed, public_link

if TYPE_CHECKING:  # company_facts imports this module, so the class is named for typing only
    from jobadvaisor.intake.company_facts import Throttle

# The throttle of the alert run being worked on (`alert_runs.AlertRuns`), set like `guarded_link`:
# every request of the run's intake waits on it for its host. `None` outside a run.
host_throttle: ContextVar["Throttle | None"] = ContextVar("host_throttle", default=None)

# The cleaned link of the alert-mail entry being added (`design.md` → Cleaning): a fetch that
# starts at it checks every redirect hop with `navigation_allowed` before requesting it.
guarded_link: ContextVar[str | None] = ContextVar("guarded_link", default=None)
REFUSED_REDIRECT = "redirect with personal parameters"
REFUSED_HOST = "redirect to a non-public address"
MAX_REDIRECTS = 10

# The rules that tell a closed posting page from an open one. The policy pack's rules add to
# these (`ladder.closed_rules`). The default is not touched by a caller, who sets a copy.
DEFAULT_CLOSED_RULES = [
    ClosedRule(host="linkedin.com", redirect_marker="trk=expired_jd_redirect")]
# The rules in force for the fetches of the current thread, set like `guarded_link`.
closed_rules: ContextVar[list[ClosedRule]] = ContextVar(
    "closed_rules", default=DEFAULT_CLOSED_RULES)
CLOSED_REDIRECT = "closed page (redirect)"
CLOSED_TEXT = "closed page (page text)"

MIN_PAGE_TEXT = 600  # characters; less is a teaser, a portal entry, a cookie wall or a challenge
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")
TIMEOUT_SECONDS = 20
SKIPPED_TAGS = {"script", "style", "noscript", "template", "svg", "head", "nav", "header",
                "footer", "label", "button", "select", "option", "textarea"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
             "source", "track", "wbr"}
CONSENT_MARK = re.compile(r"(?i)cookie|consent|gdpr|\bcmp")
BLOCK_TAGS = {"p", "div", "li", "ul", "ol", "br", "tr", "section", "article", "main", "h1", "h2",
              "h3", "h4", "h5", "h6", "dt", "dd", "table", "blockquote", "pre"}
# LinkedIn guest page: CSS class of an element -> what it holds; the first such element counts.
# The posting text is `LINKEDIN_TEXT_PARTS` in page order; the rest are the header's fields.
LINKEDIN_CLASSES = {"compensation": "pay", "description__text": "description",
                    "description__job-criteria-list": "criteria",
                    "top-card-layout__title": "title", "topcard__org-name-link": "company",
                    "topcard__flavor--bullet": "location_raw"}
LINKEDIN_TEXT_PARTS = ("pay", "description", "criteria")


class FetchError(Exception):
    """A fetch step yields no posting; the message is the reason shown in the attempts.
    `earlier` holds the failure texts of the attempts that came before the final one (a plain
    fetch's retry: `("HTTP 429",)`), oldest first; empty for a single attempt."""

    def __init__(self, reason: str, earlier: tuple[str, ...] = ()):
        super().__init__(reason)
        self.earlier = earlier


@dataclass(frozen=True)
class Page:
    """Posting text from one page. `url` is the address after redirects; `supplied` holds the
    title, company and location_raw the page's JSON-LD names (only those it names).
    `company_url` is the employer's LinkedIn company page (`https://www.linkedin.com/company/
    <slug>`) when the page is a LinkedIn guest page that links to one, else `None`. `closed` is
    true when a closed rule's text marker matches the page although it holds posting text."""

    url: str
    text: str
    supplied: dict[str, str] = field(default_factory=dict)
    company_url: str | None = None
    closed: bool = False
    earlier: tuple[str, ...] = ()  # failures of the attempts before the one that gave this page


class Download(tuple):
    """What `download_plain` returns: the `(final_url, html)` pair, so a caller can unpack two
    values, plus `earlier`, the failure texts of the attempts before the successful one (a
    retry's first answer, `("HTTP 429",)`); empty when the first attempt succeeded."""

    earlier: tuple[str, ...]

    def __new__(cls, final_url: str, html: str, earlier: tuple[str, ...] = ()):
        download = super().__new__(cls, (final_url, html))
        download.earlier = earlier
        return download


def fetch_plain(url: str, http: httpx.Client | None = None) -> Page:
    """Fetch `url` over HTTP (`download_plain`) and read its posting (`page_from_html`). The
    failures of the attempts before the successful one are `Page.earlier`, or `FetchError.earlier`
    when the page holds no posting. Raises `FetchError` naming the failure."""
    download = download_plain(url, http)
    earlier = getattr(download, "earlier", ())
    try:
        page = page_from_html(*download)
    except FetchError as error:
        raise FetchError(str(error), (*earlier, *error.earlier)) from None
    return replace(page, earlier=earlier)


def fetch_rendered(url: str) -> Page:
    """Render `url` in Chromium (`download_rendered`) and read its posting (`page_from_html`).
    Raises `FetchError` naming the failure."""
    return page_from_html(*download_rendered(url))


def url_host(url: str) -> str:
    """`url`'s host in lower case, or `""` when it has none or does not parse (a stored link
    is not validated, so `http://[bad` must not raise)."""
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def host_matches(url: str, host: str) -> bool:
    """Whether `url`'s host is `host` or a subdomain of it; never for a link that does not
    parse."""
    actual = url_host(url)
    return bool(actual) and (actual == host or actual.endswith("." + host))


def closed_redirect(address: str, rules: list[ClosedRule] | None = None) -> bool:
    """Whether a redirect hop to `address` matches a redirect marker, among `rules` (default:
    the `closed_rules` in force) of its host: the hop is a closed page's redirect and must not
    be requested."""
    return any(rule.redirect_marker and host_matches(address, rule.host)
               and rule.redirect_marker in address
               for rule in (closed_rules.get() if rules is None else rules))


def closed_by_text(url: str, html: str) -> bool:
    """Whether a text marker of the `closed_rules` in force for `url`'s host occurs, ignoring
    case, in the visible text of `html` (`html_text`: no scripts, styles or navigation)."""
    return _closed_text(url, html_text(html))


def _closed_text(url: str, text: str) -> bool:
    text = text.casefold()
    return any(rule.text_marker and host_matches(url, rule.host)
               and rule.text_marker.casefold() in text for rule in closed_rules.get())


def download_plain(url: str, http: httpx.Client | None = None, *,
                   retry: bool = True) -> "Download":
    """The address after redirects and the HTML of `url` over HTTP, retrying once after a
    transport error or a 429/5xx answer unless `retry` is false (one request, whatever the
    answer). A retry that succeeds still names the failure of the first attempt
    (`Download.earlier`). A redirect hop that matches a closed rule's redirect marker is not sent
    (`FetchError(CLOSED_REDIRECT)`), whatever the link. While `guarded_link` is `url`, a hop
    other than `url` itself that fails `navigation_allowed` is not sent either
    (`FetchError(REFUSED_REDIRECT)`), after the closed question; `url` is sent as it is.
    Waits on the `host_throttle` in force before every request it sends: the first, the retry
    and each redirect hop, on the hop's own host (a refused hop takes no slot). Raises
    `FetchError` naming the failure of the last attempt; `FetchError.earlier` lists the
    failures of the attempts before it (a 429 before a 404 reads as `("HTTP 429",)`)."""
    require_http(url)
    http = http or httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True,
                                headers={"User-Agent": USER_AGENT})
    check = _check_hop if guarded_link.get() == url else _check_closed_hop
    with request_hooks(http, check, _wait_before_request):
        return _download_plain(url, http, retry)


@contextmanager
def request_hooks(http: httpx.Client, *hooks: Callable[[httpx.Request], None]) -> Iterator[None]:
    """Run `hooks` before every request `http` sends (each redirect hop included), after its own
    request hooks, until the block ends."""
    original = http.event_hooks
    http.event_hooks = {**original, "request": [*original.get("request", []), *hooks]}
    try:
        yield
    finally:
        http.event_hooks = original


def _refusal(url: str, start: str | None) -> str | None:
    """Why a hop to `url` must not be sent (`REFUSED_HOST`, `REFUSED_REDIRECT`), or `None`. The
    guarded start link `start` itself is exempt from both rules: the caller chose it (the API
    checked it, or a check read it from the posting), whatever parameters it carries. It is
    compared in httpx's normal form, since the request URL has its host lower-cased and a
    default port dropped while the stored link may not."""
    if start and _same_link(url, start):
        return None
    if not public_link(url):
        return REFUSED_HOST
    return None if navigation_allowed(url) else REFUSED_REDIRECT


def _same_link(a: str, b: str) -> bool:
    try:
        return httpx.URL(a) == httpx.URL(b)
    except httpx.InvalidURL:
        return a == b


def _check_closed_hop(request: httpx.Request) -> None:
    if closed_redirect(str(request.url)):
        raise FetchError(CLOSED_REDIRECT)


def _check_hop(request: httpx.Request) -> None:
    _check_closed_hop(request)
    if reason := _refusal(str(request.url), guarded_link.get()):
        raise FetchError(reason)


def _wait_before_request(request: httpx.Request) -> None:
    _wait_for_host(str(request.url))


def _wait_for_host(url: str) -> None:
    """Wait on the `host_throttle` in force, if any, for `url`'s host before a request to it."""
    if throttle := host_throttle.get():
        throttle.wait(url_host(url))


def _download_plain(url: str, http: httpx.Client, retry: bool) -> "Download":
    attempts = 2 if retry else 1
    earlier: list[str] = []  # the failure texts of the attempts so far
    for attempt in range(1, attempts + 1):
        try:
            response = http.get(url)
        except FetchError as error:  # a refused redirect hop, raised by a request hook
            raise FetchError(str(error), (*earlier, *error.earlier)) from None
        except httpx.InvalidURL:
            raise FetchError("invalid URL", tuple(earlier)) from None
        except httpx.HTTPError as error:
            failure = f"connection failed: {type(error).__name__}"
            if attempt == attempts:
                raise FetchError(failure, tuple(earlier)) from None
            earlier.append(failure)
            continue
        if response.status_code == 200:
            return Download(str(response.url), response.text, tuple(earlier))
        failure = f"HTTP {response.status_code}"
        if (response.status_code == 429 or response.status_code >= 500) and attempt < attempts:
            earlier.append(failure)
            continue
        raise FetchError(failure, tuple(earlier))
    raise AssertionError("unreachable")


def download_rendered(url: str) -> tuple[str, str]:
    """The address after redirects and the HTML of `url` rendered in headless Chromium until
    the network is idle. A main-frame navigation that matches a closed rule's redirect marker
    is aborted before it is sent (`FetchError(CLOSED_REDIRECT)`), whatever the link. While
    `guarded_link` is `url`, one that fails `_refusal` is aborted too (`FetchError(
    REFUSED_REDIRECT)` or `REFUSED_HOST`). Waits on the `host_throttle` once before the
    navigation; the browser's own subresource requests are not counted. Raises `FetchError`
    naming the failure; a main-frame answer other than 200 is `HTTP <status>`, as in the plain
    fetch."""
    require_http(url)
    _wait_for_host(url)
    from playwright.sync_api import Error, sync_playwright

    refused, hops = [], []
    start, rules = guarded_link.get(), closed_rules.get()  # read here: the route callback
    # does not run in this context, so it would see the defaults
    guarded = start == url

    def blocked(address: str) -> str | None:
        """Why a navigation to `address` must not be sent: closed first, then guarded."""
        if closed_redirect(address, rules):
            return CLOSED_REDIRECT
        return _refusal(address, start) if guarded else None

    def check(route):
        """Chromium follows a server redirect without routing its target, so a main-frame
        navigation is fetched without redirects here: a refused target is never sent, and a
        clean one ends this navigation and is opened as a new one (`hops`), routed in turn."""
        request = route.request
        if not request.is_navigation_request() or request.frame.parent_frame is not None:
            route.continue_()
            return
        if reason := blocked(request.url):
            refused.append(reason)
            route.abort()
            return
        response = route.fetch(max_redirects=0)
        location = response.headers.get("location")
        if not (300 <= response.status < 400 and location):
            route.fulfill(response=response)
            return
        target = urljoin(request.url, location)
        if reason := blocked(target):
            refused.append(reason)
            route.abort()
            return
        hops.append(target)
        route.fulfill(status=200, content_type="text/html", body="")  # ends this navigation

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                tab = browser.new_page(user_agent=USER_AGENT)
                tab.route("**/*", check)
                target = url
                for _ in range(MAX_REDIRECTS + 1):
                    hops.clear()
                    try:
                        response = tab.goto(target, wait_until="networkidle",
                                            timeout=TIMEOUT_SECONDS * 1000)
                    except Error:
                        if refused:
                            raise FetchError(refused[0]) from None
                        raise
                    if not hops:
                        break
                    target = hops[0]
                else:
                    raise FetchError("too many redirects")
                if refused:
                    raise FetchError(refused[0])
                if response is not None and response.status != 200:  # like the plain fetch
                    raise FetchError(f"HTTP {response.status}")
                html, final_url = tab.content(), tab.url
            finally:
                browser.close()
    except Error as error:
        raise FetchError(f"browser failed: {str(error).splitlines()[0]}") from None
    return final_url, html


def require_http(url: str) -> None:
    """Raise `FetchError("invalid URL")` unless `url` is an http(s) address: a browser would
    otherwise read `file://` paths, and a model chooses many of the URLs fetched here."""
    if urlsplit(url).scheme.lower() not in ("http", "https"):
        raise FetchError("invalid URL")


def page_links(url: str, html: str) -> list[tuple[str, str]]:
    """Every link in a page with its text, as `(text, absolute http(s) URL)`, first occurrence
    of each URL only, navigation and footer included (careers links often sit there). A plain
    `#anchor` is dropped; a hash route (`#/…`, `#!…`) is kept, since it names another page."""
    parser = _PageParser()
    parser.feed(html)
    links = {}
    for text, href in parser.links:
        absolute, fragment = urldefrag(urljoin(url, href))
        if fragment.startswith(("/", "!")):  # a hash route names another page of an app
            absolute += f"#{fragment}"
        if absolute.startswith(("http://", "https://")) and absolute not in links:
            links[absolute] = " ".join(text.split())
    return [(text, href) for href, text in links.items()]


def page_from_html(url: str, html: str) -> Page:
    """The posting in a page: the fields of its first JSON-LD `JobPosting` as supplied values,
    and as text that posting's description, or the page's visible main text when the
    description is shorter than `MIN_PAGE_TEXT` (a teaser). A LinkedIn page without such a
    description but with its own description element gives the employer's pay range, that
    description and the criteria block, of any length, with the header's title, company and
    location as supplied values; the rest of the page is chrome. A closed rule's text marker
    (`closed_by_text`) is checked first: with posting text the `Page` has `closed` set, without
    it `FetchError(CLOSED_TEXT)` is raised. Raises `FetchError` ("no posting text") when no
    text qualifies."""
    parser = _PageParser()
    parser.feed(html)
    closed = _closed_text(url, parser.text())
    postings = parser.job_postings()
    supplied = _json_ld_fields(postings[0]) if postings else {}
    description = html_text(str(postings[0].get("description") or "")) if postings else ""
    company_url = linkedin_company_url(parser.company_href) if is_linkedin(url) else None
    if len(description) < MIN_PAGE_TEXT and is_linkedin(url) and parser.captured("description"):
        header = {name: " ".join(parser.captured(name).split())
                  for name in ("title", "company", "location_raw") if parser.captured(name)}
        body = "\n".join(filter(None, map(parser.captured, LINKEDIN_TEXT_PARTS)))
        return Page(url, body, header | supplied, company_url, closed)
    for text in (description, parser.text()):
        if len(text) >= MIN_PAGE_TEXT:
            return Page(url, text, supplied, company_url, closed)
    raise FetchError(CLOSED_TEXT if closed else "no posting text")


def json_ld_documents(html: str) -> list[object]:
    """Every `application/ld+json` block of a page that parses as JSON, in page order; blocks
    that do not parse are left out."""
    parser = _PageParser()
    parser.feed(html)
    documents = []
    for body in parser._json_ld:
        try:
            documents.append(json.loads(body))
        except json.JSONDecodeError:
            continue
    return documents


def html_text(html: str) -> str:
    """The visible text of an HTML fragment, one line per block, without scripts, styles,
    navigation, header or footer."""
    parser = _PageParser()
    parser.feed(html)
    return parser.text()


def is_linkedin(url: str) -> bool:
    """Whether `url`'s host is linkedin.com or one of its subdomains."""
    host = (urlsplit(url).hostname or "").lower()
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def linkedin_company_url(href: str | None) -> str | None:
    """`href` as the plain company page `https://www.linkedin.com/company/<slug>` (query, fragment
    and country subdomain dropped), or `None` when it is no http(s) link to a LinkedIn company."""
    if not href:
        return None
    parts = urlsplit(href.strip())
    segments = parts.path.split("/")
    if parts.scheme not in ("http", "https") or not is_linkedin(href) \
            or segments[:2] != ["", "company"] or len(segments) < 3 or not segments[2]:
        return None
    return f"https://www.linkedin.com/company/{segments[2]}"


class _PageParser(HTMLParser):
    """Collects visible text by block, links with their text, the bodies of JSON-LD scripts,
    and the text inside the `LINKEDIN_CLASSES` elements (`captured`)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._lines, self._json_ld, self._skipping = [""], [], []
        self._in_json_ld = False
        self.links: list[list[str]] = []
        self.company_href: str | None = None  # href of the first `topcard__org-name-link`
        self._anchor: list[str] | None = None
        self._lines_of: dict[str, list[str]] = {}
        # ponytail: counts same-name tags to find the container's end; fine for the guest
        # page's well-formed markup, a stray unclosed <div> inside one would run it on.
        self._open: list[list] = []  # [capture name, container tag, nesting depth]

    def captured(self, name: str) -> str:
        """The text inside the elements captured as `name`, one line per block."""
        return "\n".join(line for line in (" ".join(raw.split())
                                           for raw in self._lines_of.get(name, [])) if line)

    def _break(self):
        self._lines.append("")
        for name, _, _ in self._open:
            self._lines_of[name].append("")

    def handle_starttag(self, tag, attrs):
        for capture in self._open:
            capture[2] += tag == capture[1]
        name = next((LINKEDIN_CLASSES[c] for c in (dict(attrs).get("class") or "").split()
                     if c in LINKEDIN_CLASSES), None)
        if name and tag not in VOID_TAGS and name not in self._lines_of:
            self._open.append([name, tag, 1])
            self._lines_of[name] = [""]
        if tag == "a" and (href := dict(attrs).get("href")):
            self._anchor = ["", href]
            self.links.append(self._anchor)
            if self.company_href is None and "topcard__org-name-link" in (
                    dict(attrs).get("class") or "").split():
                self.company_href = href
        if tag == "script" and dict(attrs).get("type") == "application/ld+json":
            self._in_json_ld = True
            self._json_ld.append("")
        if tag == "body" and "head" in self._skipping:  # `</head>` may be omitted
            del self._skipping[self._skipping.index("head"):]
        if tag in SKIPPED_TAGS or (tag not in VOID_TAGS and _is_consent_dialog(attrs)):
            self._skipping.append(tag)
        if tag in BLOCK_TAGS:
            self._break()

    def handle_endtag(self, tag):
        if tag == "a":
            self._anchor = None
        if tag == "script":
            self._in_json_ld = False
        if tag in self._skipping:  # also closes skipped tags left open inside it
            del self._skipping[len(self._skipping) - 1 - self._skipping[::-1].index(tag):]
        if tag in BLOCK_TAGS:
            self._break()
        for capture in self._open:
            capture[2] -= tag == capture[1]
        self._open = [capture for capture in self._open if capture[2] > 0]

    def handle_data(self, data):
        if self._anchor is not None:
            self._anchor[0] += data
        if self._in_json_ld:
            self._json_ld[-1] += data
        elif not self._skipping:
            self._lines[-1] += data
            for name, _, _ in self._open:
                self._lines_of[name][-1] += data

    def text(self) -> str:
        return "\n".join(line for line in (" ".join(raw.split()) for raw in self._lines) if line)

    def job_postings(self) -> list[dict]:
        found = []
        for body in self._json_ld:
            try:
                _collect_job_postings(json.loads(body), found)
            except json.JSONDecodeError:
                continue
        return found


def _is_consent_dialog(attrs: list[tuple[str, str | None]]) -> bool:
    """Whether an element's id, class or attribute names mark a cookie or consent dialog,
    whose vendor lists can outweigh the posting itself."""
    marks = " ".join(f"{name} {value or ''}" for name, value in attrs
                     if name in ("id", "class") or name.startswith("data-"))
    return bool(CONSENT_MARK.search(marks))


def _collect_job_postings(node: object, found: list[dict]) -> None:
    if isinstance(node, list):
        for item in node:
            _collect_job_postings(item, found)
    elif isinstance(node, dict):
        kind = node.get("@type")
        if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
            found.append(node)
        _collect_job_postings(node.get("@graph", []), found)


def _json_ld_fields(posting: dict) -> dict[str, str]:
    organization = posting.get("hiringOrganization")
    if isinstance(organization, dict):
        organization = organization.get("name")
    places = posting.get("jobLocation") or []
    locations = [_place(place) for place in (places if isinstance(places, list) else [places])]
    if "TELECOMMUTE" in str(posting.get("jobLocationType", "")).upper():
        locations.append("Remote")
    fields = {"title": posting.get("title"), "company": organization,
              "location_raw": "; ".join(dict.fromkeys(filter(None, locations)))}
    return {name: " ".join(value.split()) for name, value in fields.items()
            if isinstance(value, str) and value.strip()}


def _place(place: object) -> str:
    address = place.get("address") if isinstance(place, dict) else place
    if isinstance(address, str):
        return address.strip()
    if not isinstance(address, dict):
        return ""
    country = address.get("addressCountry")
    if isinstance(country, dict):
        country = country.get("name")
    parts = (address.get("addressLocality") or address.get("addressRegion"), country)
    return ", ".join(part.strip() for part in parts if isinstance(part, str) and part.strip())
