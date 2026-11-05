"""Hosted decision-model competitor (spec `match-evaluation` → Hosted decision-model
competitor): the decision model scores the held-out postings as one `score` question, on the
judge's own prompt and examples, and fills the categorical features as `choice` questions on
the feature-extraction postings. Reported with precision@k, the router's cost per posting and
per-field accuracy, next to the LLM judge's and the extractor's rows.

The router accepts at most 10 score levels, so the scale is 1–10, and the answer is a fractional
level index (0–9).
"""

import json
from statistics import mean

from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import DataRepository
from jobadvaisor.data.models import Feature, PolicyPack, Posting, Profile
from jobadvaisor.evals.cost import record_call
from jobadvaisor.evals.feature_extraction import EXPECTED_FILE
from jobadvaisor.evals.scoring import precision_at_k, time_split
from jobadvaisor.index import LabelIndex
from jobadvaisor.llm import Decider
from jobadvaisor.tools.extraction import UNKNOWN, feature_set
from jobadvaisor.tools.guard import WITHHELD, ContentGuard
from jobadvaisor.tools.prompts import DATA_RULE, posting_block
from jobadvaisor.tools.scoring import scoring_prompt
from jobadvaisor.tools.similar import Example, find_similar_labeled

SCORE_LEVELS = [str(level) for level in range(1, 11)]
FIT_QUESTION = ("How well does the posting to score fit the user? Weigh the user's rated "
                "postings, which show how they decided before. 1 means no fit, 10 an excellent "
                "fit.")


def ask(decider: Decider, content: str, questions: dict[str, dict]) -> tuple[dict, float | None]:
    """The decision model's answers to `questions` about `content`, and the call's reported
    cost (`None` when the router reports none)."""
    response = decider.client.chat.completions.create(
        model=decider.model, messages=[{"role": "user", "content": content}],
        response_format={"type": "questions", "questions": questions})
    return (json.loads(response.choices[0].message.content),
            getattr(response.usage, "cost", None) if response.usage else None)


def decider_score(decider: Decider, posting: Posting, profile: Profile, policy_pack: PolicyPack,
                  examples: list[Example]) -> float:
    """The posting's fit from 1 to 10 (fractional), from one `score` question on the judge's
    prompt."""
    return _score(decider, posting, profile, policy_pack, examples)[0]


def run_scoring(repository: DataRepository, index: LabelIndex, guard: ContentGuard,
                decider: Decider, k: int = 5, held_out: int = 15, examples: int = 5) -> dict:
    """Score the held-out postings with `examples` neighbours rated before the cut-off, as the
    scoring eval does, and report precision@k and the cost per posting. `index` must be synced
    with `repository`."""
    report = {"metric": "precision@k on a time split and cost per posting"}
    usable = sum(label.verdict is not None for label in repository.labels.values())
    if usable <= held_out:
        return report | {"skipped": f"{usable} usable labels, need more than the {held_out} "
                                    "held out"}
    split = time_split(repository, held_out)
    rows, errors, costs = [], [], []
    for posting_id in split.held_out:
        try:
            if (posting := guard.posting(repository, posting_id)) is None:
                raise ValueError(WITHHELD)
            neighbours = find_similar_labeled(guard, index, repository, posting, examples,
                                              rated_before=split.cut_off, posting_id=posting_id)
            fit, cost = _score(decider, posting, repository.profile, repository.policy_pack,
                               neighbours)
        except Exception as error:  # one bad answer must not end the eval
            errors.append({"posting": posting_id, "error": str(error)})
            continue
        costs.append(cost)
        rows.append({"posting": posting_id, "score": fit,
                     "verdict": repository.labels[posting_id].verdict,
                     "example_ids": [neighbour.posting_id for neighbour in neighbours]})
    rows.sort(key=lambda row: (-row["score"], row["posting"]))
    known = [cost for cost in costs if cost is not None]
    return report | {
        "k": k, "held_out": len(split.held_out), "cut_off": split.cut_off.isoformat(),
        "precision_at_k": precision_at_k([row["verdict"] for row in rows], k) if rows else None,
        "cost_per_posting_usd": mean(known) if known else None,
        "uncosted_calls": len(costs) - len(known), "scores": rows, "errors": errors}


