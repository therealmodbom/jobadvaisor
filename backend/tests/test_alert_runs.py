"""The background run of chosen alert-mail entries (`design.md` → Run)."""

import threading
import time
from datetime import UTC, datetime

import httpx
import pytest
from conftest import FakeStructuredModel, SpacingClock, ToolScriptModel, write_json
from test_triage_graph import POLICY_PACK

import jobadvaisor.data.writer as writer_module
import jobadvaisor.intake.alert_runs as runs_module
from jobadvaisor.data.loader import DataRepositoryError, write_gate
from jobadvaisor.data.models import UnsettledLink, UnsettledLinks
from jobadvaisor.data.writer import (
    read_unsettled_links,
    update_mailbox_account,
    update_unsettled_links,
)
from jobadvaisor.intake import ladder as ladder_module
from jobadvaisor.intake.alert_runs import (
    AlertRunBusyError,
    AlertRuns,
    LinkInRunError,
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
        runs.start([RunEntry(LINKS[0], "A")], source="paste")
    monkeypatch.setattr(runs._executor, "submit", real)
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({LINKS[0]: ("p1", None)}))
    assert finished(runs, runs.start([RunEntry(LINKS[0], "A")], source="paste"))["status"] == "done"


def test_the_guard_holds_each_entry_link_and_is_cleared_after(runs, monkeypatch):
    seen = []
    monkeypatch.setattr(runs_module, "add_from_url", fake_add(
        {LINKS[0]: ("a", None), LINKS[1]: ("b", None)}, seen))
    finished(runs, runs.start([RunEntry(LINKS[0], "A"), RunEntry(LINKS[1], "B")], source="paste"))
    assert [(url, guard) for url, guard, _ in seen] == [(LINKS[0], LINKS[0]), (LINKS[1], LINKS[1])]
    assert runs._executor.submit(guarded_link.get).result() is None


def test_a_failing_entry_does_not_stop_the_others(runs, monkeypatch):
    attempts = [{"step": "plain", "url": LINKS[1], "outcome": "HTTP 403"}]
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({
        LINKS[0]: ("a", None), LINKS[1]: PostingNotFoundError(attempts), LINKS[2]: ("c", None)}))
    state = finished(runs, runs.start(
        [RunEntry(url, f"T{n}") for n, url in enumerate(LINKS)], source="paste"))
    assert state["status"] == "done" and state["total"] == state["done"] == 3
    assert [e["state"] for e in state["entries"]] == ["stored", "failed", "stored"]
    assert state["entries"][1]["attempts"] == attempts
    assert state["entries"][0] == {"url": LINKS[0], "title": "T0", "state": "stored",
                                   "posting_id": "a"}


def test_a_closed_entry_is_reported_as_closed_and_counts_as_done(runs, monkeypatch):
    attempts = [{"step": "plain", "url": LINKS[0], "outcome": "closed page (redirect)"}]
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({
        LINKS[0]: PostingNotFoundError(attempts, closed=True), LINKS[1]: ("b", None)}))
    state = finished(runs, runs.start([RunEntry(LINKS[0], "A"), RunEntry(LINKS[1], "B")],
                                      source="paste"))
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


def test_a_429_before_a_page_without_posting_text_and_a_rendered_404_is_unclear_not_closed(
        idle_intake, monkeypatch):
    replies = iter([httpx.Response(429), httpx.Response(200, text="<p>nothing</p>")])
    http = httpx.Client(transport=httpx.MockTransport(lambda request: next(replies)))
    monkeypatch.setattr(ladder_module, "fetch_plain", lambda url: fetch_plain(url, http))
    monkeypatch.setattr(ladder_module, "fetch_rendered", lambda url: (_ for _ in ()).throw(
        FetchError("HTTP 404")))
    outcome = add_entry(idle_intake, RunEntry(LINKS[0], "A"))
    assert outcome["state"] == "failed" and outcome["unclear"] is True
    assert [a["outcome"] for a in outcome["attempts"]] == [
        "HTTP 429", "no posting text", "HTTP 404"]


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
    run_id = runs.start([RunEntry(LINKS[0], "A"), RunEntry(LINKS[1], "B")], source="paste")
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
    entry = finished(runs, runs.start([RunEntry(LINKS[0], "A")], source="paste"))["entries"][0]
    assert entry["state"] == "failed" and entry["reason"] == reason


def test_an_entry_stored_meanwhile_is_a_duplicate_by_url(runs, monkeypatch):
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({LINKS[0]: ("alt", "url")}))
    entry = finished(runs, runs.start([RunEntry(LINKS[0], "A")], source="paste"))["entries"][0]
    assert (entry["state"], entry["posting_id"], entry["duplicate_by"]) == (
        "duplicate", "alt", "url")


