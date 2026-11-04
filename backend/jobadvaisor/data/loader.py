"""Load and validate a whole data repository (layout in `design.md`).

Loading is all or nothing: every file is validated first, and any problem fails the whole load,
so no part of an invalid file is ever used.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from jobadvaisor.data.models import (
    POSTING_ID_PATTERN,
    Company,
    Entity,
    ExtractionLabels,
    Label,
    PolicyPack,
    Posting,
    Profile,
    company_id,
)
from jobadvaisor.tools.extraction import feature_set

EXTRACTION_LABELS_FILE = Path("extraction-labels.json")
_BOUND_ERRORS = {"greater_than", "greater_than_equal", "less_than", "less_than_equal"}


class DataRepositoryError(Exception):
    """The data repository cannot be used. `problems` holds one line per problem, each starting
    with the file path relative to the repository root, or naming `DATA_REPOSITORY`."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("Invalid data repository:\n" + "\n".join(problems))


@dataclass(frozen=True)
class DataRepository:
    """A fully validated data repository. `postings` and `labels` are keyed by posting ID,
    `companies` by `company_id` (empty without a `companies/` directory)."""

    root: Path
    profile: Profile
    policy_pack: PolicyPack
    postings: dict[str, Posting]
    labels: dict[str, Label]
    extraction_labels: ExtractionLabels | None = None
    companies: dict[str, Company] = field(default_factory=dict)

    def company_of(self, posting: Posting) -> Company | None:
        """The stored record of the posting's company, or `None` when it has none."""
        return self.companies.get(company_id(posting.company))


def load(location: Path | None) -> DataRepository:
    """Load the data repository at `location`, normally `Settings().data_repository`.

    Raises `DataRepositoryError` listing every problem: an unset or missing location, an
    unreadable or invalid file, an unsupported schema version, an unsafe posting ID, or a label
    without its posting. The optional `extraction-labels.json` loads into `extraction_labels`
    (`None` when absent); a label for a missing posting or for a feature the extractor does not
    extract (the defaults plus the policy pack's features) is a problem. Optional
    `companies/*.json` load into `companies`.
    """
    if location is None:
        raise DataRepositoryError(["DATA_REPOSITORY is not set"])
    if not location.is_dir():
        raise DataRepositoryError([f"DATA_REPOSITORY points to {location}, which is no directory"])

    problems: list[str] = []
    profile = _load_file(location, Path("profile.json"), Profile, problems)
    policy_pack = _load_file(location, Path("policy-pack.json"), PolicyPack, problems)
    postings = _load_directory(location, "postings", Posting, problems)
    labels = _load_directory(location, "labels", Label, problems)
    companies = _load_directory(location, "companies", Company, problems)
    problems += [f"labels/{posting_id}.json: no posting postings/{posting_id}.json"
                 for posting_id in sorted(labels.keys() - _stems(location / "postings"))]
    extraction_labels = None
    if (location / EXTRACTION_LABELS_FILE).exists():
        extraction_labels = _load_file(location, EXTRACTION_LABELS_FILE, ExtractionLabels, problems)
    if extraction_labels is not None:
        problems += _extraction_label_problems(
            extraction_labels, _stems(location / "postings"),
            {feature.id for feature in feature_set(policy_pack.feature_set)}
            if policy_pack else None)
    if problems:
        raise DataRepositoryError(problems)
    return DataRepository(location, profile, policy_pack, postings, labels, extraction_labels,
                          companies)


def _extraction_label_problems(
    extraction_labels: ExtractionLabels, posting_ids: set[str], feature_ids: set[str] | None
) -> list[str]:
    """One problem per posting without a posting file and per feature outside `feature_ids`; the
    feature check is skipped when the policy pack did not load (`feature_ids` is `None`)."""
    problems = []
    for posting_id, values in extraction_labels.labels.items():
        if posting_id not in posting_ids:
            problems.append(f"{EXTRACTION_LABELS_FILE}: label names posting {posting_id}, "
                            f"which has no file postings/{posting_id}.json")
        if feature_ids is not None:
            problems += [f"{EXTRACTION_LABELS_FILE}: posting {posting_id} has a label for "
                         f"feature {feature}, which is not in the feature set"
                         for feature in sorted(values.keys() - feature_ids)]
    return problems


def _stems(directory: Path) -> set[str]:
    """Stems of every `*.json` file in `directory`, valid or not, matched case-sensitively."""
    return {path.stem for path in directory.glob("*.json")}


def _load_directory[M: Entity](
    root: Path, name: str, model: type[M], problems: list[str]
) -> dict[str, M]:
    entities = {}
    for path in sorted((root / name).glob("*.json")):
        relative = path.relative_to(root)
        if not re.fullmatch(POSTING_ID_PATTERN, path.stem):
            problems.append(f"{relative}: file name must match {POSTING_ID_PATTERN}")
        elif (entity := _load_file(root, relative, model, problems)) is not None:
            entities[path.stem] = entity
    return entities


def _load_file[M: Entity](
    root: Path, relative: Path, model: type[M], problems: list[str]
) -> M | None:
    """Validate one file, appending its problems and returning `None` when it is invalid.

    Strict mode, so values the published schema rejects (an epoch number for a timestamp, "yes"
    for a boolean) are rejected here too instead of being coerced.
    """
    try:
        text = (root / relative).read_text()
        data = json.loads(text)
    except FileNotFoundError:
        problems.append(f"{relative}: file is missing")
        return None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        problems.append(f"{relative}: not readable as JSON: {error}")
        return None
    version = data.get("schema_version") if isinstance(data, dict) else None
    if isinstance(version, str) and version not in model.supported_versions:
        problems.append(f"{relative}: schema version {version} is not supported "
                        f"(supported: {', '.join(model.supported_versions)})")
        return None
    try:
        return model.model_validate_json(text, strict=True)
    except ValidationError as error:
        for detail in error.errors():
            location = ".".join(str(part) for part in detail["loc"])
            message = detail["msg"]
            if detail["type"] in _BOUND_ERRORS:
                message += f" (got {detail['input']})"
            problems.append(": ".join(filter(None, (str(relative), location, message))))
        return None
