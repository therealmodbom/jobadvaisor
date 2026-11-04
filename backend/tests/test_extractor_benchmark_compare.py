"""Comparing stored benchmark runs, settling their disagreements, and the history view."""

import json
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from conftest import POSTING, ScriptedModel, unknown_features, write_json
from test_eval_agent import PricedModel

from jobadvaisor.data.loader import load
from jobadvaisor.evals import extractor_benchmark
from jobadvaisor.index import state_path
from jobadvaisor.settings import Settings

START = datetime(2026, 10, 28, 9, 30, 15, tzinfo=UTC)

# What each run answers per posting title; everything else is "unknown". Against model A, model B
# differs on p1 in a labelled feature (seniority), on p2 in one unlabelled feature (domain; its
# role_type differs only by case) and on p3 in two (seniority, role_type).
A = {"Backend Engineer": {"seniority": "senior", "role_type": "backend"},
     "Data Engineer": {"seniority": "junior", "role_type": "data", "domain": "fintech"},
     "Cloud Engineer": {"seniority": "junior", "role_type": "cloud"}}
B = {"Backend Engineer": {"seniority": "junior", "role_type": "backend"},
     "Data Engineer": {"seniority": "junior", "role_type": "DATA", "domain": "health"},
     "Cloud Engineer": {"seniority": "senior", "role_type": "devops"}}


class PricedScripted(ScriptedModel):
    """A scripted extractor whose every answer costs one `PricedModel` call (0.25)."""

    def _answer(self, schema, messages):
        PricedModel().invoke(messages)
        return super()._answer(schema, messages)


@pytest.fixture
def world(data_repository, tmp_path_factory, deepeval):
    """A three-posting repository (p1 Backend, p2 Data, p3 Cloud Engineer) with seniority labels
    for p1 and p2, and `store(model, answers, limit=None)` running a stub extractor into a state
    directory outside the repository. `world.state` is the repository's state path."""
    write_json(data_repository / "postings/p3.json", {**POSTING, "title": "Cloud Engineer"})
    write_json(data_repository / "extraction-labels.json", {
        "schema_version": "1",
        "labels": {"p1": {"seniority": "senior"}, "p2": {"seniority": "junior"}}})
    repository = load(data_repository)
    settings = Settings(_env_file=None, state_directory=tmp_path_factory.mktemp("compare-state"))
    clock = iter(START + timedelta(seconds=n) for n in range(100))

    def store(model, answers, limit=None):
        def answer(schema, prompt):
            title = next(title for title in answers if title in prompt)
            return unknown_features(schema, prompt) | answers[title]
        record, _ = extractor_benchmark.run(
            repository, settings, deepeval, model=model, base_url=None,
            chat=PricedScripted(answer), limit=limit, now=next(clock))
        return record["run_id"]

    return SimpleNamespace(repository=repository, settings=settings, store=store,
                           state=state_path(settings, repository.root))


def labels_of(world):
    return world.repository.extraction_labels.labels


def test_two_runs_agree_per_feature_over_the_postings_both_answered(world):
    first, second = world.store("vendor/a", A), world.store("vendor/b", B)
    result = extractor_benchmark.compare(world.state, [first, second], labels_of(world))
    assert result["postings"] == 3
    assert result["agreement"]["seniority"] == {"value": pytest.approx(1 / 3), "postings": 3}
    assert result["agreement"]["role_type"] == {"value": pytest.approx(2 / 3), "postings": 3}
    assert result["agreement"]["domain"] == {"value": pytest.approx(2 / 3), "postings": 3}
    assert result["agreement"]["tech_stack"] == {"value": 1.0, "postings": 3}
    assert [run["model"] for run in result["runs"]] == ["vendor/a", "vendor/b"]


def test_the_report_puts_model_cost_and_latency_side_by_side(world):
    ids = [world.store("vendor/a", A), world.store("vendor/b", B)]
    result = extractor_benchmark.compare(world.state, ids, labels_of(world))
    report = extractor_benchmark.format_comparison(result)
    assert re.search(r"seniority\s+0\.33\s+\(3 postings\)", report)
    assert re.search(r"vendor/a\s+\$0\.2500\s+\d+\.\d+ s", report)
    assert re.search(r"vendor/b\s+\$0\.2500\s+\d+\.\d+ s", report)


def test_runs_over_different_postings_compare_only_the_common_ones(world):
    ids = [world.store("vendor/a", A), world.store("vendor/b", B, limit=2)]
    result = extractor_benchmark.compare(world.state, ids, labels_of(world))
    assert result["postings"] == 2
    assert result["agreement"]["seniority"]["postings"] == 2
    report = extractor_benchmark.format_comparison(result)
    assert "compared on 2 postings that every run answered" in report


def test_fewer_than_two_runs_stop_with_a_message(world):
    only = world.store("vendor/a", A)
    for ids in ([], [only]):
        with pytest.raises(extractor_benchmark.BenchmarkError, match="needs at least two runs"):
            extractor_benchmark.compare(world.state, ids, labels_of(world))


def test_an_unknown_run_is_named(world):
    ids = [world.store("vendor/a", A), "20200101T000000Z-nothing"]
    with pytest.raises(extractor_benchmark.BenchmarkError,
                       match="no stored run 20200101T000000Z-nothing"):
        extractor_benchmark.compare(world.state, ids, labels_of(world))