def test_a_text_duplicate_is_stored_when_forced(runs, monkeypatch):
    seen = []
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({LINKS[0]: ("alt", "text")}, seen))
    first = finished(runs, runs.start([RunEntry(LINKS[0], "A")], source="paste"))["entries"][0]
    assert (first["state"], first["duplicate_by"]) == ("duplicate", "text")
    forced = finished(runs, runs.start([RunEntry(LINKS[0], "A", force=True)],
                                       source="paste"))["entries"][0]
    assert (forced["state"], forced["posting_id"]) == ("stored", "neu")
    assert [allow for _, _, allow in seen] == [False, True]


def test_a_forced_link_duplicate_stays_a_duplicate(runs, monkeypatch):
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({LINKS[0]: ("alt", "url")}))
    entry = finished(runs, runs.start([RunEntry(LINKS[0], "A", force=True)],
                                      source="paste"))["entries"][0]
    assert (entry["state"], entry["duplicate_by"]) == ("duplicate", "url")


def test_a_second_start_is_refused_while_the_first_computes(runs, monkeypatch):
    release = threading.Event()

    def held(intake, url, *, allow_text_duplicate=False):
        release.wait(30)
        return "a", None, None, []
    monkeypatch.setattr(runs_module, "add_from_url", held)
    first = runs.start([RunEntry(LINKS[0], "A")], source="paste")
    time.sleep(0.05)
    assert runs.read(first)["entries"][0]["state"] == "running"
    with pytest.raises(AlertRunBusyError) as refused:
        runs.start([RunEntry(LINKS[1], "B")], source="paste")
    assert refused.value.run_id == first
    release.set()
    assert finished(runs, first)["status"] == "done"


def test_a_crash_of_the_loop_fails_the_run(runs, monkeypatch):
    def crash(intake, entry):
        raise KeyError("boom")
    monkeypatch.setattr(runs_module, "add_entry", crash)
    state = finished(runs, runs.start([RunEntry(LINKS[0], "A")], source="paste"))
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
                                       RunEntry(LINKS[1], "B")], source="paste"))
    assert [url for url, _, _ in seen] == [first, LINKS[1]]
    one, two, three = state["entries"]
    assert (one["state"], one["posting_id"]) == (two["state"], two["posting_id"]) == ("stored", "a")
    assert "same_as" not in one and "same_as" not in three and two["same_as"] == 0
    assert two["url"] == second and two["title"] == "A again" and state["done"] == 3


def test_a_copy_takes_every_outcome_field_of_the_first(runs, monkeypatch):
    attempts = [{"step": "plain", "url": LINKS[0], "outcome": "HTTP 404"}]
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({
        LINKS[0]: PostingNotFoundError(attempts, closed=False)}))
    state = finished(runs, runs.start([RunEntry(LINKS[0], "A"), RunEntry(f"{LINKS[0]}/", "B")],
                                      source="paste"))
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
                                       RunEntry(f"{closed_site.url}/alt", "B")], source="paste"))
    assert [e["state"] for e in state["entries"]][0] == "stored"
    assert closed_site.hits == ["/open", "/alt"] and clock.sleeps == [3]


def test_the_runs_throttle_is_set_around_each_entry_and_cleared_after(runs, monkeypatch):
    seen = []

    def add(intake, url, *, allow_text_duplicate=False):
        seen.append(host_throttle.get())
        return "p", None, None, []
    monkeypatch.setattr(runs_module, "add_from_url", add)
    finished(runs, runs.start([RunEntry(LINKS[0], "A"), RunEntry(LINKS[1], "B")], source="paste"))
    assert seen == [runs._throttle, runs._throttle]
    assert runs._executor.submit(host_throttle.get).result() is None


def test_a_run_throttles_requests_by_three_seconds_unless_told_otherwise(tmp_path):
    runs = AlertRuns(Intake(tmp_path, FakeStructuredModel(), ContentGuard(None, {})))
    assert runs._throttle.interval == 3


# --- `current` ---------------------------------------------------------------------------------


