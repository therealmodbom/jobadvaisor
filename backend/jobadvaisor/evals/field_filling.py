"""Posting-field-filling eval: per-field accuracy for title, company and location over three
fixture pages, 10 pasted-text and 5 PDF demo postings with hand-written expectations
(`fixtures/evals/intake-fields/expected.json`)."""

import json
import re
from statistics import mean

from langchain_core.language_models import BaseChatModel

from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import DataRepository
from jobadvaisor.evals.fixture_pdf import minimal_pdf
from jobadvaisor.evals.intake import serve_pages
from jobadvaisor.intake.ladder import fetch_posting
from jobadvaisor.intake.postings import FIELDS, fill_fields, pdf_text
from jobadvaisor.settings import REPOSITORY_ROOT
from jobadvaisor.tools.extraction import UNKNOWN

EXPECTED_FILE = REPOSITORY_ROOT / "fixtures" / "evals" / "intake-fields" / "expected.json"
EVALUATED = {"title": "title", "company": "company", "location_raw": "location"}


def normalize(value: str, field_name: str) -> str:
    """`value` lower-cased, punctuation dropped, spaces collapsed; a title also loses a leading
    "junior-level", "mid-level" or "senior-level", which describes the level, not the role."""
    text = " ".join(re.sub(r"[^\w\s]", " ", value.lower()).split())
    return re.sub(r"^(junior|mid|senior) level ", "", text) if field_name == "title" else text


def run(repository: DataRepository, model: BaseChatModel, model_name: str) -> dict:
    """Fill every case's fields as intake does (values a page supplies are kept, the rest come
    from `model`) and report `accuracy` per field, `by_source` (page, text, pdf), `cases`,
    `mismatches` and `errors`; a failed case counts as wrong on every field. Title and
    company must equal an accepted value, location must contain the expected place.
    Data other than the demo persona is skipped, since only it has expectations."""
    report = {"eval": "field_filling", "metric": "per-field accuracy",
              "data": "3 fixture pages, 10 pasted-text and 5 PDF demo postings with "
                      "hand-written expected fields", "model": model_name}
    if repository.root.resolve() != FIXTURE_DIRECTORY.resolve():
        return report | {"skipped": "expected fields exist only for the demo persona"}
    expected = json.loads(EXPECTED_FILE.read_text())
    correct = {source: {name: [] for name in EVALUATED.values()}
               for source in ("page", "text", "pdf")}
    mismatches, errors = [], []
    with serve_pages() as base:
        cases = [("page", name, lambda name=name: _from_page(f"{base}/{name}", model))
                 for name in expected["pages"]]
        cases += [(source, posting_id, lambda posting_id=posting_id, source=source: _from_text(
                      repository.postings[posting_id].text, source == "pdf", model))
                  for source in ("text", "pdf") for posting_id in expected[source]]
        for source, name, fill in cases:
            wanted = expected["pages" if source == "page" else source][name]
            try:
                got = fill()
            except Exception as error:  # one bad answer must not end the eval
                errors.append({"case": name, "error": f"{type(error).__name__}: {error}"})
                got = {}
            for field_name, label in EVALUATED.items():
                value = got.get(field_name, UNKNOWN)
                ok = _correct(value, wanted, label)
                correct[source][label].append(ok)
                if not ok:
                    mismatches.append({"case": name, "field": label, "got": value})
    accuracy = {label: round(mean(ok for source in correct.values() for ok in source[label]), 3)
                for label in EVALUATED.values()}
    return report | {
        "accuracy": accuracy, "cases": sum(len(source["title"]) for source in correct.values()),
        "by_source": {source: {label: round(mean(values), 3) for label, values in fields.items()}
                      for source, fields in correct.items()},
        "mismatches": mismatches, "errors": errors}


def _from_page(url: str, model: BaseChatModel) -> dict[str, str]:
    page = fetch_posting(url, []).page
    if page is None:
        raise ValueError(f"no posting text at {url}")
    missing = [name for name in FIELDS if name not in page.supplied]
    return page.supplied | fill_fields(page.text, missing, model)


def _from_text(text: str, as_pdf: bool, model: BaseChatModel) -> dict[str, str]:
    return fill_fields(pdf_text(minimal_pdf(text)) if as_pdf else text, list(FIELDS), model)


def _correct(value: str, wanted: dict, label: str) -> bool:
    if label == "location":
        return normalize(wanted["location"], label) in normalize(value, label)
    return normalize(value, label) in {normalize(option, label) for option in wanted[label]}
