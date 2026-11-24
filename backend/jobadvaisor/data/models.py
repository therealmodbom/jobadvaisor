"""Pydantic models for the data repository's entities, the source of `schemas/*.schema.json`.

Every file carries `schema_version`. A posting's ID is its file name (`postings/<id>.json`,
`labels/<id>.json`), never a field, so file name and content cannot disagree.
"""

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Annotated, ClassVar, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

POSTING_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,63}$"
HOST_PATTERN = r"^[a-z0-9-]+(\.[a-z0-9-]+)+$"
SIZE_CLASS_PATTERN = r"^\d[\d,]*(-\d[\d,]*|\+)$"
UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})

SchemaVersion = Literal["1"]
PostingVersion = Literal["1", "2"]
NonEmpty = Field(min_length=1)


def slug(words: str) -> str:
    """`words` in `a-z0-9-`: lower case, umlauts as ae, oe, ue, ss, other characters collapsed
    to single hyphens, none at either end. Empty when nothing usable remains."""
    ascii_words = unicodedata.normalize("NFKD", words.lower().translate(UMLAUTS)) \
        .encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_words).strip("-")


def company_id(name: str) -> str:
    """The file name stem of a company's record: the name as a slug (cut to 53 characters), a
    hyphen and ten hex digits of a hash of the name with case and spacing normalised, at most 64
    characters. The hash keeps names that slug alike ("A+B", "A B") apart, so each employer has
    a record of its own. Empty for a name without usable characters, which gets no record."""
    normalized = " ".join(name.split()).casefold()
    base = slug(normalized)[:53].rstrip("-")
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:10]
    return f"{base}-{digest}" if base else ""


class Entity(BaseModel):
    """Base for every data file: unknown fields are rejected, so typos fail validation.
    `supported_versions` lists the `schema_version` values the loader accepts for the entity."""

    supported_versions: ClassVar[tuple[str, ...]] = ("1",)
    model_config = ConfigDict(extra="forbid")


class Profile(Entity):
    """`profile.json`: what the user is looking for. Only `summary` is required."""

    schema_version: SchemaVersion
    summary: str = NonEmpty
    target_roles: list[str] = []
    locations: list[str] = []
    remote: Literal["onsite", "hybrid", "remote", "any"] = "any"
    seniority: str | None = None


class ExclusionRule(Entity):
    """A hard-exclusion predicate over a raw posting field.

    `contains_any` takes a list of strings; `matches_regex` and `equals` take one string. A
    `matches_regex` value must compile as a Python regular expression.
    """

    model_config = ConfigDict(json_schema_extra={
        "if": {"properties": {"operator": {"const": "contains_any"}}},
        "then": {"properties": {"value": {"type": "array"}}},
        "else": {"properties": {"value": {"type": "string"}}},
    })

    id: str = NonEmpty
    field: Literal["title", "text", "company", "location_raw", "urls"]
    operator: Literal["contains_any", "matches_regex", "equals"]
    value: str | list[str]

    @model_validator(mode="after")
    def value_fits_operator(self) -> Self:
        """Reject a value whose shape does not fit the operator, or a regex that cannot compile."""
        if (self.operator == "contains_any") != isinstance(self.value, list):
            kind = "a list of strings" if self.operator == "contains_any" else "one string"
            raise ValueError(f"value of operator {self.operator} must be {kind}")
        if self.operator == "matches_regex":
            try:
                re.compile(self.value)
            except re.error as error:
                raise ValueError(f"value is not a valid regular expression: {error}") from None
        return self


class ReasonChip(Entity):
    """A reason the user can attach to a rating; labels store its `id`. `polarity` names the
    verdict it explains ("positive" or "negative"); a chip without one fits both."""

    id: str = NonEmpty
    label: str = NonEmpty
    polarity: Literal["positive", "negative"] | None = None


class Feature(Entity):
    """One extracted feature. `categorical` and `list` draw from `options`, which they require;
    other types have no `options`, and `text` takes a short free-text value. "unknown" is always
    allowed as a value and is not listed."""

    model_config = ConfigDict(json_schema_extra={
        "if": {"properties": {"type": {"enum": ["categorical", "list"]}}},
        "then": {"required": ["options"], "properties": {"options": {"minItems": 1}}},
        "else": {"properties": {"options": {"type": "null"}}},
    })

    id: str = NonEmpty
    description: str = NonEmpty
    type: Literal["categorical", "list", "boolean", "number", "text"]
    options: list[str] | None = None

    @model_validator(mode="after")
    def options_fit_type(self) -> Self:
        """Require non-empty `options` for categorical and list features, and none otherwise."""
        if self.type in ("categorical", "list") and not self.options:
            raise ValueError(f"options must list at least one value for {self.type} features")
        if self.type not in ("categorical", "list") and self.options is not None:
            raise ValueError(f"options are not allowed for {self.type} features")
        return self


