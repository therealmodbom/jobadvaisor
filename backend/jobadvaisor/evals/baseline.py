"""Baseline row (spec `match-evaluation` → Baseline comparison): precision@k of the old process,
whose ranking puts every posting it kept (`legacy_decision: kept`) before every one it
discarded, measured on labeled postings that carry a legacy decision, including a rated sample
of the discarded ones. Needs no model.
"""

from jobadvaisor.data.loader import DataRepository


def run(repository: DataRepository, k: int = 5) -> dict:
    """Report precision@k of the kept-first ranking over the labeled postings with a legacy
    decision. The old process did not order postings inside a group, so a group cut by k
    counts at its share of positives (the expected precision of a random order). Skipped
    without such postings, or without a rated discarded posting."""
    report = {"eval": "baseline", "metric": "precision@k of the old process (kept first)",
              "data": repository.root.name, "k": k}
    groups = {"kept": [], "discarded": []}
    for posting_id, posting in repository.postings.items():
        label = repository.labels.get(posting_id)
        if posting.legacy_decision and label and label.verdict:
            groups[posting.legacy_decision].append(label.verdict == "positive")
    if not groups["kept"] and not groups["discarded"]:
        return report | {"skipped": "no labeled posting carries legacy_decision"}
    if not groups["discarded"]:
        return report | {"skipped": "no discarded posting is rated"}
    slots, positives = k, 0.0
    for verdicts in (groups["kept"], groups["discarded"]):
        taken = min(slots, len(verdicts))
        positives += taken * sum(verdicts) / len(verdicts) if verdicts else 0
        slots -= taken
    return report | {
        "precision_at_k": positives / (k - slots),
        "kept": len(groups["kept"]), "kept_positive": sum(groups["kept"]),
        "discarded_rated": len(groups["discarded"]),
        "discarded_positive": sum(groups["discarded"]),
    }
