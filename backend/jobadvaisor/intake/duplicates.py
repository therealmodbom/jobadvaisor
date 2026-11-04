"""Duplicate detection for intake (`design.md` → Intake): a normalized URL, then a text hash,
then the share of word sequences two texts have in common."""

import hashlib
import re
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit

from jobadvaisor.data.models import Posting
from jobadvaisor.intake.bundesagentur import reference_number

SHINGLE_WORDS = 5
CONTAINMENT_THRESHOLD = 0.8  # demo persona: distinct postings reach 0.758, see `design.md`
MIN_SHINGLES = 40  # shorter texts (teasers) are compared by hash only
MIN_OVERLAP = 0.6  # of the longer text, so a short text inside a long one is no duplicate
TRACKING_PARAMETERS = re.compile(
    r"^(utm_.*|gclid|fbclid|msclkid|mc_cid|mc_eid|trk|trackingid|refid|ref|src|source)$")

Reason = Literal["url", "text", "similar_text"]


def normalize_url(url: str) -> str:
    """A comparison key for `url`: scheme and host lower-cased, `www.` dropped, no trailing
    slash, tracking parameters removed and the rest sorted, a fragment kept only as a hash
    route (`#/…`, `#!…`). A job-board detail URL becomes its reference number, since its other
    parameters only describe the search."""
    if number := reference_number(url):
        return f"arbeitsagentur:{number}"
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").removeprefix("www.")
    query = sorted((name, value) for name, value in parse_qsl(parts.query)
                   if not TRACKING_PARAMETERS.match(name.lower()))
    route = parts.fragment if parts.fragment.startswith(("/", "!")) else ""  # hash routing
    return (f"{host}{f':{parts.port}' if parts.port else ''}{parts.path.rstrip('/')}"
            + (f"?{urlencode(query)}" if query else "") + (f"#{route}" if route else ""))


def text_hash(text: str) -> str:
    """A hash of `text` ignoring case and whitespace."""
    return hashlib.sha256(" ".join(text.lower().split()).encode()).hexdigest()


def shingles(text: str) -> set[tuple[str, ...]]:
    """Every run of `SHINGLE_WORDS` consecutive words in `text`, lower-cased."""
    words = re.findall(r"\w+", text.lower())
    return {tuple(words[i:i + SHINGLE_WORDS]) for i in range(len(words) - SHINGLE_WORDS + 1)}


def containment(a: set, b: set) -> float:
    """The share of the smaller shingle set found in the other: 1 when one text holds the
    other, e.g. a repost framed by a job board's header and footer."""
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def overlap_of_longer(a: set, b: set) -> float:
    """The share of the larger shingle set found in the other: low when a short text is
    contained in a much longer, different one (shared company boilerplate)."""
    return len(a & b) / max(len(a), len(b)) if a and b else 0.0


def duplicate_of(postings: dict[str, Posting], *, urls: list[str] = (),
                 text: str | None = None) -> tuple[str, Reason] | None:
    """The ID of a stored posting that `urls` or `text` duplicate and why, or `None`: a shared
    normalized URL, the same text hash, or, for texts of at least `MIN_SHINGLES` shingles
    each, a containment of at least `CONTAINMENT_THRESHOLD` and an overlap of the longer text
    of at least `MIN_OVERLAP`."""
    keys = {normalize_url(url) for url in urls}
    for posting_id, posting in postings.items():
        if keys & {normalize_url(url) for url in posting.urls}:
            return posting_id, "url"
    if text is None:
        return None
    digest = text_hash(text)
    for posting_id, posting in postings.items():
        if text_hash(posting.text) == digest:
            return posting_id, "text"
    submitted = shingles(text)
    if len(submitted) < MIN_SHINGLES:
        return None
    for posting_id, posting in postings.items():
        stored = shingles(posting.text)
        if len(stored) >= MIN_SHINGLES and containment(submitted, stored) >= \
                CONTAINMENT_THRESHOLD and overlap_of_longer(submitted, stored) >= MIN_OVERLAP:
            return posting_id, "similar_text"
    return None
