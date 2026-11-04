"""Accuracy of the configured extractor against the data repository's extraction labels, for the
eval test runner. It makes paid model calls, so its name lacks the `test_` prefix: the default
`pytest` run never collects it, and only an explicit path does:

    DEEPEVAL_CACHE_FOLDER=<state>/deepeval deepeval test run tests/accuracy_suite.py

`DEEPEVAL_CACHE_FOLDER` must be set before the process starts, since `deepeval` fixes it at
import and would otherwise write the cases into the working directory; the failure names the
value. Settings come from `local.env`/the environment as for the benchmark command. The suite
scores the labelled postings with the benchmark's own functions, so its per-feature accuracy
equals the command's for the same extractor, and fails below the labels' `min_accuracy`.
"""

from datetime import UTC, datetime

import pytest

from jobadvaisor.data.loader import load
from jobadvaisor.evals.deepeval_runtime import load_deepeval
from jobadvaisor.evals.extraction_accuracy import check_minimum, score_accuracy
from jobadvaisor.evals.extractor_benchmark import check_state_directory, extract_postings
from jobadvaisor.index import state_path
from jobadvaisor.llm import chat_model
from jobadvaisor.settings import Settings
from jobadvaisor.tools.extraction import feature_set


def run_suite() -> tuple[dict, float | None]:
    """Extract the labelled postings with the configured extractor and return `(per_feature,
    min_accuracy)`: `score_accuracy`'s figures and the labels' minimum (`None` when unset).

    Skips with the reason when the data repository (`DATA_REPOSITORY`) holds no extraction
    labels. Raises `StateDirectoryError` for a state directory inside a repository,
    `ModelNotConfiguredError` without an extractor model and `RuntimeError` when DeepEval's
    folder was fixed outside the state directory.
    """
    settings = Settings()
    repository = load(settings.data_repository)
    extraction_labels = repository.extraction_labels
    if not extraction_labels or not any(extraction_labels.labels.values()):
        pytest.skip("the data repository holds no extraction labels")
    check_state_directory(settings.state_directory, repository.root)
    deepeval = load_deepeval(state_path(settings, repository.root))
    calls = extract_postings(repository, chat_model("extractor", settings),
                             feature_set(repository.policy_pack.feature_set),
                             only=extraction_labels.labels)
    per_feature = score_accuracy(
        deepeval, {call.posting: call.values for call in calls}, extraction_labels.labels,
        run_id=f"suite-{datetime.now(UTC):%Y%m%dT%H%M%SZ}",
        hyperparameters={"model": settings.extractor_model or settings.llm_model or ""})
    return per_feature, extraction_labels.min_accuracy


@pytest.fixture(scope="module")
def accuracy():
    """One extraction over the labelled postings for the whole module."""
    return run_suite()


def test_extractor_meets_the_minimum_accuracy(accuracy):
    """Print the accuracy per feature, and fail when it lies below `min_accuracy`."""
    per_feature, minimum = accuracy
    for feature, figures in per_feature.items():
        print(f"{feature}: {figures['accuracy']:.2f} ({figures['cases']} cases)")
    check_minimum(per_feature, minimum)
