"""Write postings, labels and screening results to the data repository. The app writes files;
the backup (`data/backup.py`) commits and pushes them. Every public write function holds
`write_gate` for its whole read-modify-write, so a backup, which holds it from `git add` to the
end of `git commit`, never sees half a write."""

import functools
import itertools
import json
import os
import re
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from jobadvaisor.data.loader import DataRepositoryError, _load_file, load
from jobadvaisor.data.models import (
    POSTING_ID_PATTERN,
    Company,
    Entity,
    ExtractionLabels,
    Guard,
    ImportMapping,
    Label,
    PolicyPack,
    Pool,
    PoolPass,
    PoolSettings,
    Posting,
    Score,
)

# ponytail: process-local, reentrant (write functions call each other); one app process only,
# a file lock if several ever write the data
write_gate = threading.RLock()


def _gated[**P, R](function: Callable[P, R]) -> Callable[P, R]:
    """Run `function` while holding `write_gate`."""
    @functools.wraps(function)
    def gated(*args: P.args, **kwargs: P.kwargs) -> R:
        with write_gate:
            return function(*args, **kwargs)
    return gated


@_gated
def write_label(root: Path, posting_id: str, label: Label) -> Path:
    """Write `label` as `labels/<posting_id>.json` under `root`, replacing any earlier label.

    The label is validated again first, since a model changed after construction is not, and one
    invalid file would fail every later load. Unset optional fields are left out, so `verdict`
    is absent for `imported_not_preference`. The file is swapped in by rename, so an app crash
    leaves the old or the new label (no fsync, so a power loss may not). Raises `ValueError`
    (including Pydantic's `ValidationError`) for an invalid label, an unsafe posting ID or a
    posting that does not exist. Returns the written path.
    """
    label = Label.model_validate(label.model_dump())
    _posting_path(root, posting_id)
    path = root / "labels" / f"{posting_id}.json"
    path.parent.mkdir(exist_ok=True)
    _replace(path, label)
    return path


@_gated
def write_score(root: Path, posting_id: str, score: Score) -> Path:
    """Write `score` as `scores/<posting_id>.json` under `root`, replacing any earlier score.

    Validated again first and swapped in by rename, like `write_label`. Raises `ValueError`
    (including Pydantic's `ValidationError`) for an invalid score, an unsafe posting ID or a
    posting that does not exist. Returns the written path.
    """
    score = Score.model_validate(score.model_dump())
    _posting_path(root, posting_id)
    path = root / "scores" / f"{posting_id}.json"
    path.parent.mkdir(exist_ok=True)
    _replace(path, score)
    return path


@_gated
def merge_extraction_labels(root: Path, additions: dict[str, dict]) -> ExtractionLabels:
    """Merge `additions` (posting ID → feature ID → value) into `extraction-labels.json` under
    `root`, creating the file if missing: an existing label is replaced, every other label and
    `min_accuracy` stay. Written by rename like `write_label`, then the whole repository is
    loaded; if that fails the file is put back as it was. Raises `DataRepositoryError` when the
    existing file or the result does not load (a posting without a file, a feature the extractor
    does not extract) and `ValueError` for a malformed value. Returns the merged labels."""
    path = root / "extraction-labels.json"
    current = _read_entity(root, Path(path.name), ExtractionLabels) \
        or ExtractionLabels(schema_version="1")
    labels = {posting: dict(values) for posting, values in current.labels.items()}
    for posting, values in additions.items():
        labels.setdefault(posting, {}).update(values)
    merged = ExtractionLabels.model_validate({**current.model_dump(), "labels": labels})
    previous = path.read_bytes() if path.exists() else None
    _replace(path, merged)
    try:
        load(root)
    except DataRepositoryError:
        if previous is None:
            path.unlink()
        else:
            path.write_bytes(previous)
        raise
    return merged


@_gated
def write_company(root: Path, company_id: str, company: Company) -> Path:
    """Write `company` as `companies/<company_id>.json` under `root`, replacing any earlier
    record. Validated again first, unset facts left out, swapped in by rename like
    `write_label`. Raises `ValueError` (including Pydantic's `ValidationError`) for an invalid
    record or an ID that does not match `POSTING_ID_PATTERN`. Returns the written path."""
    company = Company.model_validate(company.model_dump())
    path = root / "companies" / f"{_safe_id(company_id)}.json"
    path.parent.mkdir(exist_ok=True)
    _replace(path, company)
    return path


