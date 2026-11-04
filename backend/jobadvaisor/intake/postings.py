"""Storing a submitted posting: screening, per-field filling, ID allocation, corrections and
release (`design.md` → Intake, Content guard)."""

import io
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, create_model
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from jobadvaisor.data.loader import load
from jobadvaisor.data.models import PolicyPack, Posting, slug
from jobadvaisor.data.writer import create_posting, read_posting, update_posting
from jobadvaisor.intake.company_facts import look_up
from jobadvaisor.intake.duplicates import Reason, duplicate_of, normalize_url
from jobadvaisor.intake.ladder import LadderResult, fetch_posting, is_gone, login_wall_hosts
from jobadvaisor.intake.loop import run_intake_loop
from jobadvaisor.tools.extraction import UNKNOWN
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.tools.prompts import DATA_RULE, data_block

FIELDS = {
    "title": "The role's title as the posting names it",
    "company": "The hiring employer as the posting names it",
    "location_raw": "The place of work as the posting states it, e.g. a city or \"Remote\"",
}
INSTRUCTIONS = ("You read one job posting and name the fields below exactly as the posting "
                "states them. Answer \"unknown\" for a field the posting does not state. "
                + DATA_RULE.format(tag="posting"))
_STORE_LOCK = threading.Lock()


class NoPostingTextError(ValueError):
    """A submission yields no posting text; the message tells the user what to do instead."""


@dataclass(frozen=True)
class Intake:
    """What intake needs: the data repository root, the `intake` chat model and the content
    guard. `loop_model` runs the intake loop (default: `model`); `search` answers the loop's
    web searches, `None` while no search provider is configured."""

    root: Path
    model: BaseChatModel
    guard: ContentGuard
    loop_model: BaseChatModel | None = None
    search: Callable[[str], str] | None = None

    def postings(self) -> dict[str, Posting]:
        """Every stored posting by ID, as the data repository holds it now."""
        return load(self.root).postings


def read_policy_pack(root: Path) -> PolicyPack:
    """`policy-pack.json` under `root` as the file on disk holds it now."""
    return PolicyPack.model_validate_json((root / "policy-pack.json").read_text(), strict=True)


def find_posting(intake: Intake, url: str, hints: dict[str, str] | None = None, *,
                 search_if_gone: bool = True) -> LadderResult:
    """The posting behind `url`: the fetch ladder first, then the intake loop when no step
    yielded posting text, with the fields the user supplied as `hints`. Without
    `search_if_gone`, a `url` answering gone (`is_gone`) ends there, with no loop. Login-walled
    hosts come from the data repository's policy pack."""
    walled = login_wall_hosts(read_policy_pack(intake.root))
    result = fetch_posting(url, walled)
    if result.page is not None:
        return result
    if not search_if_gone and is_gone([vars(a) for a in result.attempts], url):
        return result
    return run_intake_loop(url, result.attempts, walled, intake.loop_model or intake.model,
                           intake.guard, search=intake.search, hints=hints)


@dataclass(frozen=True)
class Submission:
    """Posting text from one source, with any field values the source itself supplied.
    `urls` holds the submitted URL first, then any alternative source used."""

    text: str
    source_type: Literal["url", "text", "pdf"]
    urls: list[str] = field(default_factory=list)
    supplied: dict[str, str] = field(default_factory=dict)


def store_posting(intake: Intake, submission: Submission,
                  now: datetime | None = None) -> tuple[str, Posting]:
    """Screen, fill and store `submission` as a new posting; returns its ID and the posting.

    With a classifier configured, the supplied fields and text are screened first; a flagged
    posting reaches no model, so its missing fields stay "unknown". Otherwise every missing
    field is filled by one `intake` structured-output call (none when all are supplied).
    Raises `NoPostingTextError` for empty text.
    """
    posting, base_id = _prepare(intake, submission, now)
    return create_posting(intake.root, base_id, posting), posting


class PostingNotFoundError(Exception):
    """No fetch attempt yielded the posting behind a URL; `attempts` lists them as dicts."""

    def __init__(self, attempts: list[dict]):
        super().__init__("no attempt yielded the posting")
        self.attempts = attempts


def add_from_url(
    intake: Intake, url: str, supplied: dict[str, str] | None = None, *,
    search_if_gone: bool = True,
) -> tuple[str, Posting, Reason | None, list]:
    """Store the posting behind `url` (an http(s) address) unless a stored one has that URL.

    Returns `(posting_id, posting, duplicate_by, attempts)`: `duplicate_by` names why a stored
    posting was returned instead (`None` for a new one), `attempts` are the fetch ladder's steps
    as dicts (empty when the URL was already stored, so nothing was fetched). A new posting
    whose company has no record gets its facts looked up (`look_up`, best effort). Without
    `search_if_gone`, a gone `url` is not looked for elsewhere (`find_posting`). Raises
    `PostingNotFoundError` when no attempt yielded the posting, `NoPostingTextError` for empty
    posting text.
    """
    supplied = supplied or {}
    if found := duplicate_of(intake.postings(), urls=[url]):
        return found[0], read_posting(intake.root, found[0]), found[1], []
    result = find_posting(intake, url, supplied, search_if_gone=search_if_gone)
    attempts = [vars(attempt) for attempt in result.attempts]
    if result.page is None:
        raise PostingNotFoundError(attempts)
    submission = Submission(result.page.text, "url", posting_urls(url, result.page.url),
                            result.page.supplied | supplied)
    posting_id, posting, duplicate = add_submission(intake, submission)
    if duplicate is None:  # after the write: a lookup never sits between a posting and its file
        look_up(intake.root, posting.company, result.page.company_url)
    return posting_id, posting, duplicate, attempts


