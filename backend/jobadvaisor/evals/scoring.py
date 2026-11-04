"""Scoring eval: precision@k of the LLM judge's ranking on labels held out by time."""

import re
from dataclasses import dataclass
from datetime import datetime

from langchain_core.language_models import BaseChatModel

from jobadvaisor.data.loader import DataRepository
from jobadvaisor.evals.cost import metered
from jobadvaisor.index import LabelIndex
from jobadvaisor.tools.guard import WITHHELD, ContentGuard
from jobadvaisor.tools.scoring import score_posting
from jobadvaisor.tools.similar import find_similar_labeled


@dataclass(frozen=True)
class TimeSplit:
    """Posting IDs of usable labels rated before `cut_off` (training) and at or after it."""

    cut_off: datetime
    training: list[str]
    held_out: list[str]


def time_split(repository: DataRepository, held_out: int) -> TimeSplit:
    """Hold out the `held_out` latest labels with a verdict; the cut-off is the earliest held-out
    `rated_at`, so a label tied with it is held out too. `imported_not_preference` labels are in
    neither part. Needs more usable labels than `held_out`."""
    usable = sorted((label.rated_at, posting_id) for posting_id, label in repository.labels.items()
                    if label.verdict is not None)
    cut_off = usable[-held_out][0]
    return TimeSplit(cut_off, [posting_id for rated, posting_id in usable if rated < cut_off],
                     [posting_id for rated, posting_id in usable if rated >= cut_off])


def precision_at_k(ranked_verdicts: list[str], k: int) -> float:
    """Share of positives among the first `k` verdicts (all of them when fewer)."""
    top = ranked_verdicts[:k]
    return sum(verdict == "positive" for verdict in top) / len(top)


def _stems(label: str) -> list[str]:
    """Words of `label` of four letters or more, lower-cased and cut by two letters, so a German
    ending ("falscher", "falschem") still matches."""
    return [word[:max(4, len(word) - 2)] for word in re.findall(r"[^\W\d_]+", label.lower())
            if len(word) >= 4]


def _cue(chip, chips) -> str:
    """The text that stands for `chip` in a reasoning: the stem of the first word of its label that
    no other chip's label shares, else the whole label. Not the whole label alone, because the judge
    inflects it; not every word, because a word like "möglich" turns up in unrelated reasoning.
    # ponytail: a paraphrase without the cue word is missed; an LLM judge would catch it, at a
    # model call per case."""
    shared = {stem for other in chips if other is not chip for stem in _stems(other.label)}
    return next((stem for stem in _stems(chip.label) if stem not in shared), chip.label.lower())


def mixed_chip_citations(repository: DataRepository, rows: list[dict]) -> list[dict]:
    """For every scored row whose examples include a rating with chips of both polarities, how
    its reasoning treats them: `{"posting", "example", "cited": [chip labels whose cue (see
    `_cue`) is found in the reasoning, case-insensitive], "cites_both": bool}`, where `cites_both`
    means at least one chip of each polarity is cited. Empty when no scored row was shown such an
    example."""
    pack = repository.policy_pack.reason_chips
    chips = {chip.id: chip for chip in pack}
    cues = {chip.id: _cue(chip, pack) for chip in pack}
    found = []
    for row in rows:
        for example in row["example_ids"]:
            used = [chips[chip] for chip in repository.labels[example].chips if chip in chips]
            if {chip.polarity for chip in used} < {"positive", "negative"}:
                continue
            cited = [chip for chip in used if cues[chip.id] in row["reasoning"].lower()]
            found.append({"posting": row["posting"], "example": example,
                          "cited": [chip.label for chip in cited],
                          "cites_both": {chip.polarity for chip in cited}
                          >= {"positive", "negative"}})
    return found


def run(repository: DataRepository, index: LabelIndex, guard: ContentGuard, judge: BaseChatModel,
        model_name: str, k: int = 5, held_out: int = 15, examples: int = 5) -> dict:
    """Score every held-out posting with `examples` neighbours rated before the cut-off, rank
    by score (ties by posting ID) and report precision@k.

    `index` must be synced with `repository`; `guard` applies to the scored postings and their
    examples. The report holds `k`, `held_out`, `cut_off`, `precision_at_k`, the held-out
    `base_rate` of positives, `mixed_chip_citations` (see there) and per posting its score,
    verdict, example IDs and reasoning; a withheld posting or a failed call is listed under
    `errors` and left out of the ranking.
    """
    report = {"eval": "scoring", "metric": "precision@k on a time split",
              "data": str(repository.root.name), "model": model_name}
    usable = sum(label.verdict is not None for label in repository.labels.values())
    if usable <= held_out:
        return report | {"skipped": f"{usable} usable labels, need more than the {held_out} "
                                    "held out"}
    split = time_split(repository, held_out)
    rows, errors = [], []
    with metered() as meter:
        for posting_id in split.held_out:
            try:
                if (posting := guard.posting(repository, posting_id)) is None:
                    raise ValueError(WITHHELD)
                neighbours = find_similar_labeled(guard, index, repository, posting, examples,
                                                  rated_before=split.cut_off,
                                                  posting_id=posting_id)
                score = score_posting(posting, repository.profile, repository.policy_pack,
                                      neighbours, judge)
            except Exception as error:  # one bad answer must not end the eval
                errors.append({"posting": posting_id, "error": str(error)})
                continue
            rows.append({"posting": posting_id, "score": score.score,
                         "verdict": repository.labels[posting_id].verdict,
                         "example_ids": score.example_ids, "reasoning": score.reasoning})
    rows.sort(key=lambda row: (-row["score"], row["posting"]))
    by_level: dict[str, list[int]] = {}
    for row in rows:
        label = repository.labels[row["posting"]]
        by_level.setdefault(f"{label.verdict}/{label.strength or 'plain'}", []).append(row["score"])
    verdicts = [repository.labels[posting_id].verdict for posting_id in split.held_out]
    return report | {
        "k": k, "held_out": len(split.held_out), "cut_off": split.cut_off.isoformat(),
        "training_labels": len(split.training),
        "precision_at_k": precision_at_k([row["verdict"] for row in rows], k) if rows else None,
        "base_rate": verdicts.count("positive") / len(verdicts),
        "cost_per_posting_usd": meter.cost / len(split.held_out),
        "uncosted_calls": meter.uncosted, "mixed_chip_citations": mixed_chip_citations(
            repository, rows),
        "by_level": {level: {"count": len(scores), "mean_score": sum(scores) / len(scores)}
                     for level, scores in sorted(by_level.items())},
        "scores": rows, "errors": errors,
    }
