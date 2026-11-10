"""The posting pool: ranking, correction counter and exploration mark (`design.md` → One ranking
function). Pure over their inputs (the caller loads repository, scores and pool), so the API,
the scoring pass and later the agent all call the same functions. Row and counter shapes are
the wire contract of `GET /pool`."""

import random
import statistics

from jobadvaisor.data.loader import DataRepository
from jobadvaisor.data.models import Label, Pool, Posting, ReasonChip, Score
from jobadvaisor.tools.exclusions import check_exclusions

FIT_SCORE = 6  # score from which a posting counts as fitting
RATE_MIN_RATINGS = 10  # ratings needed before the correction share counts
# Rank among rated-positive postings: strong first, a plain yes (no strength) between the levels.
STRENGTH_ORDER = {"strong": 0, None: 1, "weak": 2}


def resolve_verdict(verdict: str | None, chips: list[str],
                    known: list[ReasonChip]) -> str:
    """The verdict of a rating with `chips` against the policy pack's `known` chips.

    A given `verdict` is kept whatever the chips say (mixed polarities are fine). Without one it
    is the polarity of the first chip, in the order given, that has a polarity. Raises
    `ValueError` naming every unknown chip ID, or saying the verdict is missing when none can be
    derived."""
    polarity = {chip.id: chip.polarity for chip in known}
    if unknown := [chip for chip in chips if chip not in polarity]:
        raise ValueError("unknown reason chip: " + ", ".join(unknown))
    if verdict:
        return verdict
    for chip in chips:
        if polarity[chip]:
            return polarity[chip]
    raise ValueError("verdict is missing: set one or give a chip with a polarity")


def pass_batch(repository: DataRepository, scores: dict[str, Score], rescore: bool) -> list[str]:
    """Posting IDs, in ID order, a pass would take: every posting without a readable score in
    `scores`, rated or not; with `rescore`, every posting. Exclusion and the content guard are
    the pass's own later steps, so excluded and held postings are still listed here."""
    return sorted(posting_id for posting_id in repository.postings
                  if rescore or posting_id not in scores)


def counter(repository: DataRepository, scores: dict[str, Score], pool: Pool) -> dict:
    """The correction counter: `{corrections, rated, rate, hint, since}`.

    Window: labels of kind `rating` rated strictly after `since` (the last pass's `started_at`,
    else its `finished_at`; null without passes, then every rating counts). `rated` counts those
    whose posting has a score in `scores`, `corrections` those contradicting it. `rate` is
    corrections / rated from `RATE_MIN_RATINGS` ratings on, else null. `hint` is `"rescore"`
    at the pool's threshold or rate, else `"fits"`. A `rating` label always has a verdict (model-
    enforced), so `label.verdict` needs no null check here.
    """
    last = pool.passes[-1] if pool.passes else None
    since = (last.started_at or last.finished_at) if last else None
    rated = corrections = 0
    for posting_id, label in repository.labels.items():
        if (label.kind != "rating" or posting_id not in scores
                or (since is not None and label.rated_at <= since)):
            continue
        rated += 1
        fits = scores[posting_id].score >= FIT_SCORE
        corrections += (label.verdict == "positive") != fits
    rate = corrections / rated if rated >= RATE_MIN_RATINGS else None
    settings = pool.settings
    rescore = corrections >= settings.correction_threshold or (
        rate is not None and rate >= settings.correction_rate)
    return {"corrections": corrections, "rated": rated, "rate": rate,
            "hint": "rescore" if rescore else "fits",
            "since": since.isoformat() if since else None}


def next_pass(repository: DataRepository, scores: dict[str, Score], pool: Pool) -> dict:
    """What the next pass would do: `{count, rescore}`. `rescore` is true when corrections
    were counted (the pass then rescores every posting, rated ones included); `count` is the
    pass batch without excluded and held postings."""
    rescore = counter(repository, scores, pool)["corrections"] > 0
    batch = pass_batch(repository, scores, rescore)
    count = sum(_blocked(repository, repository.postings[i]) is None for i in batch)
    return {"count": count, "rescore": rescore}


