"""Logistic-regression competitor (spec `match-evaluation` → Decision-model competitor): trained
on the extracted features of the labels before the cut-off, ranked on the held-out ones, and
reported with precision@k next to the LLM judge. Skipped below a minimum of training labels.

The fit is a few lines of plain Python, since the feature vectors are small; scikit-learn would
be a dependency for one eval.
"""

import math
import re
from collections import Counter
from collections.abc import Callable

from langchain_core.language_models import BaseChatModel

from jobadvaisor.data.loader import DataRepository
from jobadvaisor.data.models import Feature
from jobadvaisor.evals.cost import metered
from jobadvaisor.evals.scoring import precision_at_k, time_split
from jobadvaisor.tools.extraction import extract_features, feature_set
from jobadvaisor.tools.guard import WITHHELD, ContentGuard

MINIMUM_LABELS = 100
MIN_TOKEN_ROWS = 3
TOKEN = re.compile(r"[a-z0-9+#.]+")


def encoder(features: list[Feature], training: list[dict]) -> Callable[[dict], list[float]]:
    """A function turning one posting's extracted features into a numeric vector: one-hot per
    option for categorical and list features, `[true, false]` for booleans, the value scaled by
    the training maximum for numbers, and for text one entry per token found in at least
    `MIN_TOKEN_ROWS` training rows. "unknown" encodes as zeros."""
    # ponytail: bag of tokens for text features; embeddings if text features ever carry the signal
    vocabularies = {feature.id: sorted(token for token, rows in Counter(
        token for row in training for token in set(_tokens(row.get(feature.id)))).items()
        if rows >= MIN_TOKEN_ROWS) for feature in features if feature.type == "text"}
    scales = {feature.id: max([abs(row[feature.id]) for row in training
                               if isinstance(row.get(feature.id), int | float)
                               and not isinstance(row[feature.id], bool)] or [1]) or 1
              for feature in features if feature.type == "number"}

    def encode(row: dict) -> list[float]:
        vector = []
        for feature in features:
            value = row.get(feature.id)
            match feature.type:
                case "categorical":
                    vector += [int(value == option) for option in feature.options]
                case "list":
                    chosen = value if isinstance(value, list) else []
                    vector += [int(option in chosen) for option in feature.options]
                case "boolean":
                    vector += [int(value is True), int(value is False)]
                case "number":
                    number = isinstance(value, int | float) and not isinstance(value, bool)
                    vector.append(value / scales[feature.id] if number else 0)
                case "text":
                    found = set(_tokens(value))
                    vector += [int(token in found) for token in vocabularies[feature.id]]
        return vector

    return encode


def fit(rows: list[list[float]], targets: list[int], iterations: int = 2000,
        rate: float = 0.5, l2: float = 0.01) -> list[float]:
    """Weights (bias first) of an L2-regularised logistic regression, by batch gradient
    descent from zero, so the result is deterministic."""
    weights = [0.0] * (len(rows[0]) + 1)
    for _ in range(iterations):
        gradient = [0.0] * len(weights)
        for row, target in zip(rows, targets, strict=True):
            error = predict(weights, row) - target
            gradient[0] += error
            for index, value in enumerate(row, 1):
                gradient[index] += error * value
        weights = [weight - rate * (step / len(rows) + (l2 * weight if index else 0))
                   for index, (weight, step) in enumerate(zip(weights, gradient, strict=True))]
    return weights


def predict(weights: list[float], row: list[float]) -> float:
    """The probability of a positive verdict for one encoded row."""
    z = weights[0] + sum(weight * value for weight, value in zip(weights[1:], row, strict=True))
    return 1 / (1 + math.exp(-max(min(z, 50), -50)))


def run(repository: DataRepository, guard: ContentGuard, extractor: BaseChatModel,
        model_name: str, k: int = 5, held_out: int = 15,
        minimum_labels: int = MINIMUM_LABELS) -> dict:
    """Extract features from every usable labeled posting with the `extractor`, fit on the
    labels before the cut-off, rank the held-out postings by predicted probability (ties by
    posting ID) and report precision@k, as the scoring eval does. Skipped, without any model
    call, with fewer than `minimum_labels` training labels. A withheld posting or a failed
    extraction is listed under `errors` and left out."""
    report = {"eval": "logistic_regression", "metric": "precision@k on a time split",
              "data": repository.root.name, "extractor_model": model_name,
              "minimum_labels": minimum_labels}
    usable = sum(label.verdict is not None for label in repository.labels.values())
    if usable <= held_out:
        return report | {"skipped": f"{usable} usable labels, need more than the {held_out} "
                                    "held out"}
    split = time_split(repository, held_out)
    if len(split.training) < minimum_labels:
        return report | {"skipped": f"{len(split.training)} training labels, need at least "
                                    f"{minimum_labels}"}
    features = feature_set(repository.policy_pack.feature_set)
    extracted, errors = {}, []
    with metered() as meter:
        for posting_id in split.training + split.held_out:
            try:
                if (posting := guard.posting(repository, posting_id)) is None:
                    raise ValueError(WITHHELD)
                extracted[posting_id] = extract_features(posting, features, extractor,
                                                         repository.company_of(posting))
            except Exception as error:  # one bad answer must not end the eval
                errors.append({"posting": posting_id, "error": str(error)})
    training = [posting_id for posting_id in split.training if posting_id in extracted]
    encode = encoder(features, [extracted[posting_id] for posting_id in training])
    weights = fit([encode(extracted[posting_id]) for posting_id in training],
                  [int(repository.labels[posting_id].verdict == "positive")
                   for posting_id in training])
    ranked = sorted((-predict(weights, encode(extracted[posting_id])), posting_id)
                    for posting_id in split.held_out if posting_id in extracted)
    verdicts = [repository.labels[posting_id].verdict for posting_id in split.held_out]
    return report | {
        "k": k, "held_out": len(split.held_out), "cut_off": split.cut_off.isoformat(),
        "training_labels": len(split.training),
        "precision_at_k": precision_at_k([repository.labels[posting_id].verdict
                                          for _, posting_id in ranked], k) if ranked else None,
        "base_rate": verdicts.count("positive") / len(verdicts),
        "ranking": [{"posting": posting_id, "probability": round(-negative, 3),
                     "verdict": repository.labels[posting_id].verdict}
                    for negative, posting_id in ranked],
        "cost_usd": meter.cost, "uncosted_calls": meter.uncosted, "errors": errors,
    }


def _tokens(value) -> list[str]:
    return TOKEN.findall(value.casefold()) if isinstance(value, str) and value != "unknown" \
        else []
