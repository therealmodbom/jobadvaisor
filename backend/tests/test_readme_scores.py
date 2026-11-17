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
    return load(FIXTURE_DIRECTORY)


def _scores() -> dict[str, Score]:
    """Every fixture file validated as a `Score`, by posting ID; raises on an invalid file."""
    return {path.stem: Score.model_validate_json(path.read_text())
            for path in sorted(SCORES_ROOT.glob("*.json"))}


def test_every_score_file_validates():
    assert _scores()


def test_files_are_exactly_the_unrated_scorable_demo_postings(demo):
    """The pool image lists "Noch nicht bewertet"; a pass would score each posting no rule blocks.
    The expected set comes from the pool's own ranking over the demo persona without scores."""
    expected = {row["posting_id"] for row in rank(demo, {}, {})
                if row["state"] == "unscored" and not (row["label"] or {}).get("verdict")}
    actual = {path.stem for path in SCORES_ROOT.glob("*.json")}
    assert actual == expected, (
        f"missing: {sorted(expected - actual)}, extra: {sorted(actual - expected)}")


def test_example_ids_are_rated_demo_postings(demo):
    for posting_id, score in _scores().items():
        assert score.example_ids, posting_id
        for example_id in score.example_ids:
            assert example_id in demo.postings, (posting_id, example_id)
            assert demo.labels[example_id].verdict, (posting_id, example_id)
