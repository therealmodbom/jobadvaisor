"""Feature-extraction eval: per-field accuracy on 20 demo postings with hand-written expected
features (`fixtures/evals/feature-extraction/expected.json`)."""

import json
from statistics import mean

from langchain_core.language_models import BaseChatModel

from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import DataRepository
from jobadvaisor.evals.cost import metered
from jobadvaisor.settings import REPOSITORY_ROOT
from jobadvaisor.tools.extraction import extract_features, feature_set

EXPECTED_FILE = REPOSITORY_ROOT / "fixtures" / "evals" / "feature-extraction" / "expected.json"


def run(repository: DataRepository, model: BaseChatModel, model_name: str) -> dict:
    """Extract every expected posting with `model` and report accuracy per feature.

    The report holds `accuracy` (feature ID → share correct), `postings`, `model`, `mismatches`
    and `errors`; a failed call counts as wrong on every feature. Lists compare as sets, text
    ignoring case. Data other than the demo persona is skipped, since only it has expectations.
    """
    report = {"eval": "feature_extraction", "metric": "per-field accuracy",
              "data": "20 demo postings with hand-written expected features",
              "model": model_name}
    if repository.root.resolve() != FIXTURE_DIRECTORY.resolve():
        return report | {"skipped": "expected features exist only for the demo persona"}
    expected = json.loads(EXPECTED_FILE.read_text())["postings"]
    features = feature_set(repository.policy_pack.feature_set)
    correct: dict[str, list[bool]] = {feature.id: [] for feature in features}
    costs, uncosted = [], 0
    mismatches, errors = [], []
    for posting_id, wanted in expected.items():
        try:
            with metered() as meter:
                posting = repository.postings[posting_id]
                got = extract_features(posting, features, model, repository.company_of(posting))
            costs.append(meter.cost)
            uncosted += meter.uncosted
        except Exception as error:  # one bad answer must not end the eval
            errors.append({"posting": posting_id, "error": str(error)})
            got = {}
        for feature_id, value in wanted.items():
            same = feature_id in got and normalize(got[feature_id]) == normalize(value)
            correct[feature_id].append(same)
            if got and not same:
                mismatches.append({"posting": posting_id, "feature": feature_id,
                                   "expected": value, "got": got.get(feature_id)})
    accuracy = {feature_id: mean(hits) for feature_id, hits in correct.items() if hits}
    return report | {"postings": len(expected), "accuracy": accuracy,
                     "overall": mean(accuracy.values()),
                     "cost_per_posting_usd": mean(costs) if costs else None,
                     "uncosted_calls": uncosted, "mismatches": mismatches, "errors": errors}


def normalize(value):
    """The form in which two extracted or expected feature values compare: a list as a sorted list
    of casefolded items (so as a set of options), a string casefolded and stripped, others as is."""
    if isinstance(value, list):
        return sorted(str(item).casefold() for item in value)
    return value.casefold().strip() if isinstance(value, str) else value
