"""The background run of chosen alert-mail entries (`design.md` → Run)."""

import threading
import time

import httpx
import pytest
from conftest import FakeStructuredModel, SpacingClock, ToolScriptModel, write_json
from test_triage_graph import POLICY_PACK

import jobadvaisor.intake.alert_runs as runs_module
from jobadvaisor.intake import ladder as ladder_module
from jobadvaisor.intake.alert_runs import (
    AlertRunBusyError,
    AlertRuns,
    RunEntry,
    RunNotRunningError,
    add_entry,
)
from jobadvaisor.intake.fetch import FetchError, fetch_plain, guarded_link, host_throttle
from jobadvaisor.intake.postings import Intake, PostingNotFoundError
from jobadvaisor.tools.guard import ContentGuard

LINKS = [f"https://jobs.example.org/stelle/{n}" for n in (1, 2, 3)]


@pytest.fixture
def clock():
    return SpacingClock()


@pytest.fixture
def runs(tmp_path, clock):
    write_json(tmp_path / "policy-pack.json", POLICY_PACK)
    return AlertRuns(Intake(tmp_path, FakeStructuredModel(), ContentGuard(None, {})),
                     clock.throttle())


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


def test_a_closed_entry_is_reported_as_closed_and_counts_as_done(runs, monkeypatch):
    attempts = [{"step": "plain", "url": LINKS[0], "outcome": "closed page (redirect)"}]
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({
        LINKS[0]: PostingNotFoundError(attempts, closed=True), LINKS[1]: ("b", None)}))
    state = finished(runs, runs.start([RunEntry(LINKS[0], "A"), RunEntry(LINKS[1], "B")]))
    assert state["status"] == "done" and state["total"] == state["done"] == 2
    assert [e["state"] for e in state["entries"]] == ["closed", "stored"]
    assert state["entries"][0]["attempts"] == attempts