class ImportMapping(Entity):
    """What the columns and values of the user's job list mean for the list import. Column names
    and `values` keys match trimmed and without case. `status_column` and `assessment_column`
    name the columns holding the list's status and the user's own assessment (absent: none).
    `values` maps a status value as the list writes it to the application status it stands for
    (`skip`: the entry is not imported); a value it does not name is open."""

    status_column: str | None = None
    assessment_column: str | None = None
    values: dict[str, Literal["open", "applied", "done", "skip"]] = {}


class ClosedRule(Entity):
    """A rule that tells a closed posting page from an open one. `host` matches itself and its
    subdomains; exactly one marker is set: `redirect_marker`, a substring of the address a
    redirect points to, or `text_marker`, a phrase in the page's visible text (compared without
    case)."""

    host: Annotated[str, StringConstraints(pattern=HOST_PATTERN)]
    redirect_marker: str | None = Field(default=None, min_length=1)
    text_marker: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def one_marker(self) -> Self:
        """Reject a rule that names no marker or both."""
        if (self.redirect_marker is None) == (self.text_marker is None):
            raise ValueError("name exactly one of redirect_marker and text_marker")
        return self


class PolicyPack(Entity):
    """`policy-pack.json`: hard-exclusion rules, reason chips and the feature set. IDs are unique
    within each of the three lists. `login_wall_hosts` lists hosts intake never fetches
    anonymously (a host matches itself and its subdomains); it REPLACES the app's defaults, and
    absent means the defaults. `closed_rules` ADD to the app's default closed rules and never
    replace them; absent means the defaults only. `import_mapping` is the list import's last
    confirmed mapping; absent until the first import."""

    schema_version: SchemaVersion
    exclusion_rules: list[ExclusionRule] = []
    reason_chips: list[ReasonChip] = []
    feature_set: list[Feature] = []
    login_wall_hosts: list[Annotated[str, StringConstraints(pattern=HOST_PATTERN)]] | None = None
    closed_rules: list[ClosedRule] | None = None
    import_mapping: ImportMapping | None = None

    @model_validator(mode="after")
    def ids_unique(self) -> Self:
        """Reject a repeated ID within the rules, the chips or the features."""
        for name in ("exclusion_rules", "reason_chips", "feature_set"):
            ids = [item.id for item in getattr(self, name)]
            if duplicates := sorted({i for i in ids if ids.count(i) > 1}):
                raise ValueError(f"duplicate ids in {name}: {', '.join(duplicates)}")
        return self


class Guard(Entity):
    """The content guard's result for a posting. `released_at` is set once the user releases a
    flagged posting."""

    flagged: bool
    categories: list[str] = []
    checked_by: str = NonEmpty
    checked_at: AwareDatetime
    released_at: AwareDatetime | None = None


class Origin(Entity):
    """Where an imported posting came from: the `table` (section heading) of the import list,
    `fit` (the user's own assessment) and `status` (the list's status value), the last two as
    the list wrote them. Both are absent when the list had none."""

    table: str = NonEmpty
    fit: str | None = None
    status: str | None = None


class Availability(Entity):
    """Whether a posting is still open for applications: `state` is `available`, `closed` or
    `unknown` (the last check could not tell), `set_at` when it was set and `set_by` whether a
    `check` or the `user` set it. The next check replaces a hand setting, except one the user set
    while that check runs; an `unknown` result never reopens a closed posting."""

    state: Literal["available", "closed", "unknown"]
    set_at: AwareDatetime
    set_by: Literal["check", "user"]


class Posting(Entity):
    """`postings/<id>.json`; the ID is the file name and matches ^[a-z0-9][a-z0-9-]{0,63}$.
    Versions 1 and 2 load; version 1 has no `status` or `origin` and reads as status open without
    an origin. New postings are written as version 2. `status` is the user's application status.
    `urls` holds the submitted URL first when `source_type` is url. `guard` absent means never
    screened; `availability` absent means never checked (it does not change the schema version);
    `legacy_decision` is written only by an exporter. Unresolved `title`, `company` or
    `location_raw` hold "unknown"."""

    model_config = ConfigDict(json_schema_extra={
        "if": {"properties": {"source_type": {"const": "url"}}},
        "then": {"required": ["urls"], "properties": {"urls": {"minItems": 1}}},
    })

    supported_versions: ClassVar[tuple[str, ...]] = ("1", "2")
    schema_version: PostingVersion
    title: str = NonEmpty
    company: str = NonEmpty
    location_raw: str = NonEmpty
    text: str = NonEmpty
    source_type: Literal["url", "text", "pdf"]
    urls: list[str] = []
    added_at: AwareDatetime
    presented_at: AwareDatetime | None = None
    status: Literal["open", "applied", "done"] = "open"
    origin: Origin | None = None
    guard: Guard | None = None
    availability: Availability | None = None
    legacy_decision: Literal["kept", "discarded"] | None = None

    @model_validator(mode="after")
    def url_source_has_url(self) -> Self:
        """Require at least one URL for a posting submitted as a URL."""
        if self.source_type == "url" and not self.urls:
            raise ValueError("urls must hold the submitted URL when source_type is url")
        return self


