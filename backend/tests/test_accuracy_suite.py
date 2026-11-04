"""The accuracy suite for `deepeval test run` (`tests/accuracy_suite.py`), with a stub extractor."""

import subprocess
import sys

import accuracy_suite
import pytest
from conftest import POSTING, ScriptedModel, unknown_features, write_json

from jobadvaisor.data.loader import load
from jobadvaisor.evals import extractor_benchmark
from jobadvaisor.evals.extraction_accuracy import check_minimum
from jobadvaisor.settings import REPOSITORY_ROOT, Settings


def senior_only_for_backend(schema, prompt):
    return unknown_features(schema, prompt) | {
        "seniority": "senior" if "Backend Engineer" in prompt else "junior"}


@pytest.fixture
def suite(monkeypatch, data_repository, tmp_path_factory, deepeval):
    """The suite's inputs: three postings, seniority labels (p1 right, p2 and p3 wrong for the
    stub, which calls everything but the Backend Engineer junior) and a state directory outside
    the repository; the stub extractor and the loaded DeepEval stand in for the real ones."""
    write_json(data_repository / "postings/p3.json", {**POSTING, "title": "Cloud Engineer"})
    labels = {"p1": {"seniority": "senior"}, "p2": {"seniority": "senior"},
              "p3": {"seniority": "senior"}}
    write_json(data_repository / "extraction-labels.json", {"schema_version": "1",
                                                           "labels": labels})
    settings = Settings(_env_file=None, data_repository=data_repository,
                        state_directory=tmp_path_factory.mktemp("suite-state"),
                        extractor_model="vendor/configured")
    monkeypatch.setattr(accuracy_suite, "Settings", lambda: settings)
    monkeypatch.setattr(accuracy_suite, "chat_model",
                        lambda role, given: ScriptedModel(senior_only_for_backend))
    monkeypatch.setattr(accuracy_suite, "load_deepeval", lambda state: deepeval)
    return settings


def test_the_default_test_run_collects_none_of_the_suite():
    process = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=REPOSITORY_ROOT / "backend", capture_output=True, text=True, timeout=300)
    assert process.returncode == 0, process.stdout[-2000:]
    assert "tests/accuracy_suite.py" not in process.stdout
    assert "tests/test_extractor_benchmark.py" in process.stdout


def test_the_suite_scores_the_labelled_postings_like_the_command(suite, deepeval):
    per_feature, minimum = accuracy_suite.run_suite()
    assert minimum is None
    assert per_feature == {"seniority": {"accuracy": pytest.approx(1 / 3), "cases": 3}}
    record, _ = extractor_benchmark.run(load(suite.data_repository), suite, deepeval,
                              model="vendor/configured", base_url=None,
                              chat=ScriptedModel(senior_only_for_backend))
    assert record["metrics"][0]["per_feature"] == {"seniority": {"value": pytest.approx(1 / 3),
                                                                 "cases": 3}}


def test_the_suite_extracts_only_the_labelled_postings(suite, monkeypatch):
    write_json(suite.data_repository / "extraction-labels.json", {
        "schema_version": "1", "labels": {"p1": {"seniority": "senior"}}})
    asked = []
    monkeypatch.setattr(accuracy_suite, "chat_model", lambda role, given: ScriptedModel(
        lambda schema, prompt: asked.append(prompt) or senior_only_for_backend(schema, prompt)))
    per_feature, _ = accuracy_suite.run_suite()
    assert per_feature == {"seniority": {"accuracy": 1.0, "cases": 1}}
    assert len(asked) == 1


def test_the_suite_fails_below_the_minimum_and_names_both_figures(suite):
    write_json(suite.data_repository / "extraction-labels.json", {
        "schema_version": "1", "min_accuracy": 0.9,
        "labels": {"p1": {"seniority": "senior"}, "p2": {"seniority": "senior"}}})
    per_feature, minimum = accuracy_suite.run_suite()
    with pytest.raises(AssertionError, match=r"accuracy 0\.50 is below the minimum 0\.90"):
        check_minimum(per_feature, minimum)


def test_the_suite_passes_at_or_above_the_minimum_and_without_one():
    check_minimum({"seniority": {"accuracy": 0.9, "cases": 10}}, 0.9)
    check_minimum({"seniority": {"accuracy": 0.1, "cases": 10}}, None)


def test_the_suite_is_skipped_with_the_reason_when_there_are_no_labels(suite):
    (suite.data_repository / "extraction-labels.json").unlink()
    with pytest.raises(pytest.skip.Exception, match="holds no extraction labels"):
        accuracy_suite.run_suite()


def test_the_suite_refuses_a_state_directory_inside_a_repository(suite):
    inside = Settings(_env_file=None, data_repository=suite.data_repository,
                      state_directory=suite.data_repository / "state")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(accuracy_suite, "Settings", lambda: inside)
        with pytest.raises(extractor_benchmark.StateDirectoryError, match="STATE_DIRECTORY"):
            accuracy_suite.run_suite()