def disagreements(world):
    ids = [world.store("vendor/a", A), world.store("vendor/b", B)]
    return ids, extractor_benchmark.compare(world.state, ids, labels_of(world))["disagreements"]


def test_unlabelled_disagreements_list_the_most_differing_postings_first(world):
    ids, listed = disagreements(world)
    assert [(item["posting"], item["feature"]) for item in listed] == [
        ("p3", "role_type"), ("p3", "seniority"), ("p2", "domain")]
    assert listed[0] == {"posting": "p3", "feature": "role_type",
                         "runs": {ids[0]: "cloud", ids[1]: "devops"}, "label": None}


def test_a_labelled_case_is_not_listed(world):
    _, listed = disagreements(world)
    assert ("p1", "seniority") not in [(item["posting"], item["feature"]) for item in listed]


def test_the_disagreements_file_is_written_outside_the_repositories(world):
    _, listed = disagreements(world)
    path = extractor_benchmark.write_disagreements(world.state, listed, START)
    assert path == world.state / "benchmark" / "disagreements-20261028T093015Z.json"
    assert json.loads(path.read_text()) == listed
    assert extractor_benchmark.write_disagreements(world.state, [], START) is None


def settled(world, tmp_path, entries):
    path = tmp_path / "disagreements.json"
    path.write_text(json.dumps(entries))
    return extractor_benchmark.settle(world.repository.root, path)


def entry(posting, feature, label):
    return {"posting": posting, "feature": feature, "runs": {"a": "x", "b": "y"}, "label": label}


def test_filled_labels_are_merged_and_empty_entries_are_not(world, tmp_path):
    merged = settled(world, tmp_path, [entry("p3", "seniority", "senior"),
                                       entry("p3", "role_type", None),
                                       entry("p2", "domain", "health")])
    labels = load(world.repository.root).extraction_labels.labels
    assert merged == 2
    assert labels["p3"] == {"seniority": "senior"}
    assert labels["p2"] == {"seniority": "junior", "domain": "health"}
    assert labels["p1"] == {"seniority": "senior"}


def test_a_filled_entry_overwrites_an_existing_label_and_an_empty_one_does_not(world, tmp_path):
    settled(world, tmp_path, [entry("p1", "seniority", "lead"), entry("p2", "seniority", None)])
    labels = load(world.repository.root).extraction_labels.labels
    assert (labels["p1"]["seniority"], labels["p2"]["seniority"]) == ("lead", "junior")


def test_settling_creates_the_labels_file_when_absent_and_keeps_the_minimum(world, tmp_path):
    file = world.repository.root / "extraction-labels.json"
    file.unlink()
    settled(world, tmp_path, [entry("p1", "seniority", "senior")])
    assert load(world.repository.root).extraction_labels.labels == {"p1": {"seniority": "senior"}}
    write_json(file, {"schema_version": "1", "min_accuracy": 0.8, "labels": {}})
    settled(world, tmp_path, [entry("p1", "seniority", "senior")])
    assert load(world.repository.root).extraction_labels.min_accuracy == 0.8


def test_an_entry_the_repository_rejects_leaves_the_labels_file_unchanged(world, tmp_path):
    file = world.repository.root / "extraction-labels.json"
    before = file.read_text()
    with pytest.raises(extractor_benchmark.BenchmarkError, match="salary"):
        settled(world, tmp_path, [entry("p3", "seniority", "senior"), entry("p3", "salary", "x")])
    assert file.read_text() == before


def test_the_history_shows_one_row_per_run_with_its_date(world):
    world.store("vendor/a", A)
    world.store("vendor/b", B)
    table = extractor_benchmark.format_history(extractor_benchmark.read_records(world.state))
    rows = [line for line in table.splitlines() if "vendor/" in line]
    assert len(rows) == 2
    assert "2026-10-28" in rows[0] and "vendor/a" in rows[0]
    assert "extraction accuracy" in rows[0] and "$0.2500" in rows[0]


def test_every_history_row_names_the_run_id_that_compare_takes(world):
    world.store("vendor/a", A)
    world.store("vendor/b", B)
    records = extractor_benchmark.read_records(world.state)
    rows = extractor_benchmark.format_history(records).splitlines()[1:]
    assert [record["run_id"] in row for record, row in zip(records, rows, strict=True)] == [
        True, True]


def test_runs_on_two_days_are_two_history_rows():
    base = {"model": "m", "metrics": [], "cost_per_posting_usd": 0.1, "mean_latency_s": 1.0,
            "postings": 3}
    table = extractor_benchmark.format_history([
        base | {"run_id": "r1", "date": "2026-10-27T08:00:00+00:00"},
        base | {"run_id": "r2", "date": "2026-10-28T08:00:00+00:00"}])
    rows = [line for line in table.splitlines() if "2026-10-2" in line]
    assert len(rows) == 2
    assert "2026-10-27" in rows[0] and "2026-10-28" in rows[1]


def test_the_history_of_an_unused_state_directory_is_empty(world):
    assert extractor_benchmark.read_records(world.state) == []