def test_current_names_the_computing_run_and_nothing_after_it(runs, monkeypatch):
    release = threading.Event()

    def held(intake, url, *, allow_text_duplicate=False):
        release.wait(30)
        return "a", None, None, []
    monkeypatch.setattr(runs_module, "add_from_url", held)
    assert runs.current() is None
    run_id = runs.start([RunEntry(LINKS[0], "A")], source="paste")
    assert runs.current() == run_id
    release.set()
    finished(runs, run_id)
    assert runs.current() is None


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
    run_id = runs.start([RunEntry(url, "T") for url in LINKS], source="paste")
    assert entered.wait(10)
    assert runs.read(run_id)["cancel_requested"] is False
    assert runs.cancel(run_id) == run_id
    assert runs.read(run_id)["cancel_requested"] is True
    release.set()
    state = finished(runs, run_id)
    assert (state["status"], state["done"], state["total"]) == ("cancelled", 1, 3)
    assert [e["state"] for e in state["entries"]] == ["stored", "waiting", "waiting"]
    assert seen == [LINKS[0]] and runs.current() is None


def test_a_cancel_during_the_last_entry_ends_done_with_the_request_noted(runs, monkeypatch):
    """No entry was left out, so the run is `done`, not `cancelled` (spec: Cancel during the
    last entry)."""
    entered, release = holding_first(monkeypatch)
    run_id = runs.start([RunEntry(LINKS[0], "A")], source="paste")
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
                         RunEntry(f"{LINKS[1]}?utm_source=mail", "B again")], source="paste")
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
    run_id = runs.start([RunEntry(LINKS[0], "A")], source="paste")
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
    state = finished(runs, runs.start([RunEntry(LINKS[0], "A")], source="paste"))
    assert state["status"] == how
    with pytest.raises(RunNotRunningError):
        runs.cancel(state["run_id"])
    assert runs.read(state["run_id"]) == state


# --- the list of unsettled links: start ---------------------------------------------------------

EARLIER = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)


def rows(root) -> dict[str, UnsettledLink]:
    """The rows of `unsettled-links.json` under `root` by URL."""
    return {row.url: row for row in read_unsettled_links(root).links}


def listed(root, *links: UnsettledLink) -> None:
    """Write `links` as the list file under `root`."""
    update_unsettled_links(root, lambda current: UnsettledLinks(schema_version="1",
                                                                links=list(links)))


def row(url: str, **changes) -> UnsettledLink:
    """A row of `url` that one earlier run left unread."""
    return UnsettledLink.model_validate({
        "url": url, "title": "Old title", "source": "mailbox", "state": "unread", "tries": 1,
        "added_at": EARLIER, "last_tried_at": EARLIER,
        "attempts": [{"step": "plain", "outcome": "HTTP 429"}], "reason": None} | changes)


def test_every_link_is_waiting_in_the_list_before_the_first_entry_runs(runs, tmp_path,
                                                                       monkeypatch):
    """posting-intake → Scenario: Waiting during the run: before each entry, the links not yet
    ended are in the list as waiting, and the stored ones have left it."""
    links = [f"https://jobs.example.org/stelle/{n}" for n in range(5)]
    seen = []

    def add(intake, url, *, allow_text_duplicate=False):
        seen.append({key: value.state for key, value in rows(tmp_path).items()})
        if len(seen) == 1:
            seen.append(read_unsettled_links(tmp_path).links[0])
        return "p", None, None, []
    monkeypatch.setattr(runs_module, "add_from_url", add)
    finished(runs, runs.start([RunEntry(url, f"T{n}") for n, url in enumerate(links)],
                              source="mailbox"))
    first, new, *later = seen
    assert first == dict.fromkeys(links, "waiting")
    assert later[1] == dict.fromkeys(links[2:], "waiting")  # two of five ended
    assert (new.title, new.source, new.tries, new.last_tried_at, new.attempts) == (
        "T0", "mailbox", 0, None, [])
    assert new.added_at.tzinfo is not None


def test_two_entries_with_one_link_give_one_row_with_the_first_title(runs, tmp_path,
                                                                     monkeypatch):
    entered, release = holding_first(monkeypatch)
    run_id = runs.start([RunEntry(LINKS[0], "A"), RunEntry(f"{LINKS[0]}?utm_source=mail", "B")],
                        source="paste")
    assert entered.wait(10)
    assert [(r.url, r.title) for r in read_unsettled_links(tmp_path).links] == [(LINKS[0], "A")]
    release.set()
    finished(runs, run_id)


