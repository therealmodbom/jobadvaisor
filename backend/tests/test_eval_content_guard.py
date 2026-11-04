"""The content-guard eval's harness, with a stub classifier. The eval itself makes real calls and
runs only through `python -m jobadvaisor.evals`."""

import json

from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import load
from jobadvaisor.evals.content_guard import CLEAN_POSTINGS, INJECTED_FILE, run

DEMO = load(FIXTURE_DIRECTORY)
INJECTED = json.loads(INJECTED_FILE.read_text())["postings"]


class KeywordClassifier:
    """Flags texts naming "ignore", plus one clean demo posting, to exercise both rates."""

    name = "keyword"

    def classify(self, text: str) -> dict[str, float]:
        hit = "ignore" in text.lower() or text.startswith("Junior Android Developer")
        return {"jailbreaking": 1.0 if hit else 0.0}


class Broken:
    name = "broken"

    def classify(self, text: str) -> dict[str, float]:
        raise RuntimeError("service down")


def test_injected_fixtures_are_fictional_and_cover_three_kinds():
    assert {posting["kind"] for posting in INJECTED} == {"plain", "hidden_html", "json_ld"}
    assert all(posting["id"] for posting in INJECTED) and len(INJECTED) == 12
    assert set(CLEAN_POSTINGS) <= set(DEMO.postings) and len(CLEAN_POSTINGS) == 30


def test_reports_detection_and_false_positive_rates_per_kind():
    report = run(DEMO, KeywordClassifier(), {"jailbreaking": 0.5})
    ignore = [posting["id"] for posting in INJECTED if "ignore" in posting["text"].lower()]
    assert report["detection_rate"] == len(ignore) / 12
    assert report["false_positive_rate"] == report["false_positives"].__len__() / 30
    assert report["missed"] == [posting["id"] for posting in INJECTED
                                if posting["id"] not in ignore]
    assert set(report["detection_by_kind"]) == {"plain", "hidden_html", "json_ld"}
    assert report["classifier"] == "keyword"


def test_classifier_errors_are_listed_and_the_rates_stay_unset():
    report = run(DEMO, Broken(), {"jailbreaking": 0.5})
    assert len(report["errors"]) == 42 and report["detection_rate"] is None


def test_non_demo_data_is_skipped(data_repository):
    report = run(load(data_repository), KeywordClassifier(), {"jailbreaking": 0.5})
    assert report["skipped"] == "the clean set is the demo persona's postings"
