"""The alert-mail finder
(`openspec/changes/archive/2026-11-16-alert-mail-intake/design.md`): the postings a pasted
job alert mail lists, as title and cleaned link, read by fixed link rules or, for other senders,
by the intake model choosing link numbers. Nothing is fetched here."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from jobadvaisor.intake.bundesagentur import reference_number
from jobadvaisor.intake.duplicates import normalize_url
from jobadvaisor.intake.ladder import is_login_walled, login_wall_hosts
from jobadvaisor.intake.links import linkedin_job_id, public_link, strip_query
from jobadvaisor.intake.postings import Intake, read_policy_pack
from jobadvaisor.tools.prompts import DATA_RULE, data_block

MAX_MODEL_TEXT = 30_000
MODEL_INSTRUCTIONS = (
    "You read one job alert mail. List every job posting it advertises, each with the number N "
    "of the link (#N) that leads to that posting and the posting's title as the mail states "
    "it. Leave out links to searches, settings, the sender's home page, profiles and social "
    "media. Answer an empty list when the mail advertises no posting. "
    + DATA_RULE.format(tag="mail"))
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
    URL for a key, `title` the posting's title from the texts of that key's links (image-only
    links and URL texts already left out), "" when none fits."""

    name: str
    match: Callable[[str], str | None]
    canonical: Callable[[str], str]
    title: Callable[[list[str]], str]


@dataclass(frozen=True)
class Entry:
    """A posting the mail lists: its cleaned link and title. `ambiguous` marks a link that does
    not tell this posting from another one, so it cannot be added by its link."""

    url: str
    title: str
    ambiguous: bool = False


@dataclass(frozen=True)
class Found:
    """What the finder read in a mail (design.md → API, preview answer):
    - `entries`: at most `MAX_ENTRIES`, in mail order; `truncated` when the mail held more;
    - `read_by`: the rules that read the mail, or `["model"]`, or empty;
    - `unread_hosts`: `{host, links}` for kept links no rule read, at most `MAX_UNREAD_HOSTS`;
    - `held`: the content guard flagged the mail; `model_skipped`: why no model read it;
    - `hosts`: every kept link's host with its count, for the record."""

    entries: list[Entry]
    read_by: list[str]
    unread_hosts: list[dict]
    truncated: bool = False
    held: bool = False
    model_skipped: str | None = None
    hosts: dict[str, int] = field(default_factory=dict)


MAX_ENTRIES = 100
MAX_UNREAD_HOSTS = 10
# Navigation and account links, by a word of their text or a part of their path (lowercased).
DROP_WORDS = {
    "unsubscribe", "abbestellen", "abmelden", "abmeldung", "abonnement", "optout", "settings",
    "einstellungen", "preferences", "präferenzen", "verwalten", "manage", "alert", "alerts",
    "jobalert", "benachrichtigungen", "notifications", "mitteilungen", "profil", "profile",
    "premium", "widget", "hilfe", "help", "faq", "datenschutz", "privacy", "impressum", "imprint",
    "agb", "terms", "browser", "webversion"}
DROP_PATHS = (
    "unsubscribe", "abbestell", "abmeld", "optout", "opt-out", "/settings", "einstellung",
    "preferences", "/alerts", "job-alert", "/suchauftrag", "/search", "/suche", "/profil", "/in/",
    "/feed", "/mynetwork", "/messaging", "/notifications", "/premium", "/widgets", "/help",
    "/hilfe", "/privacy", "/datenschutz", "/impressum", "/imprint", "/email/view", "/webversion",
    "/legal", "/terms", "/agb")
OPAQUE_SEGMENT = re.compile(r"[A-Za-z0-9_=.%~-]{20,}")
# A URL in a text: with a scheme, or without one when a path or query follows its host.
MASKED_URL = re.compile(r"(?i)https?://[^\s<>\"')\]]+"
                        r"|(?:www\.)?[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}[/?][^\s<>\"')\]]*")
URL_TEXT = re.compile(r"(?i)(https?://\S+|(www\.)?[\w-]+(\.[\w-]+)*\.[a-z]{2,}(/\S*)?)")


def opaque(segment: str) -> bool:
    """Whether a path segment looks like a token: at least 20 characters of `[A-Za-z0-9_=-]`
    with upper case, lower case and a digit, and fewer than three hyphens (word slugs pass)."""
    return bool(OPAQUE_SEGMENT.fullmatch(segment)) and segment.count("-") < 3 and all(
        any(test(c) for c in segment) for test in (str.isupper, str.islower, str.isdigit))