@pytest.mark.parametrize("broken", ["invalid file", "write fails"])
def test_a_list_that_cannot_be_written_starts_no_run(runs, tmp_path, monkeypatch, broken):
    """posting-intake → Scenario: List cannot be written."""
    seen = []
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({LINKS[0]: ("a", None)}, seen))
    if broken == "invalid file":
        (tmp_path / "unsettled-links.json").write_text("{not json")
    else:
        def refuse(path, entity):
            raise PermissionError("read-only")
        monkeypatch.setattr(writer_module, "_replace", refuse)
    with pytest.raises(DataRepositoryError, match="unsettled-links.json"):
        runs.start([RunEntry(LINKS[0], "A")], source="paste")
    assert runs.current() is None and runs._state == {}
    assert runs._executor.submit(lambda: None).result() is None and seen == []
    monkeypatch.undo()
    (tmp_path / "unsettled-links.json").unlink(missing_ok=True)
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({LINKS[0]: ("a", None)}))
    assert finished(runs, runs.start([RunEntry(LINKS[0], "A")], source="paste"))[
        "status"] == "done"


def test_a_link_left_waiting_by_a_lost_run_turns_not_reached_at_the_next_start(
        runs, tmp_path, monkeypatch):
    """posting-intake → Scenario: Next run after a restart."""
    listed(tmp_path, row(LINKS[2], state="waiting"))
    entered, release = holding_first(monkeypatch)
    run_id = runs.start([RunEntry(LINKS[0], "A"), RunEntry(LINKS[1], "B")], source="paste")
    assert entered.wait(10)
    assert {url: r.state for url, r in rows(tmp_path).items()} == {
        LINKS[2]: "not_reached", LINKS[0]: "waiting", LINKS[1]: "waiting"}
    release.set()
    finished(runs, run_id)


def test_a_listed_link_taken_again_waits_with_its_row_kept(runs, tmp_path, monkeypatch):
    """A store-anyway run from a mailbox row goes through the paste route and keeps the row's
    source, first date, tries and last try (design D1 → A link taken again)."""
    listed(tmp_path, row(LINKS[0], reason="no posting text", attempts=[]))
    entered, release = holding_first(monkeypatch)
    run_id = runs.start([RunEntry(f"{LINKS[0]}?utm_source=mail", "New title", force=True)],
                        source="paste")
    assert entered.wait(10)
    taken, = read_unsettled_links(tmp_path).links
    assert taken == row(LINKS[0], reason="no posting text", attempts=[], state="waiting",
                        title="New title")
    release.set()
    finished(runs, run_id)


def test_a_repeated_row_in_a_hand_edited_file_keeps_the_first(runs, tmp_path, monkeypatch):
    listed(tmp_path, row(LINKS[0], title="First"), row(f"{LINKS[0]}/", title="Second"))
    entered, release = holding_first(monkeypatch)
    run_id = runs.start([RunEntry(LINKS[1], "B")], source="paste")
    assert entered.wait(10)
    assert [(r.url, r.title) for r in read_unsettled_links(tmp_path).links] == [
        (LINKS[0], "First"), (LINKS[1], "B")]
    release.set()
    finished(runs, run_id)


# --- the list of unsettled links: each ended entry ----------------------------------------------

RATE_LIMITED = [{"step": "plain", "url": LINKS[0], "outcome": "HTTP 429"},
                {"step": "rendered", "url": LINKS[0], "outcome": "HTTP 429"}]


def ending(monkeypatch, outcomes: dict):
    """Let `add_entry` answer `outcomes[url]` for each entry."""
    monkeypatch.setattr(runs_module, "add_entry", lambda intake, entry: dict(outcomes[entry.url]))


def test_a_failed_link_stays_as_not_read_with_its_title_and_attempts(runs, tmp_path, monkeypatch):
    """posting-intake → Scenarios: Failed link kept, First try."""
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({
        LINKS[0]: PostingNotFoundError(RATE_LIMITED), LINKS[1]: ("b", None)}))
    finished(runs, runs.start([RunEntry(LINKS[0], "Platform Engineer"), RunEntry(LINKS[1], "B")],
                              source="mailbox"))
    failed, = read_unsettled_links(tmp_path).links
    assert (failed.url, failed.title, failed.state, failed.tries, failed.reason) == (
        LINKS[0], "Platform Engineer", "unread", 1, None)
    assert [a.model_dump() for a in failed.attempts] == [
        {"step": "plain", "outcome": "HTTP 429"}, {"step": "rendered", "outcome": "HTTP 429"}]
    assert failed.added_at <= failed.last_tried_at


@pytest.mark.parametrize("settled", [{"state": "stored", "posting_id": "a"},
                                     {"state": "duplicate", "posting_id": "a",
                                      "duplicate_by": "url"},
                                     {"state": "closed", "attempts": []}])
def test_a_link_that_a_later_run_settles_leaves_the_list(runs, tmp_path, monkeypatch, settled):
    """posting-intake → Scenario: Stored link leaves the list."""
    listed(tmp_path, row(LINKS[0]), row(LINKS[1]))
    ending(monkeypatch, {LINKS[0]: settled})
    finished(runs, runs.start([RunEntry(LINKS[0], "A")], source="paste"))
    assert list(rows(tmp_path)) == [LINKS[1]]


