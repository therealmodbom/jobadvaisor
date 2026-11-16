"""The background run of chosen alert-mail entries (`design.md` → Run)."""

import threading
import time

import pytest
from conftest import FakeStructuredModel, write_json
from test_triage_graph import POLICY_PACK

import jobadvaisor.intake.alert_runs as runs_module
from jobadvaisor.intake.alert_runs import AlertRunBusyError, AlertRuns, RunEntry
from jobadvaisor.intake.fetch import guarded_link
from jobadvaisor.intake.postings import Intake, PostingNotFoundError
from jobadvaisor.tools.guard import ContentGuard

LINKS = [f"https://jobs.example.org/stelle/{n}" for n in (1, 2, 3)]


@pytest.fixture
def runs(tmp_path):
    write_json(tmp_path / "policy-pack.json", POLICY_PACK)
    return AlertRuns(Intake(tmp_path, FakeStructuredModel(), ContentGuard(None, {})))


def finished(runs: AlertRuns, run_id: str) -> dict:
    for _ in range(300):
        state = runs.read(run_id)
        if state["status"] != "running":
            return state
        time.sleep(0.01)
    raise AssertionError("run did not finish")


def fake_add(outcomes: dict, seen: list | None = None):
    """An `add_from_url` stand-in: per URL, a posting ID with a duplicate reason, or an
    exception to raise; records `(url, guarded_link, allow_text_duplicate)`."""
    def add(intake, url, *, allow_text_duplicate=False):
        if seen is not None:
            seen.append((url, guarded_link.get(), allow_text_duplicate))
        outcome = outcomes[url]
        if isinstance(outcome, Exception):
            raise outcome
        posting_id, reason = outcome
        if reason == "text" and allow_text_duplicate:
            posting_id, reason = "neu", None
        return posting_id, None, reason, [{"step": "plain", "url": url, "outcome": "ok"}]
    return add


def test_a_failed_submit_does_not_block_later_runs(runs, monkeypatch):
    real = runs._executor.submit
    def broken(*args):
        raise RuntimeError("executor down")

    monkeypatch.setattr(runs._executor, "submit", broken)
    with pytest.raises(RuntimeError):
        runs.start([RunEntry(LINKS[0], "A")])
    monkeypatch.setattr(runs._executor, "submit", real)
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({LINKS[0]: ("p1", None)}))
    assert finished(runs, runs.start([RunEntry(LINKS[0], "A")]))["status"] == "done"


def test_the_guard_holds_each_entry_link_and_is_cleared_after(runs, monkeypatch):
    seen = []
    monkeypatch.setattr(runs_module, "add_from_url", fake_add(
        {LINKS[0]: ("a", None), LINKS[1]: ("b", None)}, seen))
    finished(runs, runs.start([RunEntry(LINKS[0], "A"), RunEntry(LINKS[1], "B")]))
    assert [(url, guard) for url, guard, _ in seen] == [(LINKS[0], LINKS[0]), (LINKS[1], LINKS[1])]
    assert runs._executor.submit(guarded_link.get).result() is None


def test_a_failing_entry_does_not_stop_the_others(runs, monkeypatch):
    attempts = [{"step": "plain", "url": LINKS[1], "outcome": "HTTP 403"}]
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({
        LINKS[0]: ("a", None), LINKS[1]: PostingNotFoundError(attempts), LINKS[2]: ("c", None)}))
    state = finished(runs, runs.start([RunEntry(url, f"T{n}") for n, url in enumerate(LINKS)]))
    assert state["status"] == "done" and state["total"] == state["done"] == 3
    assert [e["state"] for e in state["entries"]] == ["stored", "failed", "stored"]
    assert state["entries"][1]["attempts"] == attempts
    assert state["entries"][0] == {"url": LINKS[0], "title": "T0", "state": "stored",
                                   "posting_id": "a"}


@pytest.mark.parametrize(("error", "reason"), [
    (ValueError("the submission holds no posting text"), "the submission holds no posting text"),
    (RuntimeError("secret detail"), "RuntimeError")])
def test_other_errors_fail_the_entry_with_a_reason(runs, monkeypatch, error, reason):
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({LINKS[0]: error}))
    entry = finished(runs, runs.start([RunEntry(LINKS[0], "A")]))["entries"][0]
    assert entry["state"] == "failed" and entry["reason"] == reason


def test_an_entry_stored_meanwhile_is_a_duplicate_by_url(runs, monkeypatch):
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({LINKS[0]: ("alt", "url")}))
    entry = finished(runs, runs.start([RunEntry(LINKS[0], "A")]))["entries"][0]
    assert (entry["state"], entry["posting_id"], entry["duplicate_by"]) == (
        "duplicate", "alt", "url")


def test_a_text_duplicate_is_stored_when_forced(runs, monkeypatch):
    seen = []
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({LINKS[0]: ("alt", "text")}, seen))
    first = finished(runs, runs.start([RunEntry(LINKS[0], "A")]))["entries"][0]
    assert (first["state"], first["duplicate_by"]) == ("duplicate", "text")
    forced = finished(runs, runs.start([RunEntry(LINKS[0], "A", force=True)]))["entries"][0]
    assert (forced["state"], forced["posting_id"]) == ("stored", "neu")
    assert [allow for _, _, allow in seen] == [False, True]


def test_a_forced_link_duplicate_stays_a_duplicate(runs, monkeypatch):
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({LINKS[0]: ("alt", "url")}))
    entry = finished(runs, runs.start([RunEntry(LINKS[0], "A", force=True)]))["entries"][0]
    assert (entry["state"], entry["duplicate_by"]) == ("duplicate", "url")


def test_a_second_start_is_refused_while_the_first_computes(runs, monkeypatch):
    release = threading.Event()

    def held(intake, url, *, allow_text_duplicate=False):
        release.wait(30)
        return "a", None, None, []
    monkeypatch.setattr(runs_module, "add_from_url", held)
    first = runs.start([RunEntry(LINKS[0], "A")])
    time.sleep(0.05)
    assert runs.read(first)["entries"][0]["state"] == "running"
    with pytest.raises(AlertRunBusyError) as refused:
        runs.start([RunEntry(LINKS[1], "B")])
    assert refused.value.run_id == first
    release.set()
    assert finished(runs, first)["status"] == "done"


def test_a_crash_of_the_loop_fails_the_run(runs, monkeypatch):
    def crash(intake, entry):
        raise KeyError("boom")
    monkeypatch.setattr(runs_module, "add_entry", crash)
    state = finished(runs, runs.start([RunEntry(LINKS[0], "A")]))
    assert (state["status"], state["error"]) == ("failed", "KeyError")


def test_an_unknown_run_reads_none(runs):
    assert runs.read("nope") is None