def test_an_expired_link_from_a_mail_is_closed_not_refused(tmp_path, closed_site):
    write_json(tmp_path / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(tmp_path / "policy-pack.json", {**POLICY_PACK, "closed_rules": closed_site.rules})
    intake = Intake(tmp_path, FakeStructuredModel(), ContentGuard(None, {}),
                    loop_model=ToolScriptModel(plan=[]))
    url = f"{closed_site.url}/expired/1"
    outcome = add_entry(intake, RunEntry(url, "A"))
    assert outcome["state"] == "closed"
    assert [a["outcome"] for a in outcome["attempts"]] == ["closed page (redirect)"]
    assert closed_site.hits == ["/expired/1"]


def ladder_answering(monkeypatch, plain: str, rendered: str):
    """Fake plain and rendered fetchers that fail with the given outcomes."""
    def fail(outcome):
        def fetch(url):
            raise FetchError(outcome)
        return fetch
    monkeypatch.setattr(ladder_module, "fetch_plain", fail(plain))
    monkeypatch.setattr(ladder_module, "fetch_rendered", fail(rendered))


@pytest.fixture
def idle_intake(tmp_path):
    """An intake whose loop model finds nothing."""
    write_json(tmp_path / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(tmp_path / "policy-pack.json", POLICY_PACK)
    return Intake(tmp_path, FakeStructuredModel(), ContentGuard(None, {}),
                  loop_model=ToolScriptModel(plan=[]))


def test_one_404_among_rate_limited_answers_is_failed_and_unclear_not_closed(
        idle_intake, monkeypatch):
    ladder_answering(monkeypatch, "HTTP 404", "HTTP 429")
    outcome = add_entry(idle_intake, RunEntry(LINKS[0], "A"))
    assert outcome["state"] == "failed" and outcome["unclear"] is True
    assert [a["outcome"] for a in outcome["attempts"]] == ["HTTP 404", "HTTP 429"]


def test_a_404_after_a_retried_429_is_failed_and_unclear_not_closed(idle_intake, monkeypatch):
    replies = iter([httpx.Response(429), httpx.Response(404)])
    http = httpx.Client(transport=httpx.MockTransport(lambda request: next(replies)))
    monkeypatch.setattr(ladder_module, "fetch_plain", lambda url: fetch_plain(url, http))
    monkeypatch.setattr(ladder_module, "fetch_rendered", lambda url: (_ for _ in ()).throw(
        FetchError("HTTP 404")))
    outcome = add_entry(idle_intake, RunEntry(LINKS[0], "A"))
    assert outcome["state"] == "failed" and outcome["unclear"] is True
    assert [a["outcome"] for a in outcome["attempts"]] == ["HTTP 429", "HTTP 404", "HTTP 404"]


def test_a_404_beside_a_page_without_posting_text_is_closed_and_not_unclear(
        idle_intake, monkeypatch):
    ladder_answering(monkeypatch, "HTTP 404", "no posting text")
    outcome = add_entry(idle_intake, RunEntry(LINKS[0], "A"))
    assert outcome["state"] == "closed" and "unclear" not in outcome


def test_a_failure_without_a_404_is_not_unclear(idle_intake, monkeypatch):
    ladder_answering(monkeypatch, "HTTP 429", "HTTP 429")
    outcome = add_entry(idle_intake, RunEntry(LINKS[0], "A"))
    assert outcome["state"] == "failed" and "unclear" not in outcome


def test_an_entry_read_from_its_page_is_stored_available(tmp_path, closed_site):
    """The run read the posting from its page, which is what a check calls available."""
    write_json(tmp_path / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(tmp_path / "policy-pack.json", {**POLICY_PACK, "closed_rules": closed_site.rules})
    fields = {"title": "Platform Engineer", "company": "Acme", "location_raw": "Remote"}
    intake = Intake(tmp_path, FakeStructuredModel(fields), ContentGuard(None, {}),
                    loop_model=ToolScriptModel(plan=[]))
    outcome = add_entry(intake, RunEntry(f"{closed_site.url}/open", "A"))
    assert outcome["state"] == "stored", outcome
    availability = intake.postings()[outcome["posting_id"]].availability
    assert (availability.state, availability.set_by) == ("available", "check")


def test_a_closed_entry_counts_as_done_while_the_run_goes_on(runs, monkeypatch):
    release = threading.Event()

    def add(intake, url, *, allow_text_duplicate=False):
        if url == LINKS[1]:
            release.wait(30)
            return "b", None, None, []
        raise PostingNotFoundError([], closed=True)
    monkeypatch.setattr(runs_module, "add_from_url", add)
    run_id = runs.start([RunEntry(LINKS[0], "A"), RunEntry(LINKS[1], "B")])
    for _ in range(300):
        if runs.read(run_id)["done"] == 1:
            break
        time.sleep(0.01)
    state = runs.read(run_id)
    assert [e["state"] for e in state["entries"]] == ["closed", "running"] and state["done"] == 1
    release.set()
    assert finished(runs, run_id)["done"] == 2


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


def test_a_link_in_two_tracking_forms_is_fetched_once_and_the_copy_names_the_first(
        runs, monkeypatch):
    seen = []
    first, second = LINKS[0], f"{LINKS[0]}?utm_source=mail"
    monkeypatch.setattr(runs_module, "add_from_url", fake_add(
        {first: ("a", None), LINKS[1]: ("b", None)}, seen))
    state = finished(runs, runs.start([RunEntry(first, "A"), RunEntry(second, "A again"),
                                       RunEntry(LINKS[1], "B")]))
    assert [url for url, _, _ in seen] == [first, LINKS[1]]
    one, two, three = state["entries"]
    assert (one["state"], one["posting_id"]) == (two["state"], two["posting_id"]) == ("stored", "a")
    assert "same_as" not in one and "same_as" not in three and two["same_as"] == 0
    assert two["url"] == second and two["title"] == "A again" and state["done"] == 3


def test_a_copy_takes_every_outcome_field_of_the_first(runs, monkeypatch):
    attempts = [{"step": "plain", "url": LINKS[0], "outcome": "HTTP 404"}]
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({
        LINKS[0]: PostingNotFoundError(attempts, closed=False)}))
    state = finished(runs, runs.start([RunEntry(LINKS[0], "A"), RunEntry(f"{LINKS[0]}/", "B")]))
    first, copy = state["entries"]
    assert copy["state"] == "failed" and copy["attempts"] == attempts and copy["same_as"] == 0
    assert copy | {"url": first["url"], "title": first["title"]} == first | {"same_as": 0}


# --- spacing (`fetch.host_throttle`) ---------------------------------------------------------


def test_two_entries_on_one_host_are_spaced_by_the_runs_throttle(tmp_path, closed_site, clock):
    write_json(tmp_path / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(tmp_path / "policy-pack.json", {**POLICY_PACK, "closed_rules": closed_site.rules})
    fields = {"title": "Platform Engineer", "company": "Acme", "location_raw": "Remote"}
    intake = Intake(tmp_path, FakeStructuredModel(fields), ContentGuard(None, {}),
                    loop_model=ToolScriptModel(plan=[]))
    runs = AlertRuns(intake, clock.throttle())
    state = finished(runs, runs.start([RunEntry(f"{closed_site.url}/open", "A"),
                                       RunEntry(f"{closed_site.url}/alt", "B")]))
    assert [e["state"] for e in state["entries"]][0] == "stored"
    assert closed_site.hits == ["/open", "/alt"] and clock.sleeps == [3]


def test_the_runs_throttle_is_set_around_each_entry_and_cleared_after(runs, monkeypatch):
    seen = []

    def add(intake, url, *, allow_text_duplicate=False):
        seen.append(host_throttle.get())
        return "p", None, None, []
    monkeypatch.setattr(runs_module, "add_from_url", add)
    finished(runs, runs.start([RunEntry(LINKS[0], "A"), RunEntry(LINKS[1], "B")]))
    assert seen == [runs._throttle, runs._throttle]
    assert runs._executor.submit(host_throttle.get).result() is None


def test_a_run_throttles_requests_by_three_seconds_unless_told_otherwise(tmp_path):
    runs = AlertRuns(Intake(tmp_path, FakeStructuredModel(), ContentGuard(None, {})))
    assert runs._throttle.interval == 3


# --- the end hook and `current` ---------------------------------------------------------------


class EndHook:
    """An `on_end` that records what it saw: the entries it was given and, read from inside the
    hook, the run's status and whether `current()` still names it."""

    def __init__(self, runs: AlertRuns, error: Exception | None = None):
        self.runs, self.error, self.calls = runs, error, []

    def __call__(self, entries):
        current = self.runs.current()
        self.calls.append({"entries": entries, "current": current,
                           "status": self.runs.read(current)["status"] if current else None,
                           "thread": threading.current_thread()})
        if self.error:
            raise self.error


def test_current_names_the_computing_run_and_nothing_after_it(runs, monkeypatch):
    release = threading.Event()

    def held(intake, url, *, allow_text_duplicate=False):
        release.wait(30)
        return "a", None, None, []
    monkeypatch.setattr(runs_module, "add_from_url", held)
    assert runs.current() is None
    run_id = runs.start([RunEntry(LINKS[0], "A")])
    assert runs.current() == run_id
    release.set()
    finished(runs, run_id)
    assert runs.current() is None


def test_the_end_hook_gets_the_final_entries_before_the_status_leaves_running(runs, monkeypatch):
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({
        LINKS[0]: ("a", None), LINKS[1]: PostingNotFoundError([], closed=True)}))
    hook = EndHook(runs)
    run_id = runs.start([RunEntry(LINKS[0], "A"), RunEntry(LINKS[1], "B")], hook)
    state = finished(runs, run_id)
    call, = hook.calls  # a single call; reading the run from inside it did not deadlock
    assert [e["state"] for e in call["entries"]] == ["stored", "closed"]
    assert call["current"] == run_id and call["status"] == "running"
    assert call["thread"] is not threading.current_thread()
    assert state["status"] == "done" and runs.current() is None


def test_the_end_hook_runs_after_a_crash_with_the_entries_as_they_stood(runs, monkeypatch):
    def crash_on_second(intake, entry):
        if entry.url == LINKS[1]:
            raise KeyError("boom")
        return {"state": "stored", "posting_id": "a"}
    monkeypatch.setattr(runs_module, "add_entry", crash_on_second)
    hook = EndHook(runs)
    state = finished(runs, runs.start([RunEntry(url, "T") for url in LINKS], hook))
    assert state["status"] == "failed"
    call, = hook.calls
    assert [e["state"] for e in call["entries"]] == ["stored", "running", "waiting"]
    assert call["status"] == "running"


def test_an_exception_in_the_end_hook_is_logged_by_type_and_frees_the_slot(
        runs, monkeypatch, caplog):
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({LINKS[0]: ("a", None)}))
    hook = EndHook(runs, ValueError("secret detail"))
    with caplog.at_level("WARNING"):
        state = finished(runs, runs.start([RunEntry(LINKS[0], "A")], hook))
    assert state["status"] == "done" and runs.current() is None
    assert "ValueError" in caplog.text and "secret detail" not in caplog.text
    assert finished(runs, runs.start([RunEntry(LINKS[0], "A")]))["status"] == "done"


def test_a_failed_submit_never_calls_the_end_hook(runs, monkeypatch):
    def broken(*args):
        raise RuntimeError("executor down")
    monkeypatch.setattr(runs._executor, "submit", broken)
    hook = EndHook(runs)
    with pytest.raises(RuntimeError):
        runs.start([RunEntry(LINKS[0], "A")], hook)
    assert hook.calls == [] and runs.current() is None


# --- cancel -----------------------------------------------------------------------------------


def holding_first(monkeypatch, urls_seen: list | None = None):
    """An `add_from_url` that stores every entry, but holds the first call until the returned
    `release` is set; `entered` is set once it is inside that call."""
    entered, release = threading.Event(), threading.Event()

    def add(intake, url, *, allow_text_duplicate=False):
        if urls_seen is not None:
            urls_seen.append(url)
        if not entered.is_set():
            entered.set()
            assert release.wait(30)
        return "p", None, None, []
    monkeypatch.setattr(runs_module, "add_from_url", add)
    return entered, release


def test_a_cancel_stops_after_the_current_entry_and_the_rest_stay_waiting(runs, monkeypatch):
    seen = []
    entered, release = holding_first(monkeypatch, seen)
    hook = EndHook(runs)
    run_id = runs.start([RunEntry(url, "T") for url in LINKS], hook)
    assert entered.wait(10)
    assert runs.read(run_id)["cancel_requested"] is False
    assert runs.cancel(run_id) == run_id
    assert runs.read(run_id)["cancel_requested"] is True
    release.set()
    state = finished(runs, run_id)
    assert (state["status"], state["done"], state["total"]) == ("cancelled", 1, 3)
    assert [e["state"] for e in state["entries"]] == ["stored", "waiting", "waiting"]
    assert seen == [LINKS[0]] and runs.current() is None
    call, = hook.calls  # the end hook runs after a cancel too, before the status left running
    assert [e["state"] for e in call["entries"]] == ["stored", "waiting", "waiting"]
    assert call["status"] == "running"


def test_a_cancel_during_the_last_entry_ends_done_with_the_request_noted(runs, monkeypatch):
    """No entry was left out, so the run is `done`, not `cancelled` (spec: Cancel during the
    last entry)."""
    entered, release = holding_first(monkeypatch)
    run_id = runs.start([RunEntry(LINKS[0], "A")])
    assert entered.wait(10)
    assert runs.cancel(run_id) == run_id
    release.set()
    state = finished(runs, run_id)
    assert (state["status"], state["done"], state["total"]) == ("done", 1, 1)
    assert state["cancel_requested"] is True
    assert [e["state"] for e in state["entries"]] == ["stored"]


def test_an_entry_whose_first_link_was_never_reached_stays_waiting(runs, monkeypatch):
    entered, release = holding_first(monkeypatch)
    run_id = runs.start([RunEntry(LINKS[0], "A"), RunEntry(LINKS[1], "B"),
                         RunEntry(f"{LINKS[1]}?utm_source=mail", "B again")])
    assert entered.wait(10)
    runs.cancel(run_id)
    release.set()
    entries = finished(runs, run_id)["entries"]
    assert [e["state"] for e in entries] == ["stored", "waiting", "waiting"]
    assert "same_as" not in entries[2]


def test_a_cancel_before_the_first_entry_runs_none(runs, monkeypatch):
    seen = []
    release = threading.Event()
    runs._executor.submit(release.wait, 30)  # the worker is busy until released
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({LINKS[0]: ("a", None)}, seen))
    run_id = runs.start([RunEntry(LINKS[0], "A")])
    runs.cancel(run_id)
    release.set()
    state = finished(runs, run_id)
    assert state["status"] == "cancelled" and state["done"] == 0 and seen == []
    with pytest.raises(RunNotRunningError):  # a cancelled run is ended
        runs.cancel(run_id)


def test_a_cancel_of_an_unknown_run_answers_none(runs):
    assert runs.cancel("nope") is None


@pytest.mark.parametrize("how", ["done", "failed"])
def test_a_cancel_of_an_ended_run_is_refused_and_changes_nothing(runs, monkeypatch, how):
    if how == "failed":
        monkeypatch.setattr(runs_module, "add_entry", lambda intake, entry: 1 / 0)
    else:
        monkeypatch.setattr(runs_module, "add_from_url", fake_add({LINKS[0]: ("a", None)}))
    state = finished(runs, runs.start([RunEntry(LINKS[0], "A")]))
    assert state["status"] == how
    with pytest.raises(RunNotRunningError):
        runs.cancel(state["run_id"])
    assert runs.read(state["run_id"]) == state