class Company(Entity):
    """`companies/<id>.json`: what a lookup found about one employer, `<id>` being `company_id`
    of `name`. `size_class` is LinkedIn's range without the word employees ("51-200",
    "10,001+"), `founded` a four-digit year; each is absent when the source did not state it, so
    a record may hold neither (a completed lookup that found nothing). Both facts come from one
    `source` ("linkedin" or "website", the last one read for a record without facts; "manual"
    for a record the user entered, `source_url` then pointing at what they read) at
    `source_url`, looked up or entered at `fetched_at`."""

    schema_version: SchemaVersion
    name: str = NonEmpty
    size_class: Annotated[str, StringConstraints(pattern=SIZE_CLASS_PATTERN)] | None = None
    founded: int | None = Field(default=None, ge=1000, le=9999)
    source: Literal["linkedin", "website", "manual"]
    source_url: str = NonEmpty
    fetched_at: AwareDatetime


class Label(Entity):
    """`labels/<id>.json`: the label of `postings/<id>.json`. `verdict` is required, except for
    kind `imported_not_preference`, where it is absent. `strength` (`weak` | `strong`) is
    optional and only with a verdict; absent means a plain yes or no. `chips` hold reason chip
    IDs."""

    model_config = ConfigDict(json_schema_extra={
        "if": {"properties": {"kind": {"const": "imported_not_preference"}}},
        "then": {"properties": {"verdict": {"type": "null"}}},
        "else": {"required": ["verdict"], "properties": {"verdict": {"type": "string"}}},
    })

    schema_version: SchemaVersion
    kind: Literal["rating", "imported_interest", "imported_rejection", "imported_not_preference"]
    verdict: Literal["positive", "negative"] | None = None
    strength: Literal["weak", "strong"] | None = None
    chips: list[str] = []
    note: str | None = None
    rated_at: AwareDatetime

    @model_validator(mode="after")
    def verdict_fits_kind(self) -> Self:
        """Require a verdict for every kind except `imported_not_preference`, which has none,
        and a verdict for any `strength`."""
        if (self.kind == "imported_not_preference") != (self.verdict is None):
            raise ValueError(f"verdict must be absent exactly for kind imported_not_preference, "
                             f"got kind {self.kind}")
        if self.strength and self.verdict is None:
            raise ValueError("strength needs a verdict")
        return self


class Score(Entity):
    """`scores/<id>.json`: the stored fit score of `postings/<id>.json`. `score` is 0-10,
    `example_ids` the rated postings the judge was shown, `scored_at` when a pass or a single
    score wrote it."""

    schema_version: SchemaVersion
    score: int = Field(ge=0, le=10)
    reasoning: str
    example_ids: list[str] = []
    scored_at: AwareDatetime


class ExtractionLabels(Entity):
    """`extraction-labels.json`: hand-settled feature values, `labels[posting ID][feature ID]`,
    shaped like the extractor's output for the feature's type (text, list of options, boolean,
    number). `min_accuracy` (0 to 1) is the user's bar for the extractor; absent means the
    benchmark only reports. The loader checks that every posting and feature exists."""

    schema_version: SchemaVersion
    min_accuracy: float | None = Field(default=None, ge=0, le=1)
    labels: dict[str, dict[str, str | bool | float | list[str]]] = {}


class PoolSettings(Entity):
    """The two user-editable pool settings. The minimum ratings for a rate is fixed in code."""

    correction_threshold: int = Field(default=10, ge=1)
    correction_rate: float = Field(default=0.3, ge=0, le=1)


class PoolPass(Entity):
    """One finished pass: when, how many postings it `scored`, the `corrections` and `rated`
    counts it measured, and the resulting `rate` (absent when too few ratings to compute one).
    `started_at` is when the pass began; absent in passes written before slice 2. `variant` is
    `"all"` for a pass over all postings (rescore), `"unscored"` for one over the unscored only;
    `None` marks a record from before variants and counts as a pass over all postings.
    `cancelled` is `True` for a pass the user stopped after it scored something; absent
    otherwise (never `False`, so older readers that forbid unknown fields still read the
    records of passes that were not cancelled)."""

    started_at: AwareDatetime | None = None
    variant: Literal["unscored", "all"] | None = None
    cancelled: Literal[True] | None = None
    finished_at: AwareDatetime
    scored: int = Field(ge=0)
    corrections: int = Field(ge=0)
    rated: int = Field(ge=0)
    rate: float | None = None


