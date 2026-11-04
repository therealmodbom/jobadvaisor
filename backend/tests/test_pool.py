from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jobadvaisor.data.loader import DataRepository
from jobadvaisor.data.models import (
    Guard,
    Label,
    PolicyPack,
    Pool,
    PoolPass,
    PoolSettings,
    Posting,
    Profile,
    Score,
)
from jobadvaisor.data.writer import read_scores, write_score
from jobadvaisor.pool import best_open, counter, next_pass, pass_batch, rank, resolve_verdict

T0 = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
PACK = PolicyPack.model_validate({
    "schema_version": "1",
    "exclusion_rules": [{"id": "no-sales", "field": "title", "operator": "contains_any",
                         "value": ["sales"]}]})


def posting(title="Engineer", day=0, status="open", guard=None) -> Posting:
    return Posting(schema_version="2", title=title, company="Acme", location_raw="Kiel",
                   text="Text", source_type="text", added_at=T0 + timedelta(days=day),
                   status=status, guard=guard)


def score(value: int) -> Score:
    return Score(schema_version="1", score=value, reasoning="r", scored_at=T0)


def label(verdict="positive", at=T0 + timedelta(days=1), kind="rating", chips=(),
          strength=None) -> Label:
    return Label(schema_version="1", kind=kind, verdict=verdict, strength=strength,
                 chips=list(chips), rated_at=at)


def repo(postings: dict[str, Posting], labels: dict[str, Label] | None = None) -> DataRepository:
    return DataRepository(Path("."), Profile(schema_version="1", summary="s"), PACK, postings,
                          labels or {})


def ids(rows) -> list[str]:
    return [row["posting_id"] for row in rows]


def test_rank_groups_in_order_and_ties_by_newest():
    held = Guard(flagged=True, categories=["injection"], checked_by="t", checked_at=T0)
    postings = {
        "pos-low": posting(), "unrated-high": posting(), "unrated-mid-old": posting(day=1),
        "unrated-mid-new": posting(day=2), "unscored": posting(), "neg": posting(),
        "excl": posting("Sales Rep"), "held": posting(guard=held)}
    scores = {"pos-low": score(4), "unrated-high": score(9), "unrated-mid-old": score(5),
              "unrated-mid-new": score(5), "neg": score(9)}
    labels = {"pos-low": label(), "neg": label("negative")}
    rows = rank(repo(postings, labels), scores, {})
    assert ids(rows) == ["pos-low", "unrated-high", "unrated-mid-new", "unrated-mid-old",
                         "unscored", "neg", "excl", "held"]
    by_id = {row["posting_id"]: row for row in rows}
    assert by_id["excl"]["state"] == "excluded" and by_id["excl"]["rules"] == ["no-sales"]
    assert by_id["held"]["state"] == "held" and by_id["held"]["categories"] == ["injection"]
    assert by_id["unscored"]["state"] == "unscored" and by_id["unscored"]["score"] is None
    assert by_id["pos-low"]["label"]["verdict"] == "positive"
    assert by_id["unrated-high"] | {"exploration": False} == by_id["unrated-high"]


def test_rank_positive_group_by_score_then_rated_at():
    postings = {"a": posting(), "b": posting(), "c": posting(), "d": posting()}
    scores = {"a": score(3), "b": score(8), "c": score(3)}
    labels = {k: label(at=T0 + timedelta(days=n)) for n, k in enumerate("abcd", 1)}
    assert ids(rank(repo(postings, labels), scores, {})) == ["b", "c", "a", "d"]


def test_rank_positive_group_orders_strong_then_plain_then_weak():
    postings = {k: posting() for k in ("weak-high", "plain-high", "strong-low", "weak-new")}
    scores = {"weak-high": score(9), "plain-high": score(9), "strong-low": score(2),
              "weak-new": score(9)}
    labels = {"weak-high": label(strength="weak"), "plain-high": label(),
              "strong-low": label(strength="strong"),
              "weak-new": label(strength="weak", at=T0 + timedelta(days=5))}
    rows = rank(repo(postings, labels), scores, {})
    assert ids(rows) == ["strong-low", "plain-high", "weak-new", "weak-high"]
    assert [row["label"]["strength"] for row in rows] == ["strong", None, "weak", "weak"]


def test_a_strength_never_moves_a_posting_out_of_its_direction_group():
    postings = {"weak-yes": posting(), "unrated": posting(), "weak-no": posting(),
                "strong-no": posting()}
    scores = {"weak-yes": score(1), "unrated": score(9), "weak-no": score(9),
              "strong-no": score(9)}
    labels = {"weak-yes": label(strength="weak"), "weak-no": label("negative", strength="weak"),
              "strong-no": label("negative", strength="strong")}
    got = ids(rank(repo(postings, labels), scores, {}))
    assert got[:2] == ["weak-yes", "unrated"] and set(got[2:]) == {"weak-no", "strong-no"}