def test_a_link_tried_again_counts_a_second_try_and_keeps_its_first_date(
        runs, tmp_path, monkeypatch):
    """posting-intake → Scenario: Tried again."""
    listed(tmp_path, row(LINKS[0]))
    disputed = [{"step": "plain", "url": LINKS[0], "outcome": "HTTP 404"}]
    ending(monkeypatch, {LINKS[0]: {"state": "failed", "attempts": disputed, "unclear": True}})
    finished(runs, runs.start([RunEntry(LINKS[0], "A")], source="paste"))
    again = rows(tmp_path)[LINKS[0]]
    assert (again.state, again.tries, again.added_at, again.source) == (
        "unclear", 2, EARLIER, "mailbox")
    assert again.last_tried_at > EARLIER
    assert [a.outcome for a in again.attempts] == ["HTTP 404"]


def test_the_same_link_from_two_runs_is_one_row_with_two_tries(runs, tmp_path, monkeypatch):
    """data-repository → Scenario: Same link from two mails."""
    ending(monkeypatch, {LINKS[0]: {"state": "failed", "attempts": []},
                         f"{LINKS[0]}?utm_source=mail": {"state": "failed", "attempts": []}})
    finished(runs, runs.start([RunEntry(LINKS[0], "A")], source="mailbox"))
    finished(runs, runs.start([RunEntry(f"{LINKS[0]}?utm_source=mail", "A")], source="mailbox"))
    only, = read_unsettled_links(tmp_path).links
    assert (only.url, only.tries) == (LINKS[0], 2)


def test_a_browser_failure_on_a_redirect_keeps_neither_the_hop_nor_the_message(
        runs, tmp_path, monkeypatch):
    """data-repository → Scenario: Browser failure on a redirect."""
    hop = "https://hop.example.net/redirect?token=SECRET-7"
    attempts = [{"step": "plain", "url": hop, "outcome": "connection failed: ConnectTimeout"},
                {"step": "rendered", "url": hop,
                 "outcome": f"browser failed: net::ERR_ABORTED at {hop}"},
                {"step": "search", "url": hop, "outcome": f"fetch failed: {hop} refused"}]
    ending(monkeypatch, {LINKS[0]: {"state": "failed", "attempts": attempts}})
    finished(runs, runs.start([RunEntry(LINKS[0], "A")], source="mailbox"))
    assert [(a.step, a.outcome) for a in rows(tmp_path)[LINKS[0]].attempts] == [
        ("plain", "connection failed"), ("rendered", "browser failed"),
        ("search", "fetch failed")]
    text = (tmp_path / "unsettled-links.json").read_text()
    assert "hop.example.net" not in text and "SECRET" not in text and "ERR_ABORTED" not in text


def test_a_failure_with_only_a_reason_is_not_read_with_that_reason(runs, tmp_path, monkeypatch):
    ending(monkeypatch, {LINKS[0]: {"state": "failed", "reason": "LLMError"}})
    finished(runs, runs.start([RunEntry(LINKS[0], "A")], source="paste"))
    failed = rows(tmp_path)[LINKS[0]]
    assert (failed.state, failed.reason, failed.attempts, failed.source) == (
        "unread", "LLMError", [], "paste")


def test_an_overlong_title_and_reason_are_cut(runs, tmp_path, monkeypatch):
    ending(monkeypatch, {LINKS[0]: {"state": "failed", "reason": "r" * 500}})
    state = finished(runs, runs.start([RunEntry(LINKS[0], "t" * 500)], source="paste"))
    assert state["status"] == "done"
    failed = rows(tmp_path)[LINKS[0]]
    assert (failed.title, failed.reason) == ("t" * 300, "r" * 200)


def test_a_repeat_of_a_link_in_one_run_counts_one_try(runs, tmp_path, monkeypatch):
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({
        LINKS[0]: PostingNotFoundError(RATE_LIMITED)}))
    finished(runs, runs.start([RunEntry(LINKS[0], "A"), RunEntry(f"{LINKS[0]}/", "A again")],
                              source="paste"))
    assert rows(tmp_path)[LINKS[0]].tries == 1 and len(rows(tmp_path)) == 1


