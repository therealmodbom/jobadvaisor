"""Accuracy of extracted features against extraction labels, as a custom DeepEval metric.

One `LLMTestCase` per labelled posting: the posting ID as `input` (never its text, since DeepEval
stores test cases on disk), the extracted values as JSON in `actual_output` and the labels as JSON
in `expected_output`. A failed call has no values and so scores wrong on every labelled feature.
"""

import json
from collections import defaultdict
from statistics import mean

from jobadvaisor.evals.deepeval_runtime import DeepEval
from jobadvaisor.evals.feature_extraction import normalize

ACCURACY = "extraction accuracy"


def accuracy_metric(deepeval: DeepEval):
    """A DeepEval metric instance scoring a test case as the share of its labelled features whose
    extracted value equals the label; its `reason` is the JSON of feature ID → equal (true or
    false)."""

    class ExtractionAccuracy(deepeval.BaseMetric):
        def __init__(self):
            self.threshold = 1.0
            self.async_mode = False
            self.evaluation_model = None
            self.strict_mode = False
            self.verbose_mode = False

        def measure(self, test_case, *args, **kwargs) -> float:
            """Score `test_case` (JSON values against JSON labels) and keep the per-feature
            result in `reason`."""
            got = json.loads(test_case.actual_output)
            wanted = json.loads(test_case.expected_output)
            same = {feature: feature in got and normalize(got[feature]) == normalize(value)
                    for feature, value in wanted.items()}
            self.score = mean(same.values())
            self.reason = json.dumps(same)
            self.success = self.score >= self.threshold
            return self.score

        async def a_measure(self, test_case, *args, **kwargs) -> float:
            return self.measure(test_case)

        def is_successful(self) -> bool:
            return self.success

        @property
        def __name__(self):
            return ACCURACY

    return ExtractionAccuracy()


def pooled_accuracy(per_feature: dict[str, dict]) -> float:
    """The accuracy over all labelled feature values of `score_accuracy`'s result, which must not
    be empty: each feature's accuracy weighted by its case count."""
    cases = sum(figures["cases"] for figures in per_feature.values())
    return sum(figures["accuracy"] * figures["cases"] for figures in per_feature.values()) / cases


def check_minimum(per_feature: dict[str, dict], minimum: float | None) -> None:
    """Raise `AssertionError` naming the pooled accuracy, the `minimum` and the per-feature
    figures when the accuracy falls below it; no minimum (`None`) never fails."""
    if minimum is None:
        return
    value = pooled_accuracy(per_feature)
    if value < minimum:
        detail = ", ".join(f"{feature} {figures['accuracy']:.2f} ({figures['cases']} cases)"
                           for feature, figures in per_feature.items())
        raise AssertionError(f"{ACCURACY} {value:.2f} is below the minimum {minimum:.2f}: {detail}")


def score_accuracy(deepeval: DeepEval, extracted: dict[str, dict | None],
                   labels: dict[str, dict], run_id: str, hyperparameters: dict) -> dict[str, dict]:
    """Accuracy per labelled feature: `{feature ID: {"accuracy": share equal, "cases": count}}`.

    `extracted` maps posting ID to its values, `None` for a failed call (wrong); only postings
    with a non-empty label entry are cases, and a label for a posting not in `extracted` is
    skipped. Empty when there are no cases. `run_id` and `hyperparameters` (str/int/float values)
    are stored with the DeepEval run.
    """
    cases = [deepeval.LLMTestCase(input=posting, actual_output=json.dumps(values or {}),
                                  expected_output=json.dumps(labels[posting]))
             for posting, values in extracted.items() if labels.get(posting)]
    if not cases:
        return {}
    result = deepeval.evaluate(cases, [accuracy_metric(deepeval)], identifier=run_id,
                               hyperparameters=hyperparameters)
    equal, total = defaultdict(int), defaultdict(int)
    for test_result in result.test_results:
        for feature, same in json.loads(test_result.metrics_data[0].reason).items():
            equal[feature] += same
            total[feature] += 1
    return {feature: {"accuracy": equal[feature] / total[feature], "cases": total[feature]}
            for feature in total}