def rank(repository: DataRepository, scores: dict[str, Score], score_problems: dict[str, str],
         statuses: tuple[str, ...] = ("open",)) -> list[dict]:
    """Pool rows of the postings whose `status` is in `statuses`, in rank order.

    Row keys: `posting_id, title, company, location_raw, added_at` (ISO), `state` (`scored`,
    `unscored`, `excluded` or `held`), `rules` (exclusion rule IDs), `categories` (guard
    categories), `score` (int or null), `score_problem` (str or null), `label` (`{verdict,
    strength, chips, note, rated_at}` or null), `status`, `origin` (dict or null), `exploration`
    (bool). A label with null verdict is no rating. Group order: positive-rated, unrated scored,
    unrated unscored, negative-rated, excluded, held; ties newest `added_at` first. Within the
    positive-rated group the strength comes first (strong, no strength, weak), then score and
    `rated_at`; a strength never changes the group.
    Exploration marks every fifth place among the open members of the unrated scored group
    with a low-scored posting, picked seeded by the number of label files, so the picks stay
    put until a rating changes; the group's other members follow in score order.
    """
    groups: list[list[dict]] = [[] for _ in range(6)]
    for posting_id, posting in sorted(repository.postings.items()):
        if posting.status in statuses:
            row = _row(repository, posting_id, posting, scores, score_problems)
            groups[_group(row)].append(row)
    for number, group in enumerate(groups):
        group.sort(key=lambda row: row["added_at"], reverse=True)
        if number == 0:
            group.sort(key=lambda row: row["label"]["rated_at"], reverse=True)
        if number in (0, 1, 3):
            group.sort(key=lambda row: -1 if row["score"] is None else row["score"], reverse=True)
        if number == 0:
            group.sort(key=lambda row: STRENGTH_ORDER[row["label"]["strength"]])
    still_open = [row for row in groups[1] if row["status"] == "open"]
    groups[1] = _explore(still_open, len(repository.labels)) + [
        row for row in groups[1] if row["status"] != "open"]
    return [row for group in groups for row in group]


def best_open(repository: DataRepository, scores: dict[str, Score],
              score_problems: dict[str, str], statuses: tuple[str, ...] = ("open",)
              ) -> list[dict]:
    """The rows of `rank` worth applying to, in rank order: without postings rated negative,
    excluded or held, and without the exploration picks, which are a learning aid and no
    recommendation. The agent's `best_open_postings` lists these."""
    return [row for row in rank(repository, scores, score_problems, statuses)
            if row["state"] in ("scored", "unscored") and not row["exploration"]
            and (row["label"] or {}).get("verdict") != "negative"]


def _blocked(repository: DataRepository, posting: Posting) -> tuple[str, list[str]] | None:
    """`("held", categories)` for a flagged, unreleased posting, `("excluded", rules)` for one an
    exclusion rule matches now, else `None`. Held takes precedence."""
    guard = posting.guard
    if guard and guard.flagged and guard.released_at is None:
        return "held", guard.categories
    if rules := check_exclusions(posting, repository.policy_pack.exclusion_rules):
        return "excluded", rules
    return None


def _row(repository: DataRepository, posting_id: str, posting: Posting,
         scores: dict[str, Score], score_problems: dict[str, str]) -> dict:
    blocked = _blocked(repository, posting)
    state = blocked[0] if blocked else "scored" if posting_id in scores else "unscored"
    label = repository.labels.get(posting_id)
    return {
        "posting_id": posting_id, "title": posting.title, "company": posting.company,
        "location_raw": posting.location_raw, "added_at": posting.added_at.isoformat(),
        "state": state,
        "rules": blocked[1] if state == "excluded" else [],
        "categories": blocked[1] if state == "held" else [],
        "score": scores[posting_id].score if posting_id in scores else None,
        "score_problem": score_problems.get(posting_id),
        "label": _label(label), "status": posting.status,
        "origin": posting.origin.model_dump(mode="json") if posting.origin else None,
        "exploration": False}


def _label(label: Label | None) -> dict | None:
    if label is None:
        return None
    return {"verdict": label.verdict, "strength": label.strength, "chips": label.chips,
            "note": label.note, "rated_at": label.rated_at.isoformat()}


def _group(row: dict) -> int:
    verdict = row["label"]["verdict"] if row["label"] else None
    if verdict == "positive":
        return 0
    if verdict == "negative":
        return 3
    return {"scored": 1, "unscored": 2, "excluded": 4, "held": 5}[row["state"]]


def _explore(group: list[dict], seed: int) -> list[dict]:
    """Reposition the exploration picks of `group` (rows in score order); marks them."""
    if not group:
        return group
    median = statistics.median(row["score"] for row in group)
    below = sorted((row for row in group if row["score"] < median),
                   key=lambda row: row["posting_id"])
    chosen = random.Random(seed).sample(below, min(round(len(group) / 5), len(below)))
    picks = [row | {"exploration": True} for row in group if row in chosen]
    rest = [row for row in group if row not in chosen]
    result: list[dict] = []
    while picks or rest:
        takes_pick = picks and (len(result) + 1) % 5 == 0 or not rest
        result.append(picks.pop(0) if takes_pick else rest.pop(0))
    return result
