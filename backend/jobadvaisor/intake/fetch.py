"""The fetch ladder's general fetchers (`design.md` → Intake): a plain HTTP fetch reading
schema.org `JobPosting` JSON-LD, and Playwright Chromium for script-rendered pages."""

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit

import httpx

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
    """A fetch step yields no posting; the message is the reason shown in the attempts."""


@dataclass(frozen=True)
class Page:
    """Posting text from one page. `url` is the address after redirects; `supplied` holds the
    title, company and location_raw the page's JSON-LD names (only those it names).
    `company_url` is the employer's LinkedIn company page (`https://www.linkedin.com/company/
    <slug>`) when the page is a LinkedIn guest page that links to one, else `None`."""

    url: str
    text: str
    supplied: dict[str, str] = field(default_factory=dict)
    company_url: str | None = None


def fetch_plain(url: str, http: httpx.Client | None = None) -> Page:
    """Fetch `url` over HTTP (`download_plain`) and read its posting (`page_from_html`).
    Raises `FetchError` naming the failure."""
    return page_from_html(*download_plain(url, http))


def fetch_rendered(url: str) -> Page:
    """Render `url` in Chromium (`download_rendered`) and read its posting (`page_from_html`).
    Raises `FetchError` naming the failure."""
    return page_from_html(*download_rendered(url))


def download_plain(url: str, http: httpx.Client | None = None) -> tuple[str, str]:
    """The address after redirects and the HTML of `url` over HTTP, retrying once after a
    transport error or a 429/5xx answer. Raises `FetchError` naming the failure."""
    require_http(url)
    http = http or httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True,
                                headers={"User-Agent": USER_AGENT})
    for attempt in (1, 2):
        try:
            response = http.get(url)
        except httpx.InvalidURL:
            raise FetchError("invalid URL") from None
        except httpx.HTTPError as error:
            if attempt == 2:
                raise FetchError(f"connection failed: {type(error).__name__}") from None
            continue
        if response.status_code == 429 or response.status_code >= 500:
            if attempt == 2:
                raise FetchError(f"HTTP {response.status_code}")
            continue
        if response.status_code != 200:
            raise FetchError(f"HTTP {response.status_code}")
        return str(response.url), response.text
    raise AssertionError("unreachable")


def download_rendered(url: str) -> tuple[str, str]:
    """The address after redirects and the HTML of `url` rendered in headless Chromium until
    the network is idle. Raises `FetchError` naming the failure."""
    require_http(url)
    from playwright.sync_api import Error, sync_playwright

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                tab = browser.new_page(user_agent=USER_AGENT)
                response = tab.goto(url, wait_until="networkidle",
                                    timeout=TIMEOUT_SECONDS * 1000)
                if response is not None and response.status >= 400:
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
    location as supplied values; the rest of the page is chrome. Raises `FetchError` ("no
    posting text") when no text qualifies."""
    parser = _PageParser()
    parser.feed(html)
    postings = parser.job_postings()
    supplied = _json_ld_fields(postings[0]) if postings else {}
    description = html_text(str(postings[0].get("description") or "")) if postings else ""
    company_url = linkedin_company_url(parser.company_href) if is_linkedin(url) else None
    if len(description) < MIN_PAGE_TEXT and is_linkedin(url) and parser.captured("description"):
        header = {name: " ".join(parser.captured(name).split())
                  for name in ("title", "company", "location_raw") if parser.captured(name)}
        body = "\n".join(filter(None, map(parser.captured, LINKEDIN_TEXT_PARTS)))
        return Page(url, body, header | supplied, company_url)
    for text in (description, parser.text()):
        if len(text) >= MIN_PAGE_TEXT:
            return Page(url, text, supplied, company_url)
    raise FetchError("no posting text")


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
