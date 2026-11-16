"""The alert-mail finder (`openspec/changes/alert-mail-intake/design.md`): the postings a pasted
job alert mail lists, as title and cleaned link, read by fixed link rules or, for other senders,
by the intake model choosing link numbers. Nothing is fetched here."""

import ipaddress
import re
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlsplit

from jobadvaisor.intake.bundesagentur import reference_number
from jobadvaisor.intake.links import linkedin_job_id, strip_query

CAREER_SITE_PATH = re.compile(r"^/job/[^/]+/\d+(?:-[a-z]{2}_[A-Z]{2})?/?$")
BLOCK_TAGS = {"p", "div", "li", "ul", "ol", "br", "tr", "td", "th", "table", "section", "article",
              "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "center"}
SKIPPED_TAGS = {"script", "style", "head", "title", "template", "noscript"}
TEXT_URL = re.compile(r"https?://[^\s<>\"')\]]+")


@dataclass(frozen=True)
class Link:
    """A link in a mail: `url` as the mail has it, `text` its visible text or, when it has
    none, its image's `alt`, and `image_only` when the text comes from that `alt`."""

    url: str
    text: str
    image_only: bool


@dataclass(frozen=True)
class Rule:
    """A fixed link rule: `match` gives a link's posting key or `None`, `canonical` the posting's
    URL for a key."""

    name: str
    match: Callable[[str], str | None]
    canonical: Callable[[str], str]


def _career_site_key(url: str) -> str | None:
    parts = urlsplit(url)
    if not CAREER_SITE_PATH.match(parts.path) or "refid" not in {
            name.lower() for name, _ in parse_qsl(parts.query, keep_blank_values=True)}:
        return None
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


RULES = (
    Rule("linkedin", linkedin_job_id, lambda key: f"https://www.linkedin.com/jobs/view/{key}"),
    Rule("bundesagentur", reference_number,
         lambda key: f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{key}"),
    Rule("career_site", _career_site_key, lambda key: key),
)


def rule_for(url: str) -> tuple[Rule, str] | None:
    """The first rule that reads `url`, with the posting key it gives, or `None`."""
    for rule in RULES:
        try:
            key = rule.match(url)
        except ValueError:
            key = None
        if key:
            return rule, key
    return None


def clean_link(url: str) -> str:
    """`url` without personal parameters: a rule's canonical URL when a rule reads it, else
    `strip_query(url)`."""
    found = rule_for(url)
    return found[0].canonical(found[1]) if found else strip_query(url)


def read_mail(html: str | None, text: str) -> list[str | Link]:
    """The mail as an ordered stream of text blocks (`str`) and links: from `html` when it is
    not `None`, else from the plain `text`. Only absolute http(s) links on public hosts stay
    links; any other link's text stays as a text block."""
    items = _from_html(html) if html is not None else _from_text(text)
    out: list[str | Link] = []
    for item in items:
        if isinstance(item, Link) and not public_link(item.url):
            item = item.text
        if item:
            out.append(item)
    return out


def public_link(url: str) -> bool:
    """Whether `url` is an absolute http(s) address on a public host: not `localhost`, not a
    single-label host, and no IP literal in a loopback, private, link-local or reserved range."""
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").rstrip(".").lower()
    except ValueError:
        return False
    if parts.scheme.lower() not in ("http", "https") or not host:
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return "." in host and host != "localhost" and not host.endswith(".localhost")


def _clean(text: str) -> str:
    return " ".join(text.replace("\xad", "").split())


def _from_text(text: str) -> list[str | Link]:
    """Plain text: each URL is a link. Its text is what precedes it on its line, or else the
    first line of its block: the lines after the previous URL, restarted after a line ending
    in `:` or `,` (an intro or a greeting). Alert mails put the title first and further
    details between it and the URL."""
    items: list[str | Link] = []
    block: list[str] = []
    for raw in text.splitlines():
        line = _clean(raw)
        if not line:
            continue
        found = list(TEXT_URL.finditer(line))
        if not found:
            items.append(line)
            block = [] if line.endswith((":", ",")) else block + [line]
            continue
        before = line[:found[0].start()].strip()
        for match in found:
            items.append(Link(match.group(0), before or (block[0] if block else ""), False))
        block = []
    return items


def _from_html(html: str) -> list[str | Link]:
    parser = _MailParser()
    parser.feed(html)
    parser.close()
    return parser.items()


class _MailParser(HTMLParser):
    """Text blocks and links in mail order. Text inside a link belongs to that link (and to
    every link around it: some senders nest a title link inside a card link)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._items: list = [""]
        self._open: list[dict] = []
        self._skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIPPED_TAGS:
            self._skipping += 1
        if tag in BLOCK_TAGS:
            self._break()
        if tag == "a":
            anchor = {"href": dict(attrs).get("href") or "", "text": "", "alt": ""}
            self._open.append(anchor)
            self._items += [anchor, ""]
        if tag == "img" and self._open:
            for anchor in self._open:
                anchor["alt"] = anchor["alt"] or (dict(attrs).get("alt") or "")

    def handle_endtag(self, tag):
        if tag in SKIPPED_TAGS:
            self._skipping = max(0, self._skipping - 1)
        if tag == "a" and self._open:
            self._open.pop()
        if tag in BLOCK_TAGS:
            self._break()

    def _break(self):
        if self._open:
            for anchor in self._open:
                anchor["text"] += " "
        else:
            self._items.append("")

    def handle_data(self, data):
        if self._skipping:
            return
        if self._open:
            for anchor in self._open:
                anchor["text"] += data
        else:
            self._items[-1] += data

    def items(self) -> list[str | Link]:
        out = []
        for item in self._items:
            if isinstance(item, dict):
                text = _clean(item["text"])
                out.append(Link(item["href"].strip(), text or _clean(item["alt"]), not text
                                and bool(_clean(item["alt"]))))
            elif _clean(item):
                out.append(_clean(item))
        return out