def test_best_open_leaves_a_weak_negative_out_and_keeps_every_positive_level():
    postings = {k: posting() for k in ("strong", "weak", "weak-no")}
    scores = {k: score(8) for k in postings}
    labels = {"strong": label(strength="strong"), "weak": label(strength="weak"),
              "weak-no": label("negative", strength="weak")}
    assert ids(best_open(repo(postings, labels), scores, {})) == ["strong", "weak"]


def test_a_weak_negative_on_a_high_score_counts_as_one_correction():
    repository = repo({"p": posting()}, {"p": label("negative", strength="weak")})
    assert counter(repository, {"p": score(8)}, _pool())["corrections"] == 1


def test_rank_filters_by_status():
    postings = {"o": posting(), "a": posting(status="applied")}
    assert ids(rank(repo(postings), {}, {})) == ["o"]
    both = rank(repo(postings), {}, {}, statuses=("open", "applied", "done"))
    assert sorted(ids(both)) == ["a", "o"]


def test_rank_shows_score_problem_and_ignores_null_verdict_label():
    labels = {"p": label(None, kind="imported_not_preference")}
    [row] = rank(repo({"p": posting()}, labels), {}, {"p": "scores/p.json: broken"})
    assert row["state"] == "unscored" and row["score_problem"] == "scores/p.json: broken"
    assert row["label"]["verdict"] is None


def _pool(*passes, **settings) -> Pool:
    return Pool(schema_version="1", settings=PoolSettings(**settings), passes=list(passes))


def _rated(n: int, wrong: int, at=T0 + timedelta(days=1)):
    """n rated postings scored 8; the first `wrong` rated negative (corrections)."""
    postings = {f"r{i}": posting() for i in range(n)}
    scores = {f"r{i}": score(8) for i in range(n)}
    labels = {f"r{i}": label("negative" if i < wrong else "positive", at, chips=["x"])
              for i in range(n)}
    return repo(postings, labels), scores


def test_correction_counts_agreement_and_unscored_do_not():
    repository, scores = _rated(2, 1)
    repository.postings["u"] = posting()
    repository.labels["u"] = label("negative")
    got = counter(repository, scores, _pool())
    assert (got["corrections"], got["rated"], got["rate"], got["since"]) == (1, 2, None, None)


def test_low_score_rated_positive_is_a_correction():
    repository = repo({"p": posting()}, {"p": label("positive")})
    assert counter(repository, {"p": score(5)}, _pool())["corrections"] == 1


def test_rating_before_since_does_not_count_and_started_at_wins():
    repository, scores = _rated(1, 1, at=T0 + timedelta(days=1))
    old = PoolPass(finished_at=T0 + timedelta(days=3), scored=1, corrections=0, rated=0)
    assert counter(repository, scores, _pool(old))["rated"] == 0
    started = old.model_copy(update={"started_at": T0})
    got = counter(repository, scores, _pool(started))
    assert got["rated"] == 1 and got["since"] == T0.isoformat()
    old_since = counter(repository, scores, _pool(old))["since"]
    assert old_since == (T0 + timedelta(days=3)).isoformat()


def test_imported_labels_are_not_in_the_window():
    repository = repo({"p": posting()}, {"p": label(kind="imported_interest")})
    assert counter(repository, {"p": score(2)}, _pool())["rated"] == 0


def test_rate_needs_ten_ratings_and_hint_follows_threshold_and_rate():
    repository, scores = _rated(9, 3)
    got = counter(repository, scores, _pool(correction_threshold=4, correction_rate=0.3))
    assert (got["rate"], got["hint"]) == (None, "fits")
    got = counter(repository, scores, _pool(correction_threshold=3, correction_rate=0.9))
    assert got["hint"] == "rescore"
    repository, scores = _rated(10, 3)
    got = counter(repository, scores, _pool(correction_threshold=10, correction_rate=0.3))
    assert (got["rate"], got["hint"]) == (0.3, "rescore")
    got = counter(repository, scores, _pool(correction_threshold=10, correction_rate=0.31))
    assert got["hint"] == "fits"


def _exploration_repo(values: list[int]):
    postings = {f"p{i:02d}": posting() for i in range(len(values))}
    scores = {f"p{i:02d}": score(v) for i, v in enumerate(values)}
    return repo(postings), scores


def test_exploration_marks_two_of_ten_below_the_median_at_five_and_ten():
    repository, scores = _exploration_repo(list(range(10, 0, -1)))
    rows = rank(repository, scores, {})
    marked = [i for i, row in enumerate(rows, 1) if row["exploration"]]
    assert marked == [5, 10]
    assert all(rows[i - 1]["score"] < 5.5 for i in marked)
    assert ids(rank(repository, scores, {})) == ids(rows)


