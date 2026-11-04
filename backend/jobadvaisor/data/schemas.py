"""Generate `schemas/*.schema.json` (JSON Schema 2020-12) from the models (ADR 0006).

Run `uv run python -m jobadvaisor.data.schemas` in `backend/` after changing a model, and commit
the output. `tests/test_schemas.py` fails while the committed files drift from the models.
"""

import json
from pathlib import Path

from pydantic import BaseModel

from jobadvaisor.data.models import (
    Company,
    ExtractionLabels,
    Label,
    PolicyPack,
    Pool,
    Posting,
    Profile,
    Score,
)
from jobadvaisor.settings import REPOSITORY_ROOT

SCHEMA_DIRECTORY = REPOSITORY_ROOT / "schemas"
ENTITIES: dict[str, type[BaseModel]] = {
    "profile": Profile,
    "policy-pack": PolicyPack,
    "posting": Posting,
    "label": Label,
    "score": Score,
    "company": Company,
    "pool": Pool,
    "extraction-labels": ExtractionLabels,
}


def render() -> dict[str, str]:
    """Return file name → schema file content for every entity."""
    files = {}
    for name, model in ENTITIES.items():
        schema = {"$schema": "https://json-schema.org/draft/2020-12/schema",
                  **model.model_json_schema()}
        files[f"{name}.schema.json"] = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
    return files


def write(directory: Path = SCHEMA_DIRECTORY) -> None:
    """Write every rendered schema into `directory`, creating it if needed."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in render().items():
        (directory / name).write_text(content)


def drift(directory: Path = SCHEMA_DIRECTORY) -> list[str]:
    """Return the sorted names of schema files in `directory` that are missing, differ from the
    rendered ones, or belong to no entity. Empty means no drift."""
    expected = render()
    present = {path.name for path in directory.glob("*.schema.json")}
    return sorted(
        name for name in expected.keys() | present
        if name not in present or expected.get(name) != (directory / name).read_text()
    )


if __name__ == "__main__":
    write()
