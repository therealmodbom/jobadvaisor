"""The alert-mail eval (`openspec/changes/alert-mail-intake/design.md` → Eval): the finder on
anonymized alert mails, scored as *postings found* and *links correct* with two DeepEval
metrics without a judge, per rule and for the model.

Each case is `fixtures/intake/alert-mails/<case>.html` or `.txt` with `<case>.json`: the
expected `[{url, title}]` after cleaning, or `{"held": true}`. Links are compared exactly; a
case's group is the rule that reads its links, else `model`.
"""

import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from statistics import mean

from langchain_core.language_models import BaseChatModel

from jobadvaisor.evals.deepeval_runtime import DeepEval
from jobadvaisor.intake.alert_mail import (
    Found,
    Link,
    find_postings,
    model_view,
    read_mail,
    rule_for,
)
from jobadvaisor.llm import ModelNotConfiguredError
from jobadvaisor.settings import REPOSITORY_ROOT
from jobadvaisor.tools.guard import ContentGuard

CASES = REPOSITORY_ROOT / "fixtures" / "intake" / "alert-mails"
METRICS = ("postings_found", "links_correct")


@dataclass(frozen=True)
class Case:
    """One fixture mail: `html` or plain `text`, and what the finder should answer."""

    name: str
    html: str | None
    text: str
    expected: list[dict] | dict


def load_cases() -> list[Case]:
    """Every fixture mail with its expectation, by name."""
    cases = []
    for path in sorted(CASES.iterdir()):
        if path.suffix in (".html", ".txt"):
            content = path.read_text()
            html, text = (content, "") if path.suffix == ".html" else (None, content)
            cases.append(Case(path.stem, html, text, json.loads(path.with_suffix(".json")
                                                                .read_text())))
    return cases


def scores(expected: list[dict] | dict, found: Found) -> tuple[float, float]:
    """`(postings found, links correct)`: expected links returned over expected links, and
    returned links that are expected over returned links (1.0 when nothing is returned). A
    case expecting nothing that returns nothing scores 1.0 on both; one expecting `held` 1.0
    on both when held, else 0.0. Ambiguous entries count as returned."""
    if isinstance(expected, dict):
        return (1.0, 1.0) if found.held else (0.0, 0.0)
    wanted = {entry["url"] for entry in expected}
    got = {entry.url for entry in found.entries}
    hit = len(wanted & got)
    return (hit / len(wanted) if wanted else 1.0, hit / len(got) if got else 1.0)


def group(case: Case) -> str:
    """The rule that reads the case's first matching link, else `model`."""
    for item in read_mail(case.html, case.text):
        if isinstance(item, Link) and (found := rule_for(item.url)):
            return found[0].name
    return "model"


def _metric(deepeval: DeepEval, name: str, index: int):
    class AlertMailMetric(deepeval.BaseMetric):
        def __init__(self):
            self.threshold = 1.0
            self.async_mode = False
            self.evaluation_model = None
            self.strict_mode = False
            self.verbose_mode = False

        def measure(self, test_case, *args, **kwargs) -> float:
            """Score `test_case` (the answer as JSON against the expectation as JSON)."""
            answer = json.loads(test_case.actual_output)
            found = Found([_Url(url) for url in answer["urls"]], [], [], held=answer["held"])
            self.score = scores(json.loads(test_case.expected_output), found)[index]
            self.reason = name
            self.success = self.score >= self.threshold
            return self.score

        async def a_measure(self, test_case, *args, **kwargs) -> float:
            return self.measure(test_case)

        def is_successful(self) -> bool:
            return self.success

        @property
        def __name__(self):
            return name

    return AlertMailMetric()


@dataclass(frozen=True)
class _Url:
    url: str


def run(model_factory: Callable[[], BaseChatModel], guard: ContentGuard, model_name: str,
        deepeval: DeepEval) -> dict:
    """The report: each case's figures, or `skipped` with the reason for a model case when no
    classifier or no `intake` model is configured (`model_factory` raises
    `ModelNotConfiguredError`), and the mean figures per group. Rule cases run regardless."""
    rows, test_cases, names = [], [], []
    for case in load_cases():
        kind = group(case)
        needs_model = kind == "model" and model_view(read_mail(case.html, case.text))[1]
        model = None
        if needs_model and guard.classifier is None:
            rows.append({"case": case.name, "group": kind, "skipped": "screening off"})
            continue
        if needs_model:
            try:
                model = model_factory()
            except ModelNotConfiguredError as error:
                rows.append({"case": case.name, "group": kind, "skipped": str(error)})
                continue
        try:
            found = find_postings(case.html, case.text, model=model, guard=guard)
        except Exception as error:  # a failed case scores 0 and the eval goes on
            found = Found([], [], [])
            rows.append({"case": case.name, "group": kind, "error": type(error).__name__})
        else:
            rows.append({"case": case.name, "group": kind})
        names.append(len(rows) - 1)
        test_cases.append(deepeval.LLMTestCase(
            input=case.name, expected_output=json.dumps(case.expected),
            actual_output=json.dumps({"urls": [e.url for e in found.entries],
                                      "held": found.held})))
    if test_cases:
        result = deepeval.evaluate(test_cases, [_metric(deepeval, name, index)
                                                for index, name in enumerate(METRICS)],
                                   identifier=f"alert_mail {model_name}",
                                   hyperparameters={"model": model_name})
        for row_index, test_result in zip(names, result.test_results, strict=True):
            for metric in test_result.metrics_data:
                rows[row_index][metric.name] = metric.score
    groups = defaultdict(list)
    for row in rows:
        groups[row["group"]].append(row)
    return {"eval": "alert_mail", "model": model_name,
            "guard": guard.classifier.name if guard.classifier else None,
            "groups": {name: _figures(members) for name, members in groups.items()},
            "cases": rows}


def _figures(rows: list[dict]) -> dict:
    scored = [row for row in rows if "postings_found" in row]
    if not scored:
        return {"cases": 0, "skipped": rows[0].get("skipped")}
    return {"cases": len(scored)} | {metric: mean(row[metric] for row in scored)
                                     for metric in METRICS}