def test_exploration_seed_is_the_label_count():
    values = list(range(10, 0, -1))
    picks = set()
    for extra in range(6):
        repository, scores = _exploration_repo(values)
        for j in range(extra):  # labels of postings outside the pool view (done)
            repository.postings[f"d{j}"] = posting(status="done")
            repository.labels[f"d{j}"] = label()
        picks.add(tuple(row["posting_id"] for row in rank(repository, scores, {})
                        if row["exploration"]))
    assert len(picks) > 1


def test_exploration_with_one_below_marks_one_and_none_below_marks_none():
    repository, scores = _exploration_repo([9, 9, 9, 9, 9, 9, 9, 9, 9, 1])
    rows = rank(repository, scores, {})
    assert sum(row["exploration"] for row in rows) == 1
    assert rows[4]["exploration"] and rows[4]["posting_id"] == "p09"
    repository, scores = _exploration_repo([5] * 10)
    assert not any(row["exploration"] for row in rank(repository, scores, {}))


def test_pass_batch_skips_rated_and_scored_unless_rescoring():
    repository = repo({"rated": posting(), "scored": posting(), "bad": posting(), "new": posting()},
                      {"rated": label()})
    scores = {"scored": score(5), "rated": score(5)}
    assert pass_batch(repository, scores, False) == ["bad", "new"]
    assert pass_batch(repository, scores, True) == ["bad", "new", "scored"]


def test_exploration_runs_over_open_rows_only():
    repository, scores = _exploration_repo(list(range(10, 0, -1)))
    open_rows = rank(repository, scores, {})
    for i, status in enumerate(["done", "applied", "done", "done"]):
        repository.postings[f"x{i}"] = posting(status=status)
        scores[f"x{i}"] = score(1)
    rows = rank(repository, scores, {}, statuses=("open", "applied", "done"))
    open_part = [row for row in rows if row["status"] == "open"]
    assert [i for i, row in enumerate(open_part, 1) if row["exploration"]] == [5, 10]
    assert ids(open_part) == ids(open_rows)
    assert ids(rows[10:]) == ["x0", "x1", "x2", "x3"]
    assert not any(row["exploration"] for row in rows[10:])


def test_pass_batch_takes_postings_with_a_null_verdict_label():
    repository = repo({"imported": posting(), "rated": posting()},
                      {"imported": label(None, kind="imported_not_preference"), "rated": label()})
    assert pass_batch(repository, {}, False) == ["imported"]


def test_corrupt_score_file_counts_as_unscored(tmp_path):
    (tmp_path / "scores").mkdir()
    (tmp_path / "scores/bad.json").write_text("{nope")
    (tmp_path / "scores/Not Safe.json").write_text("{}")
    scores, problems = read_scores(tmp_path)
    assert scores == {} and list(problems) == ["bad"] and "scores/bad.json" in problems["bad"]
    assert pass_batch(repo({"bad": posting()}), scores, False) == ["bad"]


def test_next_pass_excludes_excluded_and_held_and_follows_corrections():
    held = Guard(flagged=True, checked_by="t", checked_at=T0)
    repository = repo({"ok": posting(), "excl": posting("Sales"), "held": posting(guard=held)})
    assert next_pass(repository, {}, _pool()) == {"count": 1, "rescore_unrated": False}
    repository, scores = _rated(2, 1)
    repository.postings["ok"] = posting()
    assert next_pass(repository, scores, _pool()) == {"count": 1, "rescore_unrated": True}


def test_read_scores_round_trip(tmp_path):
    (tmp_path / "postings").mkdir()
    (tmp_path / "postings/p1.json").write_text(posting().model_dump_json())
    write_score(tmp_path, "p1", score(6))
    assert read_scores(tmp_path) == ({"p1": score(6)}, {})
    assert read_scores(tmp_path / "missing") == ({}, {})


CHIPS = PolicyPack.model_validate({"schema_version": "1", "reason_chips": [
    {"id": "remote", "label": "remote", "polarity": "positive"},
    {"id": "onsite", "label": "onsite only", "polarity": "negative"},
    {"id": "other", "label": "other"}]}).reason_chips


def test_a_given_verdict_is_kept_whatever_the_chips_say():
    assert resolve_verdict("negative", ["remote"], CHIPS) == "negative"
    assert resolve_verdict("positive", [], CHIPS) == "positive"


def test_the_verdict_is_the_polarity_of_the_first_chip_that_has_one():
    assert resolve_verdict(None, ["other", "onsite", "remote"], CHIPS) == "negative"
    assert resolve_verdict(None, ["remote", "onsite"], CHIPS) == "positive"


def test_no_verdict_to_derive_raises_naming_the_missing_verdict():
    for chips in ([], ["other"]):
        with pytest.raises(ValueError, match="verdict is missing"):
            resolve_verdict(None, chips, CHIPS)


def test_an_unknown_chip_raises_naming_it_even_with_a_verdict():
    with pytest.raises(ValueError, match="nope"):
        resolve_verdict("positive", ["remote", "nope"], CHIPS)