def test_a_failed_link_whose_row_was_removed_meanwhile_is_listed_again(
        runs, tmp_path, monkeypatch):
    """A hand edit or a pull removed the row while the entry ran."""
    def add(intake, entry):
        listed(tmp_path)  # an empty list
        return {"state": "failed", "attempts": []}
    monkeypatch.setattr(runs_module, "add_entry", add)
    finished(runs, runs.start([RunEntry(LINKS[0], "A")], source="mailbox"))
    again = rows(tmp_path)[LINKS[0]]
    assert (again.state, again.tries, again.source, again.title) == ("unread", 1, "mailbox", "A")


def failing_write(monkeypatch, failing_calls: set[int]) -> list:
    """Make the calls numbered in `failing_calls` (1 is the start's write) of
    `update_unsettled_links` raise `OSError`; returns the list of call numbers seen."""
    real, calls = runs_module.update_unsettled_links, []

    def update(root, change):
        calls.append(len(calls) + 1)
        if calls[-1] in failing_calls:
            raise OSError("disk full: /secret/path")
        return real(root, change)
    monkeypatch.setattr(runs_module, "update_unsettled_links", update)
    return calls


def test_a_failing_write_after_an_entry_is_logged_and_the_run_goes_on(
        runs, tmp_path, monkeypatch, caplog):
    ending(monkeypatch, {LINKS[0]: {"state": "failed", "attempts": []},
                         LINKS[1]: {"state": "failed", "reason": "x"}})
    failing_write(monkeypatch, {2})
    with caplog.at_level("WARNING"):
        state = finished(runs, runs.start([RunEntry(LINKS[0], "A"), RunEntry(LINKS[1], "B")],
                                          source="paste"))
    assert state["status"] == "done" and [e["state"] for e in state["entries"]] == [
        "failed", "failed"]
    assert rows(tmp_path)[LINKS[1]].state == "unread"
    assert "OSError" in caplog.text and "/secret/path" not in caplog.text


def test_the_row_is_written_before_the_entry_shows_as_ended(runs, tmp_path, monkeypatch):
    """A client that reads the list once `done` grew sees the entry's row."""
    seen = []
    real = runs_module.update_unsettled_links

    def update(root, change):
        seen.append(runs.read(runs.current())["done"])
        return real(root, change)
    ending(monkeypatch, {LINKS[0]: {"state": "failed", "attempts": []}})
    monkeypatch.setattr(runs_module, "update_unsettled_links", update)
    finished(runs, runs.start([RunEntry(LINKS[0], "A")], source="paste"))
    assert seen[:2] == [0, 0]


# --- the list of unsettled links: the end of the run --------------------------------------------


def test_the_links_a_cancelled_run_did_not_reach_are_not_reached(runs, tmp_path, monkeypatch):
    """posting-intake → Scenario: Cancelled run."""
    links = [f"https://jobs.example.org/stelle/{n}" for n in range(4)]
    entered, release = holding_first(monkeypatch)
    run_id = runs.start([RunEntry(url, "T") for url in links], source="paste")
    assert entered.wait(10)
    runs.cancel(run_id)
    release.set()
    assert finished(runs, run_id)["status"] == "cancelled"
    assert {url: r.state for url, r in rows(tmp_path).items()} == dict.fromkeys(
        links[1:], "not_reached")


def test_a_link_not_reached_again_keeps_its_last_try(runs, tmp_path, monkeypatch):
    """posting-intake → Scenario: Not reached again."""
    earlier = row(LINKS[1], reason="no posting text")
    listed(tmp_path, earlier)
    entered, release = holding_first(monkeypatch)
    run_id = runs.start([RunEntry(LINKS[0], "A"), RunEntry(LINKS[1], "New")], source="paste")
    assert entered.wait(10)
    runs.cancel(run_id)
    release.set()
    finished(runs, run_id)
    assert rows(tmp_path)[LINKS[1]] == earlier.model_copy(update={"state": "not_reached",
                                                                  "title": "New"})


def test_a_crash_leaves_the_links_not_ended_not_reached(runs, tmp_path, monkeypatch):
    def crash_on_second(intake, entry):
        if entry.url == LINKS[1]:
            raise KeyError("boom")
        return {"state": "failed", "attempts": []}
    monkeypatch.setattr(runs_module, "add_entry", crash_on_second)
    state = finished(runs, runs.start([RunEntry(url, "T") for url in LINKS], source="paste"))
    assert state["status"] == "failed"
    assert {url: r.state for url, r in rows(tmp_path).items()} == {
        LINKS[0]: "unread", LINKS[1]: "not_reached", LINKS[2]: "not_reached"}


