from datetime import UTC, datetime

import pytest

from jobadvaisor.data.loader import DataRepositoryError
from jobadvaisor.data.models import Pool, PoolPass, PoolSettings, Score
from jobadvaisor.data.writer import (
    append_pass,
    read_pool,
    read_score,
    update_pool_settings,
    write_pool,
    write_score,
)

NOW = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
SCORE = Score(schema_version="1", score=7, reasoning="Fits.", example_ids=["p2"], scored_at=NOW)


def _pass(scored: int) -> PoolPass:
    return PoolPass(finished_at=NOW, scored=scored, corrections=1, rated=12, rate=0.1)


def test_score_round_trip_and_replace(data_repository):
    path = write_score(data_repository, "p1", SCORE)
    assert path == data_repository / "scores/p1.json"
    assert read_score(data_repository, "p1") == SCORE
    newer = SCORE.model_copy(update={"score": 3})
    write_score(data_repository, "p1", newer)
    assert read_score(data_repository, "p1") == newer
    assert [p.name for p in (data_repository / "scores").iterdir()] == ["p1.json"]


def test_missing_score_is_none(data_repository):
    assert read_score(data_repository, "p1") is None


def test_unsupported_score_version_is_refused(data_repository):
    (data_repository / "scores").mkdir()
    (data_repository / "scores/p1.json").write_text(SCORE.model_dump_json().replace('"1"', '"9"'))
    with pytest.raises(DataRepositoryError, match="not supported"):
        read_score(data_repository, "p1")


def test_read_score_refuses_an_unsafe_id(data_repository):
    with pytest.raises(ValueError, match="must match"):
        read_score(data_repository, "../p1")


def test_malformed_score_file_is_refused(data_repository):
    (data_repository / "scores").mkdir()
    (data_repository / "scores/p1.json").write_text("{not json")
    with pytest.raises(DataRepositoryError, match="scores/p1.json"):
        read_score(data_repository, "p1")


def test_update_pool_settings_keeps_the_passes(data_repository):
    append_pass(data_repository, _pass(3))
    pool = update_pool_settings(data_repository, PoolSettings(correction_threshold=2))
    assert pool.settings.correction_threshold == 2 and len(pool.passes) == 1
    assert read_pool(data_repository) == pool


def test_score_for_unknown_posting_is_refused(data_repository):
    with pytest.raises(ValueError, match="no posting postings/p9.json"):
        write_score(data_repository, "p9", SCORE)


def test_missing_pool_is_defaults_with_empty_history(data_repository):
    assert read_pool(data_repository) == Pool(schema_version="1")
    assert read_pool(data_repository).settings == PoolSettings()


def test_append_pass_keeps_earlier_passes(data_repository):
    append_pass(data_repository, _pass(5))
    pool = append_pass(data_repository, _pass(8))
    assert [p.scored for p in pool.passes] == [5, 8]
    assert read_pool(data_repository) == pool
    assert [p.name for p in data_repository.glob("*pool*")] == ["pool.json"]


def test_write_pool_keeps_settings(data_repository):
    pool = Pool(schema_version="1", settings=PoolSettings(correction_rate=0.5), passes=[_pass(1)])
    write_pool(data_repository, pool)
    assert read_pool(data_repository) == pool