def read_company(root: Path, company_id: str) -> Company | None:
    """`companies/<company_id>.json` under `root` as the file on disk holds it now, or `None`
    when the company has no record. Raises `ValueError` for an unsafe ID and
    `DataRepositoryError` for an unreadable, invalid or unsupported-version file."""
    return _read_entity(root, Path("companies") / f"{_safe_id(company_id)}.json", Company)


def read_score(root: Path, posting_id: str) -> Score | None:
    """`scores/<posting_id>.json` under `root` as the file on disk holds it now, or `None` when
    the posting has no score. Raises `ValueError` for an unsafe ID and `DataRepositoryError` for
    an unreadable, invalid or unsupported-version file."""
    return _read_entity(root, Path("scores") / f"{_safe_id(posting_id)}.json", Score)


def read_pool(root: Path) -> Pool:
    """`pool.json` under `root`, or a `Pool` with default settings and an empty history when the
    file is missing. Raises `DataRepositoryError` for an unreadable, invalid or
    unsupported-version file."""
    return _read_entity(root, Path("pool.json"), Pool) or Pool(schema_version="1")


@_gated
def write_pool(root: Path, pool: Pool) -> Path:
    """Write `pool` as `pool.json` under `root`, replacing the file by rename like `write_label`.
    Validated again first. Raises `ValueError` for an invalid pool. Returns the written path."""
    pool = Pool.model_validate(pool.model_dump())
    path = root / "pool.json"
    _replace(path, pool)
    return path


@_gated
def append_pass(root: Path, finished: PoolPass) -> Pool:
    """Append `finished` to the `passes` of `pool.json` under `root` (created with defaults if
    missing), keeping settings and earlier passes, and return the updated pool. Read-modify-write
    under the write gate with an atomic final write. Raises like `read_pool` and `write_pool`."""
    pool = read_pool(root)
    pool.passes.append(finished)
    write_pool(root, pool)
    return pool


@_gated
def update_pool_settings(root: Path, settings: PoolSettings) -> Pool:
    """Replace the `settings` of `pool.json` under `root` (created with defaults if missing),
    keeping the passes, and return the updated pool. Same locking as `append_pass`. Raises like
    `read_pool` and `write_pool`; an invalid `settings` raises `ValueError`."""
    settings = PoolSettings.model_validate(settings.model_dump())
    pool = read_pool(root)
    pool.settings = settings
    write_pool(root, pool)
    return pool


def read_scores(root: Path) -> tuple[dict[str, Score], dict[str, str]]:
    """Every readable `scores/*.json` under `root` by posting ID, and the problems by posting ID
    (one line naming the file and why) for unreadable, invalid or unsupported-version files.
    Files whose stem is no safe posting ID are skipped; a missing directory gives two empty
    dicts. Never raises for a bad score file."""
    scores: dict[str, Score] = {}
    problems: dict[str, str] = {}
    for path in sorted((root / "scores").glob("*.json")):
        if not re.fullmatch(POSTING_ID_PATTERN, path.stem):
            continue
        try:
            score = read_score(root, path.stem)
        except DataRepositoryError as error:
            problems[path.stem] = "; ".join(error.problems)
        else:
            if score is not None:
                scores[path.stem] = score
    return scores, problems


def _safe_id(posting_id: str) -> str:
    if not re.fullmatch(POSTING_ID_PATTERN, posting_id):
        raise ValueError(f"posting ID {posting_id!r} must match {POSTING_ID_PATTERN}")
    return posting_id


def _read_entity[M: Entity](root: Path, relative: Path, model: type[M]) -> M | None:
    if not (root / relative).exists():
        return None
    problems: list[str] = []
    entity = _load_file(root, relative, model, problems)
    if problems:
        raise DataRepositoryError(problems)
    return entity


@_gated
def write_guard(root: Path, posting_id: str, guard: Guard) -> Posting:
    """Set the `guard` of `postings/<posting_id>.json` under `root` to `guard`, leaving every
    other field as the file on disk holds it, and return the updated posting.

    The posting is re-read from disk and only its `guard` key replaced, so a change made since
    the repository was loaded is kept. Validated before writing, written by rename like
    `write_label`. Raises `ValueError` for an unsafe posting ID, a
    posting that does not exist or an invalid result.
    """
    return update_posting(root, posting_id,
                          {"guard": guard.model_dump(mode="json", exclude_none=True)})