def test_an_outcome_whose_write_failed_lands_at_the_end(runs, tmp_path, monkeypatch):
    ending(monkeypatch, {LINKS[0]: {"state": "failed", "attempts": RATE_LIMITED},
                         LINKS[1]: {"state": "stored", "posting_id": "b"}})
    failing_write(monkeypatch, {2, 3})  # both per-entry writes
    finished(runs, runs.start([RunEntry(LINKS[0], "A"), RunEntry(LINKS[1], "B")],
                              source="mailbox"))
    landed, = read_unsettled_links(tmp_path).links
    assert (landed.url, landed.state, landed.tries) == (LINKS[0], "unread", 1)
    assert [a.outcome for a in landed.attempts] == ["HTTP 429", "HTTP 429"]


def test_a_link_whose_write_failed_twice_stays_waiting_and_frees_the_slot(
        runs, tmp_path, monkeypatch, caplog):
    ending(monkeypatch, {LINKS[0]: {"state": "failed", "attempts": []}})
    failing_write(monkeypatch, {2, 3})  # the entry's write and the end's
    with caplog.at_level("WARNING"):
        state = finished(runs, runs.start([RunEntry(LINKS[0], "A")], source="paste"))
    assert state["status"] == "done" and runs.current() is None
    assert rows(tmp_path)[LINKS[0]].state == "waiting" and caplog.text.count("OSError") == 2


def test_the_end_touches_no_row_of_another_link(runs, tmp_path, monkeypatch):
    """A row another run left waiting (here written by a pull while this run computes) is no
    link of this run, so its end leaves it alone."""
    stray = row(LINKS[2], state="waiting")

    def add(intake, entry):
        update_unsettled_links(tmp_path, lambda current: current.model_copy(
            update={"links": [*current.links, stray]}))
        return {"state": "stored", "posting_id": "a"}
    monkeypatch.setattr(runs_module, "add_entry", add)
    finished(runs, runs.start([RunEntry(LINKS[0], "A")], source="paste"))
    assert rows(tmp_path) == {LINKS[2]: stray}


def test_the_end_is_written_before_the_slot_is_freed_so_the_next_run_keeps_its_rows(
        runs, tmp_path, monkeypatch):
    real, computing = runs_module.update_unsettled_links, []

    def update(root, change):
        computing.append(runs.current())
        return real(root, change)
    monkeypatch.setattr(runs_module, "update_unsettled_links", update)
    ending(monkeypatch, {LINKS[0]: {"state": "failed", "attempts": []}})
    first = runs.start([RunEntry(LINKS[0], "A")], source="paste")
    finished(runs, first)
    assert computing == [first, first, first]  # start, entry, end: all while it computes
    monkeypatch.undo()
    entered, release = holding_first(monkeypatch)
    second = runs.start([RunEntry(LINKS[0], "A")], source="paste")
    assert entered.wait(10)
    assert rows(tmp_path)[LINKS[0]].state == "waiting"
    release.set()
    finished(runs, second)


# --- reading and removing -----------------------------------------------------------------------


def shown(runs: AlertRuns) -> dict[str, tuple[str, bool]]:
    """`unsettled()`'s rows as URL → (state, in_run)."""
    return {link["url"]: (link["state"], link["in_run"]) for link in runs.unsettled()["links"]}


def test_after_a_restart_waiting_rows_read_as_not_reached(tmp_path):
    """posting-intake → Scenario: Restart during a run (a fresh `AlertRuns` over its file)."""
    write_json(tmp_path / "policy-pack.json", POLICY_PACK)
    listed(tmp_path, row(LINKS[0], state="waiting"), row(LINKS[1]))
    fresh = AlertRuns(Intake(tmp_path, FakeStructuredModel(), ContentGuard(None, {})))
    answer = fresh.unsettled()
    assert answer["run_id"] is None
    assert shown(fresh) == {LINKS[0]: ("not_reached", False), LINKS[1]: ("unread", False)}
    assert set(answer["links"][0]) == {"url", "title", "source", "state", "tries", "added_at",
                                       "last_tried_at", "attempts", "reason", "in_run"}
    assert answer["links"][0]["attempts"] == [{"step": "plain", "outcome": "HTTP 429"}]


def test_the_rows_of_the_computing_run_are_in_run_and_the_answer_names_it(
        runs, tmp_path, monkeypatch):
    listed(tmp_path, row(LINKS[2]))
    entered, release = holding_first(monkeypatch)
    run_id = runs.start([RunEntry(LINKS[0], "A"), RunEntry(LINKS[1], "B")], source="paste")
    assert entered.wait(10)
    assert runs.unsettled()["run_id"] == run_id
    assert shown(runs) == {LINKS[0]: ("waiting", True), LINKS[1]: ("waiting", True),
                           LINKS[2]: ("unread", False)}
    release.set()
    finished(runs, run_id)
    assert runs.unsettled()["run_id"] is None and shown(runs) == {LINKS[2]: ("unread", False)}