def posting_urls(submitted: str, page_url: str) -> list[str]:
    """The `urls` of a posting found through `submitted`: that URL first, then the address the
    text came from (a redirect target or an alternative source) when it is another address
    after `normalize_url`, so later submissions of either are found as duplicates."""
    return [submitted] + ([page_url] if normalize_url(page_url) != normalize_url(submitted)
                          else [])


def add_submission(intake: Intake,
                   submission: Submission) -> tuple[str, Posting, Reason | None]:
    """The stored posting `submission` duplicates (`duplicate_of`) with the reason, or the
    newly stored one (`store_posting`) with `None`. Duplicates are checked again right before
    the write, under a lock, so concurrent identical submissions store one posting."""
    postings = intake.postings()
    if found := duplicate_of(postings, urls=submission.urls, text=submission.text):
        return found[0], postings[found[0]], found[1]
    posting, base_id = _prepare(intake, submission)
    with _STORE_LOCK:  # ponytail: one process; a second app process would need a file lock
        postings = intake.postings()
        if found := duplicate_of(postings, urls=submission.urls, text=submission.text):
            return found[0], postings[found[0]], found[1]
        return create_posting(intake.root, base_id, posting), posting, None


def _prepare(intake: Intake, submission: Submission,
             now: datetime | None = None) -> tuple[Posting, str]:
    text = submission.text.strip()
    if not text:
        raise NoPostingTextError("the submission holds no posting text; paste the text instead")
    supplied = {name: value.strip() for name, value in submission.supplied.items()
                if name in FIELDS and value and value.strip()}
    guard = None
    if intake.guard.classifier is not None:
        guard = intake.guard.screen(
            "\n".join(supplied.get(name, "") for name in FIELDS) + "\n\n" + text)
    filled = {} if guard and guard.flagged else fill_fields(text, list(FIELDS.keys() - supplied),
                                                            intake.model)
    added_at = now or datetime.now(UTC)
    fields = {name: supplied.get(name) or filled.get(name) or UNKNOWN for name in FIELDS}
    posting = Posting(schema_version="2", text=text, source_type=submission.source_type,
                      urls=submission.urls, added_at=added_at, guard=guard, **fields)
    return posting, posting_id_base(added_at, fields["company"], fields["title"])


def fill_fields(text: str, missing: list[str], model: BaseChatModel) -> dict[str, str]:
    """Field name → value for each of `missing` ("title", "company", "location_raw"), read from
    `text` by one structured-output call; "unknown" where the posting does not say. No call
    when nothing is missing."""
    if not missing:
        return {}
    missing = [name for name in FIELDS if name in missing]
    schema: type[BaseModel] = create_model(
        "PostingFields", **{name: (str, Field(description=FIELDS[name])) for name in missing})
    result = model.with_structured_output(schema).invoke([
        SystemMessage(INSTRUCTIONS), HumanMessage(data_block("posting", text))])
    return {name: value.strip() or UNKNOWN
            for name, value in result.model_dump().items()}


def pdf_text(data: bytes) -> str:
    """The text of every page of a PDF, joined by blank lines. Raises `NoPostingTextError` for
    a file that is no readable PDF or holds no text (a scan)."""
    try:
        reader = PdfReader(io.BytesIO(data))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except (PyPdfError, ValueError, OSError):
        text = ""
    if not text:
        raise NoPostingTextError("the PDF holds no readable text; paste the posting text instead")
    return text


def posting_id_base(added_at: datetime, company: str, title: str) -> str:
    """`<YYYYMMDD>-<company>-<title>` in `a-z0-9-`, at most 61 characters, so a `-NN`
    collision suffix still fits the 64 of `POSTING_ID_PATTERN`. Umlauts become ae, oe, ue, ss."""
    return f"{added_at:%Y%m%d}-{slug(' '.join((company, title)))}"[:61].rstrip("-")


class NotFlaggedError(ValueError):
    """A release was asked for a posting the content guard did not flag."""


def amend_posting(root: Path, posting_id: str, corrections: dict[str, str], release: bool,
                  now: datetime | None = None) -> Posting:
    """Store the user's corrections of title, company or location and, with `release`, release
    a flagged posting by setting `guard.released_at`, in one write; returns the posting.
    Raises `NotFlaggedError` for a release of an unflagged posting, `ValueError` for an
    unknown posting."""
    updates: dict[str, object] = dict(corrections)
    if release:
        guard = read_posting(root, posting_id).guard
        if guard is None or not guard.flagged:
            raise NotFlaggedError(f"posting {posting_id} is not flagged by the content guard")
        updates["guard"] = guard.model_copy(update={"released_at": now or datetime.now(UTC)}) \
            .model_dump(mode="json", exclude_none=True)
    return update_posting(root, posting_id, updates)