def dropped(link: Link) -> bool:
    """Whether `link` is a navigation, account or legal link, a home page, or has an opaque
    path segment (its path may itself be a token)."""
    path = unquote(urlsplit(link.url).path)
    words = set(re.findall(r"\w+", link.text.lower()))
    return (path in ("", "/") or bool(words & DROP_WORDS)
            or any(part in path.lower() for part in DROP_PATHS)
            or any(opaque(segment) for segment in path.split("/")))


def _linkedin_title(texts: list[str]) -> str:
    return next((text for text in texts if " · " not in text), "")


def _bundesagentur_title(texts: list[str]) -> str:
    return max((re.sub(r"^\d+\.\s*", "", text) for text in texts), key=len, default="")


def _career_site_title(texts: list[str]) -> str:
    return re.sub(r"\s+-\s+[^-]+,\s*[A-Z]{2}$", "", texts[0]) if texts else ""


def _career_site_key(url: str) -> str | None:
    parts = urlsplit(url)
    if not CAREER_SITE_PATH.match(parts.path) or "refid" not in {
            name.lower() for name, _ in parse_qsl(parts.query, keep_blank_values=True)}:
        return None
    return f"{parts.scheme}://{parts.netloc.rpartition('@')[2]}{parts.path}"


RULES = (
    Rule("linkedin", linkedin_job_id, lambda key: f"https://www.linkedin.com/jobs/view/{key}",
         _linkedin_title),
    Rule("bundesagentur", reference_number,
         lambda key: f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{key}",
         _bundesagentur_title),
    Rule("career_site", _career_site_key, lambda key: key, _career_site_title),
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


def find_postings(html: str | None, text: str, *, model, guard) -> Found:
    """The postings the mail (`read_mail`) lists. When any link matches a rule, the rules read
    the mail without a model call, and `unread_hosts` names the hosts of other kept links.
    Otherwise the `model` reads it behind the content `guard` (`_model_path`)."""
    items = read_mail(html, text)
    links = [item for item in items if isinstance(item, Link)]
    hosts: dict[str, int] = {}
    for link in links:
        host = _host(link.url)
        hosts[host] = hosts.get(host, 0) + 1
    matched = [(link, rule_for(link.url)) for link in links]
    if not any(found for _, found in matched):
        return _model_path(items, model, guard, hosts)
    groups: dict[tuple[str, str], list[Link]] = {}
    unread: dict[str, set[str]] = {}
    for link, found in matched:
        if found:
            groups.setdefault((found[0].name, found[1]), []).append(link)
        elif not dropped(link):
            unread.setdefault(_host(link.url), set()).add(strip_query(link.url))
    rules = {rule.name: rule for rule in RULES}
    entries = []
    for (name, key), group in groups.items():
        texts = [link.text for link in group
                 if link.text and not link.image_only and not URL_TEXT.fullmatch(link.text)]
        entries.append(Entry(rules[name].canonical(key), rules[name].title(texts)))
    return Found(entries[:MAX_ENTRIES], list(dict.fromkeys(name for name, _ in groups)),
                 [{"host": host, "links": len(urls)} for host, urls in sorted(unread.items())]
                 [:MAX_UNREAD_HOSTS], truncated=len(entries) > MAX_ENTRIES, hosts=hosts)


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


class FinderError(Exception):
    """The finder could not read the mail: "screening failed" or "finder failed" (a 502 the
    user can retry)."""


class _Pick(BaseModel):
    link: int = Field(description="The number N of the link (#N) that leads to the posting")
    title: str = Field(description="The posting's title as the mail states it")


class _Picks(BaseModel):
    postings: list[_Pick] = Field(description="Every job posting the mail lists, in mail order")


def model_view(items: list[str | Link]) -> tuple[str, list[Link]]:
    """The text the model reads, at most `MAX_MODEL_TEXT` characters, and its numbered links:
    each link the drop list keeps is written `[text](#N host/path)`, every other link as its
    text. Every URL in a text keeps its host and path only, with opaque segments as `…`. The
    view ends before the first item that no longer fits, so a link the model never sees has no
    number."""
    lines, numbered, size = [], [], 0
    for item in items:
        if isinstance(item, Link) and not dropped(item):
            line = f"[{_mask_urls(item.text)}](#{len(numbered) + 1} {_host_path(item.url)})"
            keep = True
        else:
            line = _mask_urls(item.text if isinstance(item, Link) else item)
            keep = False
        if not line:
            continue
        if size + len(line) + 1 > MAX_MODEL_TEXT:
            break
        lines.append(line)
        size += len(line) + 1
        if keep:
            numbered.append(item)
    return "\n".join(lines), numbered


def _host_path(url: str) -> str:
    parts = urlsplit(url)
    path = "/".join("…" if opaque(segment) else segment for segment in parts.path.split("/"))
    return f"{(parts.hostname or '').lower()}{path}"


def _mask_urls(text: str) -> str:
    def mask(match: re.Match) -> str:
        url = match.group(0)
        return _host_path(url if "://" in url else "//" + url)

    return MASKED_URL.sub(mask, text)


def _model_path(items: list[str | Link], model, guard, hosts: dict[str, int]) -> Found:
    """design.md → Model fallback: nothing to read after the drop list, screening off, held by
    the guard, or the `intake` model's picks grouped by cleaned link. Raises `FinderError`."""
    text, numbered = model_view(items)
    if not numbered:
        return Found([], [], [], hosts=hosts)
    if guard.classifier is None:
        return Found([], [], [], model_skipped="screening off", hosts=hosts)
    try:
        flagged = guard.screen(text).flagged
    except Exception:
        raise FinderError("screening failed") from None
    if flagged:
        return Found([], [], [], held=True, hosts=hosts)
    try:
        picks = model.with_structured_output(_Picks).invoke([
            SystemMessage(MODEL_INSTRUCTIONS), HumanMessage(data_block("mail", text))]).postings
    except Exception:
        raise FinderError("finder failed") from None
    groups: dict[str, list[tuple[int, str]]] = {}
    for pick in sorted(picks, key=lambda pick: pick.link):
        title = _clean(pick.title)
        if 1 <= pick.link <= len(numbered) and title and not URL_TEXT.fullmatch(title):
            groups.setdefault(clean_link(numbered[pick.link - 1].url), []).append(
                (pick.link, title))
    entries = []
    for url, picked in groups.items():
        titles = list(dict.fromkeys(title for _, title in picked))
        distinct = {" ".join(title.casefold().split()) for title in titles}
        entries += ([Entry(url, titles[0])] if len(distinct) == 1 else
                    [Entry(url, title, ambiguous=True) for title in titles])
    entries.sort(key=lambda entry: next(n for n, t in groups[entry.url] if t == entry.title))
    cut = len(numbered) < sum(isinstance(i, Link) and not dropped(i) for i in items)
    return Found(entries[:MAX_ENTRIES], ["model"], [], hosts=hosts,
                 truncated=len(entries) > MAX_ENTRIES or cut)


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
        if tag == "body":
            self._skipping = 0  # a head left open must not swallow the body
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


def _record(record: Path, line: dict) -> None:
    """Append `line` as JSON to `record`; a failed write is ignored (the record is a
    convenience for #109)."""
    try:
        record.parent.mkdir(parents=True, exist_ok=True)
        with record.open("a") as file:
            file.write(json.dumps(line) + "\n")
    except OSError:
        pass


def preview(intake: Intake, html: str | None, text: str, record: Path) -> dict:
    """The preview answer for a pasted mail (design.md → API, without `screening`): the
    finder's entries, each with the stored posting that has its link (`duplicate`) and whether
    its host is login-walled. The stored postings are read once. One line per preview is
    appended to `record` (design.md → Record for #109), a `failed` line when the finder fails;
    a failed write is ignored. Raises `FinderError`."""
    try:
        found = find_postings(html, text, model=intake.model, guard=intake.guard)
    except FinderError as error:
        _record(record, {"at": datetime.now(UTC).isoformat(), "failed": str(error)})
        raise
    postings = intake.postings()
    by_key = {normalize_url(url): posting_id
              for posting_id, posting in postings.items() for url in posting.urls}
    walled = login_wall_hosts(read_policy_pack(intake.root))
    entries = []
    for entry in found.entries:
        posting_id = by_key.get(normalize_url(entry.url))
        entries.append({
            "url": entry.url, "title": entry.title, "ambiguous": entry.ambiguous,
            "duplicate": {"posting_id": posting_id, "title": postings[posting_id].title}
            if posting_id else None,
            "login_walled": is_login_walled(entry.url, walled)})
    line = {"at": datetime.now(UTC).isoformat(), "read_by": found.read_by, "hosts": found.hosts,
            "entries": len(found.entries), "held": found.held,
            "model_skipped": found.model_skipped}
    _record(record, line)
    return {"entries": entries, "read_by": found.read_by, "unread_hosts": found.unread_hosts,
            "held": found.held, "model_skipped": found.model_skipped,
            "truncated": found.truncated}