def test_a_row_a_lost_run_left_waiting_is_not_in_run_before_the_start_write(
        runs, tmp_path, monkeypatch):
    """posting-intake → Requirement: Links a run did not reach („while the computing run is not
    the one that took it“): between claiming the slot and the start write, a row a lost run left
    `waiting` reads `not_reached` and can be removed, while a link of the new run is held."""
    listed(tmp_path, row(LINKS[2], state="waiting"), row(LINKS[1], state="waiting"))
    write = runs_module.update_unsettled_links
    seen = {}

    def first_write(root, change):
        if not seen:  # the start write: the slot is claimed, the rows are not written yet
            seen["shown"] = shown(runs)
            with pytest.raises(LinkInRunError):
                runs.remove(LINKS[1])
            runs.remove(LINKS[2])
        return write(root, change)
    monkeypatch.setattr(runs_module, "update_unsettled_links", first_write)
    monkeypatch.setattr(runs_module, "add_from_url", fake_add({LINKS[0]: ("a", None),
                                                               LINKS[1]: ("b", None)}))
    finished(runs, runs.start([RunEntry(LINKS[0], "A"), RunEntry(LINKS[1], "B")],
                              source="paste"))
    assert seen["shown"] == {LINKS[2]: ("not_reached", False), LINKS[1]: ("waiting", True)}
    assert shown(runs) == {}


def test_the_rows_are_ordered_by_their_latest_activity_newest_first(runs, tmp_path):
    listed(tmp_path, row(LINKS[0], last_tried_at=datetime(2026, 11, 21, tzinfo=UTC)),
           row(LINKS[1], last_tried_at=None, added_at=datetime(2026, 11, 22, tzinfo=UTC)),
           row(LINKS[2], last_tried_at=datetime(2026, 11, 23, tzinfo=UTC)))
    assert list(shown(runs)) == [LINKS[2], LINKS[1], LINKS[0]]


def test_a_removed_link_is_gone_and_nothing_else_changes(runs, tmp_path):
    """posting-intake → Scenario: Remove a link (also for a fresh `AlertRuns`, as after a
    restart, and for a link in another tracking form)."""
    update_mailbox_account(tmp_path, "imap.example.org", 993, "name@example.org")
    write_json(tmp_path / "postings" / "p1.json", {"schema_version": "1", "title": "T"})
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")
              if path.name != "unsettled-links.json"}
    listed(tmp_path, row(LINKS[0]), row(LINKS[1]))
    runs.remove(f"{LINKS[0]}?utm_source=mail")
    assert list(shown(runs)) == [LINKS[1]]
    fresh = AlertRuns(Intake(tmp_path, FakeStructuredModel(), ContentGuard(None, {})))
    assert list(shown(fresh)) == [LINKS[1]]
    assert {path: path.read_bytes() for path in tmp_path.rglob("*.json")
            if path.name != "unsettled-links.json"} == before


def test_a_link_the_computing_run_has_not_ended_cannot_be_removed(runs, tmp_path, monkeypatch):
    """posting-intake → Scenario: Remove during the run; a row the run does not hold can go."""
    listed(tmp_path, row(LINKS[2]))
    entered, release = holding_first(monkeypatch)
    run_id = runs.start([RunEntry(LINKS[0], "A"), RunEntry(LINKS[1], "B")], source="paste")
    assert entered.wait(10)
    with pytest.raises(LinkInRunError):
        runs.remove(LINKS[1])
    runs.remove(LINKS[2])
    assert set(shown(runs)) == {LINKS[0], LINKS[1]}
    release.set()
    finished(runs, run_id)


def test_an_unknown_link_is_not_found(runs, tmp_path):
    """posting-intake → Scenario: Unknown link."""
    listed(tmp_path, row(LINKS[0]))
    with pytest.raises(KeyError):
        runs.remove(LINKS[1])
    assert list(shown(runs)) == [LINKS[0]]


def test_the_in_run_refusal_is_decided_inside_the_write(runs, tmp_path, monkeypatch):
    """`remove` asks for the computing run while it holds the write gate, so a run that starts
    meanwhile cannot list the link as waiting between the check and the removal."""
    listed(tmp_path, row(LINKS[0], state="waiting"))
    held = []

    def holding():
        held.append(write_gate._is_owned())
        return "run-9", frozenset({runs_module.normalize_url(LINKS[0])})
    monkeypatch.setattr(runs, "_holding", holding)
    with pytest.raises(LinkInRunError):
        runs.remove(LINKS[0])
    assert held == [True]