def run_extraction(repository: DataRepository, decider: Decider) -> dict:
    """Fill the categorical features of the 20 feature-extraction postings with one `choice`
    question each ("unknown" as an extra option) and report per-field accuracy and the cost per
    posting. Data other than the demo persona is skipped, since only it has expectations."""
    report = {"metric": "per-field accuracy for the categorical features"}
    if repository.root.resolve() != FIXTURE_DIRECTORY.resolve():
        return report | {"skipped": "expected features exist only for the demo persona"}
    expected = json.loads(EXPECTED_FILE.read_text())["postings"]
    features = [feature for feature in feature_set(repository.policy_pack.feature_set)
                if feature.type == "categorical"]
    questions = {feature.id: choice_question(feature) for feature in features}
    correct = {feature.id: [] for feature in features}
    mismatches, errors, costs = [], [], []
    for posting_id, wanted in expected.items():
        try:
            answers, cost = ask(decider, DATA_RULE.format(tag="posting") + "\n\n"
                                + posting_block(repository.postings[posting_id]), questions)
            costs.append(cost)
            got = {feature_id: answers[feature_id]["choice"] for feature_id in questions}
        except Exception as error:  # one bad answer must not end the eval
            errors.append({"posting": posting_id, "error": str(error)})
            got = {}
        for feature_id in questions:
            same = str(got.get(feature_id)).casefold() == str(wanted[feature_id]).casefold()
            correct[feature_id].append(same)
            if got and not same:
                mismatches.append({"posting": posting_id, "feature": feature_id,
                                   "expected": wanted[feature_id], "got": got[feature_id]})
    accuracy = {feature_id: mean(hits) for feature_id, hits in correct.items()}
    known = [cost for cost in costs if cost is not None]
    return report | {"postings": len(expected), "accuracy": accuracy,
                     "overall": mean(accuracy.values()) if accuracy else None,
                     "cost_per_posting_usd": mean(known) if known else None,
                     "mismatches": mismatches, "errors": errors}


def run(repository: DataRepository, index: LabelIndex, guard: ContentGuard,
        decider: Decider | None) -> dict:
    """Both competitor rows, or the skip reason when no decision model is named (`--model`)."""
    if decider is None:
        return {"eval": "decider_competitor", "skipped": "--model is not given"}
    return {"eval": "decider_competitor", "model": decider.model, "data": repository.root.name,
            "scoring": run_scoring(repository, index, guard, decider),
            "extraction": run_extraction(repository, decider)}


def _score(decider: Decider, posting: Posting, profile: Profile, policy_pack: PolicyPack,
           examples: list[Example]) -> tuple[float, float | None]:
    instructions, message = scoring_prompt(posting, profile, policy_pack, examples)
    answers, cost = ask(decider, f"{instructions}\n\n{message}", {
        "fit": {"type": "score", "instructions": FIT_QUESTION, "criteria": SCORE_LEVELS}})
    return 1 + answers["fit"]["score"], cost


def choice_question(feature: Feature) -> dict:
    """The `choice` question for a categorical `feature`: its options plus "unknown"."""
    return {"type": "choice",
            "instructions": f"{feature.description}, as the posting states it; \"{UNKNOWN}\" "
                            "when it does not say.",
            "criteria": dict.fromkeys(feature.options + [UNKNOWN])}


def extract_choices(posting: Posting, features: list[Feature], decider: Decider) -> dict:
    """Feature ID → the decision model's choice, for the categorical features in `features` only
    (it has no question type for the others). The call's reported cost goes to the active meter
    (`evals.cost`). Raises what the call raises or `KeyError` for a missing answer."""
    questions = {feature.id: choice_question(feature)
                 for feature in features if feature.type == "categorical"}
    if not questions:
        return {}
    answers, cost = ask(decider, DATA_RULE.format(tag="posting") + "\n\n"
                        + posting_block(posting), questions)
    record_call(cost)
    return {feature_id: answers[feature_id]["choice"] for feature_id in questions}
