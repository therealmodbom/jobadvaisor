"""Regression test for `fixtures/readme-scores/`, the seeded scores the README image script
overlays on a demo persona copy. Not an eval: it checks fixture data, no model is involved."""

import pytest

from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import load
from jobadvaisor.data.models import Score
from jobadvaisor.pool import rank
from jobadvaisor.settings import REPOSITORY_ROOT

SCORES_ROOT = REPOSITORY_ROOT / "fixtures" / "readme-scores"


@pytest.fixture(scope="module")
def demo():
    """The committed demo persona, loaded once per module."""
    return load(FIXTURE_DIRECTORY)


def _scores() -> dict[str, Score]:
    """Every fixture file validated as a `Score`, by posting ID; raises on an invalid file."""
    return {path.stem: Score.model_validate_json(path.read_text())
            for path in sorted(SCORES_ROOT.glob("*.json"))}


def test_every_score_file_validates():
    """Every fixture file parses as a `Score`, and the directory is not empty."""
    assert _scores()


def test_files_are_exactly_the_unrated_scorable_demo_postings(demo):
    """The pool image lists "Noch nicht bewertet"; a pass would score each posting no rule blocks.
    The expected set comes from the pool's own ranking over the demo persona without scores."""
    expected = {row["posting_id"] for row in rank(demo, {}, {})
                if row["state"] == "unscored" and not (row["label"] or {}).get("verdict")}
    actual = {path.stem for path in SCORES_ROOT.glob("*.json")}
    assert actual == expected, (
        f"missing: {sorted(expected - actual)}, extra: {sorted(actual - expected)}")


def test_example_ids_are_three_other_rated_demo_postings(demo):
    """Each score names three distinct demo postings with a verdict, none of them itself."""
    for posting_id, score in _scores().items():
        ids = score.example_ids
        assert len(set(ids)) == len(ids) == 3, (posting_id, ids)
        assert posting_id not in ids, posting_id
        for example_id in ids:
            assert example_id in demo.postings, (posting_id, example_id)
            label = demo.labels.get(example_id)
            assert label is not None and label.verdict, (posting_id, example_id)
