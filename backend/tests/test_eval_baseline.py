"""The baseline row and where non-demo eval reports go."""

import json

import pytest
from conftest import AT, LABEL, POLICY_PACK, POSTING, PROFILE, write_json

from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import load
from jobadvaisor.evals import __main__ as cli
from jobadvaisor.evals.baseline import run
from jobadvaisor.settings import REPOSITORY_ROOT, Settings


def repository_with(tmp_path, decisions: dict[str, tuple[str, str | None]]):
    """A data repository whose posting `<id>` has legacy decision and verdict `decisions[id]`
    (verdict `None`: unlabeled)."""
    write_json(tmp_path / "profile.json", PROFILE)
    write_json(tmp_path / "policy-pack.json", POLICY_PACK)
    for posting_id, (decision, verdict) in decisions.items():
        write_json(tmp_path / f"postings/{posting_id}.json",
                   {**POSTING, "legacy_decision": decision})
        if verdict:
            write_json(tmp_path / f"labels/{posting_id}.json",
                       {**LABEL, "kind": "imported_interest", "verdict": verdict,
                        "rated_at": AT})
    return load(tmp_path)


def test_demo_baseline_puts_kept_postings_first():
    report = run(load(FIXTURE_DIRECTORY), k=5)
    assert report["precision_at_k"] == 1.0
    assert (report["kept"], report["discarded_rated"], report["discarded_positive"]) == (12, 11, 1)


def test_ties_inside_a_group_count_at_their_expected_share(tmp_path):
    repository = repository_with(tmp_path, {
        "k1": ("kept", "positive"), "k2": ("kept", "negative"),
        "d1": ("discarded", "positive"), "d2": ("discarded", "negative"),
        "d3": ("discarded", "negative"), "d4": ("discarded", None)})
    report = run(repository, k=3)
    assert report["precision_at_k"] == pytest.approx((1 + 1 / 3) / 3)


def test_skipped_without_legacy_decisions(data_repository):
    assert run(load(data_repository))["skipped"] == "no labeled posting carries legacy_decision"


def test_skipped_without_a_rated_sample_of_discarded_postings(tmp_path):
    repository = repository_with(tmp_path, {"k1": ("kept", "positive"),
                                            "d1": ("discarded", None)})
    assert run(repository)["skipped"] == "no discarded posting is rated"


def test_non_demo_reports_default_to_the_state_directory(data_repository, tmp_path,
                                                         monkeypatch, capsys):
    state = tmp_path / "state"
    monkeypatch.setattr(cli, "Settings", lambda: Settings(_env_file=None, state_directory=state))
    cli.main(["--data", str(data_repository), "--only", "baseline"])
    [written] = list(state.rglob("evals-*.json"))
    assert json.loads(written.read_text())[0]["eval"] == "baseline"
    assert not written.resolve().is_relative_to(REPOSITORY_ROOT)


def test_non_demo_run_refuses_a_state_directory_inside_the_repository(data_repository,
                                                                       monkeypatch):
    monkeypatch.setattr(cli, "Settings", lambda: Settings(
        _env_file=None, state_directory=REPOSITORY_ROOT / "state"))
    with pytest.raises(SystemExit):
        cli.main(["--data", str(data_repository), "--only", "baseline"])
    assert not (REPOSITORY_ROOT / "state").exists()


def test_demo_run_without_out_writes_no_file(monkeypatch, tmp_path, capsys):
    state = tmp_path / "state"
    monkeypatch.setattr(cli, "Settings", lambda: Settings(_env_file=None, state_directory=state))
    cli.main(["--only", "baseline"])
    assert not list(state.rglob("evals-*.json"))
