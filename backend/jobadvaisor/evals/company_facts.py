"""Company-facts eval: does the extractor use the facts block? One hand-written posting that
states neither its employer's size nor its stage is extracted with the employer's record
(`fixtures/evals/company-facts/case.json`); the `company_stage` must follow from the facts."""

import json

from langchain_core.language_models import BaseChatModel

from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import DataRepository
from jobadvaisor.data.models import Company, Posting
from jobadvaisor.evals.cost import metered
from jobadvaisor.settings import REPOSITORY_ROOT
from jobadvaisor.tools.extraction import extract_features, feature_set

CASE_FILE = REPOSITORY_ROOT / "fixtures" / "evals" / "company-facts" / "case.json"


def run(repository: DataRepository, model: BaseChatModel, model_name: str) -> dict:
    """Extract the case posting with `model` and its company record, and report whether the
    `company_stage` equals the expected one (`correct`, with `expected` and `got`).

    The report also holds `cost_usd`, `uncosted_calls` and `errors`; a failed call counts as
    wrong (`got` is `None`). Data other than the demo persona is skipped, since the demo
    persona's policy pack defines the stage options the case expects.
    """
    report = {"eval": "company_facts", "metric": "company_stage from facts alone",
              "data": "1 hand-written posting that states no size or stage", "model": model_name}
    if repository.root.resolve() != FIXTURE_DIRECTORY.resolve():
        return report | {"skipped": "the case exists only for the demo persona"}
    case = json.loads(CASE_FILE.read_text())
    expected = case["expected"]["company_stage"]
    got, errors = None, []
    with metered() as meter:
        try:
            got = extract_features(Posting.model_validate(case["posting"]),
                                   feature_set(repository.policy_pack.feature_set), model,
                                   Company.model_validate(case["company"]))["company_stage"]
        except Exception as error:  # a failed call is a wrong answer, not the end of the suite
            errors.append({"posting": "company-facts-case", "error": str(error)})
    return report | {"expected": expected, "got": got, "correct": got == expected,
                     "cost_usd": meter.cost, "uncosted_calls": meter.uncosted, "errors": errors}
