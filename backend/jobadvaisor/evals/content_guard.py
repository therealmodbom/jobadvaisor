"""Content-guard eval: detection rate on fictional injected postings and false-positive rate on
clean demo postings, per classifier."""

import json

from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import DataRepository
from jobadvaisor.guard import Classifier, screen_content
from jobadvaisor.settings import REPOSITORY_ROOT
from jobadvaisor.tools.guard import screened_text

INJECTED_FILE = REPOSITORY_ROOT / "fixtures" / "evals" / "content-guard" / "injected.json"
CLEAN_POSTINGS = [f"demo-{number:03d}" for number in range(31, 61)]


def run(repository: DataRepository, classifier: Classifier, thresholds: dict[str, float]) -> dict:
    """Screen every injected fixture and the clean demo postings with `classifier`.

    The report holds `detection_rate` (overall and `detection_by_kind`), `false_positive_rate`,
    the `missed` and `false_positives` IDs, and `errors`; a text whose call fails counts in
    neither rate. Data other than the demo persona is skipped, since the clean set is its
    postings.
    """
    report = {"eval": "content_guard", "metric": "detection rate and false-positive rate",
              "data": "12 fictional injected postings, 30 clean demo postings",
              "classifier": classifier.name, "thresholds": thresholds}
    if repository.root.resolve() != FIXTURE_DIRECTORY.resolve():
        return report | {"skipped": "the clean set is the demo persona's postings"}
    injected = json.loads(INJECTED_FILE.read_text())["postings"]
    errors, flagged = [], {}
    texts = [(item["id"], item["text"]) for item in injected] + [
        (posting_id, screened_text(repository.postings[posting_id]))
        for posting_id in CLEAN_POSTINGS]
    for text_id, text in texts:
        try:
            flagged[text_id] = screen_content(text, classifier, thresholds).flagged
        except Exception as error:  # one failed call must not end the eval
            errors.append({"text": text_id, "error": str(error)})
    by_kind: dict[str, list[bool]] = {}
    for item in injected:
        if item["id"] in flagged:
            by_kind.setdefault(item["kind"], []).append(flagged[item["id"]])
    detected = [hit for hits in by_kind.values() for hit in hits]
    clean = [flagged[posting_id] for posting_id in CLEAN_POSTINGS if posting_id in flagged]
    return report | {
        "detection_rate": sum(detected) / len(detected) if detected else None,
        "detection_by_kind": {kind: sum(hits) / len(hits) for kind, hits in by_kind.items()},
        "false_positive_rate": sum(clean) / len(clean) if clean else None,
        "missed": [item["id"] for item in injected if flagged.get(item["id"]) is False],
        "false_positives": [posting_id for posting_id in CLEAN_POSTINGS
                            if flagged.get(posting_id)],
        "errors": errors,
    }