class Pool(Entity):
    """`pool.json`: `settings` and the `passes` history, one entry appended per pass. A missing
    file means the defaults and an empty history."""

    schema_version: SchemaVersion
    settings: PoolSettings = PoolSettings()
    passes: list[PoolPass] = []


ID_HASH_PATTERN = r"^[0-9a-f]{16}$"
IdHash = Annotated[str, StringConstraints(pattern=ID_HASH_PATTERN)]


def message_id_hash(message_id: str) -> str:
    """The record of a mail's Message-ID: the first 16 hex characters of the SHA-256 of the ID,
    trimmed and lower-cased. It recognises a moved or renumbered mail without storing the ID,
    which names the sender's domain."""
    return hashlib.sha256(message_id.strip().lower().encode()).hexdigest()[:16]


@dataclass(frozen=True)
class MailRef:
    """Where one mail sits and which mail it is: `folder`, the folder's `validity`
    (UIDVALIDITY), the mail's `uid`, and `id_hash` (`message_id_hash`; `None` for a mail without
    a Message-ID, which then relies on its UID alone). Never holds sender, subject or text."""

    folder: str
    validity: int
    uid: int
    id_hash: str | None


class FolderUids(Entity):
    """The UIDs recorded in one folder, valid only under that folder's `validity`."""

    validity: int = Field(ge=0)
    uids: list[int] = []


class MailRecord(Entity):
    """A set of mails, by `uids` per folder name and by `ids` (Message-ID hashes). A mail is in
    the record when its UID is listed under the folder's current validity, or its hash is in
    `ids`. Methods return a new record; lists stay sorted and without repeats."""

    uids: dict[str, FolderUids] = {}
    ids: list[IdHash] = []

    def holds(self, mail: MailRef) -> bool:
        """Whether `mail` is in the record, by UID under the same validity or by hash."""
        folder = self.uids.get(mail.folder)
        return (folder is not None and folder.validity == mail.validity
                and mail.uid in folder.uids) or (mail.id_hash is not None
                                                 and mail.id_hash in self.ids)

    def marked(self, mails: Iterable[MailRef]) -> Self:
        """The record with `mails` added. A mail under a new validity of its folder replaces
        that folder's UIDs, since the old ones mean nothing any more."""
        uids = {name: set(folder.uids) for name, folder in self.uids.items()}
        validity = {name: folder.validity for name, folder in self.uids.items()}
        ids = set(self.ids)
        for mail in mails:
            if validity.get(mail.folder) != mail.validity:
                validity[mail.folder], uids[mail.folder] = mail.validity, set()
            uids[mail.folder].add(mail.uid)
            if mail.id_hash:
                ids.add(mail.id_hash)
        return self.model_copy(update={
            "uids": {name: FolderUids(validity=validity[name], uids=sorted(found))
                     for name, found in uids.items()},
            "ids": sorted(ids)})

    def unmarked(self, mails: Iterable[MailRef]) -> Self:
        """The record without `mails` (by UID under the same validity, and by hash)."""
        mails = list(mails)
        gone = {mail.id_hash for mail in mails}
        uids = {}
        for name, folder in self.uids.items():
            drop = {mail.uid for mail in mails
                    if mail.folder == name and mail.validity == folder.validity}
            if kept := [uid for uid in folder.uids if uid not in drop]:
                uids[name] = folder.model_copy(update={"uids": kept})
        return self.model_copy(update={"uids": uids,
                                       "ids": [hashed for hashed in self.ids
                                               if hashed not in gone]})


class Folders(Entity):
    """The folder choice: `{"all": true}` for every folder but the system folders, or
    `{"names": [...]}` for exactly those. Exactly one of the two is set."""

    all: Literal[True] | None = None
    names: list[str] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def exactly_one_choice(self) -> Self:
        """Refuse neither choice and both."""
        if (self.all is None) == (self.names is None):
            raise ValueError("choose either all folders or a list of folder names")
        return self


class Mailbox(Entity):
    """`mailbox.json`: the IMAP account without its password, the `folders` choice,
    `max_mails` per check (1 to 1000, 200 when absent), the `since` start date and the
    `last_check_at` time of the last finished check, the `handled` mails (never read again)
    and the `waiting` mails (no model read them because screening was off). A missing file
    means no mailbox is configured. Marks are numbers and hashes, never sender, subject or
    text."""

    schema_version: SchemaVersion
    host: str = Field(min_length=1)
    port: int = Field(default=993, ge=1, le=65535)
    user: str = Field(min_length=1)
    folders: Folders = Folders(all=True)
    max_mails: int = Field(default=200, ge=1, le=1000)
    since: date | None = None
    last_check_at: AwareDatetime | None = None
    handled: MailRecord = MailRecord()
    waiting: MailRecord = MailRecord()