def read_posting(root: Path, posting_id: str) -> Posting:
    """`postings/<posting_id>.json` under `root` as the file on disk holds it now. Raises
    `ValueError` for an unsafe ID or a posting that does not exist."""
    return Posting.model_validate_json(_posting_path(root, posting_id).read_text(), strict=True)


@_gated
def update_posting(root: Path, posting_id: str, updates: dict[str, object]) -> Posting:
    """Replace the top-level keys in `updates` (JSON values) of `postings/<posting_id>.json`
    under `root` in one write, keeping every other key as the file on disk holds it, and return
    the updated posting. Writing a version 2 field (`status`, `origin`) sets `schema_version` to
    `"2"`. Raises like `write_guard`."""
    if updates.keys() & {"status", "origin"}:
        updates = updates | {"schema_version": "2"}
    return _update_json(_posting_path(root, posting_id), updates, Posting)


@_gated
def write_login_wall_hosts(root: Path, hosts: list[str]) -> PolicyPack:
    """Set `login_wall_hosts` in `policy-pack.json` under `root` to `hosts`, keeping every other
    key as the file on disk holds it (an absent field stays absent), and return the updated
    pack. Validated before writing, written by rename like `write_label`. Raises `ValueError`
    for a host that does not match `HOST_PATTERN`."""
    return _update_json(root / "policy-pack.json", {"login_wall_hosts": hosts}, PolicyPack)


@_gated
def write_import_mapping(root: Path, mapping: ImportMapping) -> PolicyPack:
    """Set `import_mapping` in `policy-pack.json` under `root` to `mapping`, keeping every other
    key as the file on disk holds it, and return the updated pack. Written like
    `write_login_wall_hosts`; raises `ValueError` if the resulting pack is invalid."""
    return _update_json(root / "policy-pack.json",
                        {"import_mapping": mapping.model_dump(mode="json")}, PolicyPack)


@_gated
def _update_json[T: BaseModel](path: Path, updates: dict[str, object], model: type[T]) -> T:
    """Merge `updates` into the JSON object at `path`, validate it as `model`, write it by
    rename and return it. Read and write run under the write gate, so two updates of one file
    (an import's origin mark and a status `PATCH`) never drop each other's keys."""
    data = json.loads(path.read_text()) | updates
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    entity = model.model_validate_json(text, strict=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text)
    os.replace(temporary, path)
    return entity


@_gated
def create_posting(root: Path, base_id: str, posting: Posting) -> str:
    """Write `posting` as a new file `postings/<base_id>.json` under `root`, or with `-2`, `-3`
    … appended when that name is taken, and return the ID used. Never overwrites a file: the
    name is claimed by a hard link, which fails if it exists, so concurrent writers get
    distinct IDs. Raises `ValueError` for an ID that cannot match `POSTING_ID_PATTERN`."""
    posting = Posting.model_validate(posting.model_dump())
    directory = root / "postings"
    directory.mkdir(exist_ok=True)
    handle, name = tempfile.mkstemp(dir=directory, prefix=".", suffix=".new")
    temporary = Path(name)
    with os.fdopen(handle, "w") as file:
        file.write(posting.model_dump_json(indent=2, exclude_none=True) + "\n")
    try:
        for n in itertools.count(1):
            posting_id = base_id if n == 1 else f"{base_id}-{n}"
            if not re.fullmatch(POSTING_ID_PATTERN, posting_id):
                raise ValueError(f"posting ID {posting_id!r} must match {POSTING_ID_PATTERN}")
            try:
                os.link(temporary, directory / f"{posting_id}.json")
                return posting_id
            except FileExistsError:
                continue
    finally:
        temporary.unlink()


def _posting_path(root: Path, posting_id: str) -> Path:
    if not re.fullmatch(POSTING_ID_PATTERN, posting_id):
        raise ValueError(f"posting ID {posting_id!r} must match {POSTING_ID_PATTERN}")
    path = root / "postings" / f"{posting_id}.json"
    if not path.is_file():
        raise ValueError(f"no posting postings/{posting_id}.json in {root}")
    return path


def _replace(path: Path, entity: BaseModel) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(entity.model_dump_json(indent=2, exclude_none=True) + "\n")
    os.replace(temporary, path)
