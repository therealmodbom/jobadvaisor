"""The availability check (`design.md` → D5): what one posting's links say, which postings a check
covers, and the background run with its report. Pages are synthetic, behind an httpx mock
transport; the spacing runs on an injected clock and sleep."""

import threading
import time
from datetime import UTC, datetime

import httpx
import pytest
from conftest import AT, write_json
from test_triage_graph import POLICY_PACK, add_posting

import jobadvaisor.availability as availability_module
from jobadvaisor.availability import (
    HOST_SPACING_SECONDS,
    AvailabilityChecks,
    CheckBusyError,
    CheckStateError,
    check_batch,
    check_posting,
    checkable,
)
from jobadvaisor.data.loader import DataRepositoryError, load
from jobadvaisor.data.models import ClosedRule, Posting
from jobadvaisor.data.writer import delete_posting, read_posting, update_posting
from jobadvaisor.intake import fetch
from jobadvaisor.intake.company_facts import Throttle

PAGE = "<html><body><main>" + "We look for a developer. " * 40 + "</main></body></html>"
JOB = "https://jobs.example.org/job/1"
OTHER = "https://careers.example.net/job/2"
TEXT_RULE = ClosedRule(host="example.org", text_marker="no longer available")
BY_USER = {"state": "available", "set_at": AT, "set_by": "user"}


def reply(status: int = 200, **kwargs):
    """A route answer: a response built anew for every request."""
    return lambda: httpx.Response(status, **kwargs)


class Site:
    """An httpx client over a mock transport: `routes` maps a URL to `reply(...)` or to an
    exception to raise, any other URL answers 200 with `PAGE`; every requested URL goes to
    `seen`, and `on_request` (if set) is called with it first."""

    def __init__(self, routes: dict | None = None):
        self.routes, self.seen, self.on_request = routes or {}, [], None
        self.client = httpx.Client(transport=httpx.MockTransport(self._handle),
                                   follow_redirects=True)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.seen.append(url)
        if self.on_request:
            self.on_request(url)
        answer = self.routes.get(url, reply(200, text=PAGE))
        if isinstance(answer, Exception):
            raise answer
        return answer()


class Clock:
    """A fake clock whose sleep advances it; `sleeps` lists every pause."""

    def __init__(self):
        self.now, self.sleeps = 0.0, []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def throttle(self) -> Throttle:
        return Throttle(HOST_SPACING_SECONDS, self, self.sleep)


@pytest.fixture(autouse=True)
def example_org_text_rule():
    """The closed rules in force for calls made on the test's own thread: the defaults and a
    text marker for example.org. A check's worker thread does not see them."""
    token = fetch.closed_rules.set([*fetch.DEFAULT_CLOSED_RULES, TEXT_RULE])
    yield
    fetch.closed_rules.reset(token)


def posting(*urls: str, **fields) -> Posting:
    return Posting(schema_version="2", title="Backend Engineer", company="Acme", text="Text",
                   location_raw="Remote", source_type="url", urls=list(urls),
                   added_at=datetime(2026, 1, 5, tzinfo=UTC), **fields)


def test_the_spacing_is_three_seconds_per_host():
    assert HOST_SPACING_SECONDS == 3


# --- check_posting: what the links of one posting say

def test_a_page_that_answers_is_available():
    assert check_posting(posting(JOB), [], http=Site().client) == "available"


@pytest.mark.parametrize("status", [404, 410])
def test_a_gone_page_is_closed(status):
    site = Site({JOB: reply(status)})
    assert check_posting(posting(JOB), [], http=site.client) == "closed"
    assert site.seen == [JOB]


def test_a_redirect_to_a_closed_marker_is_closed_and_its_target_is_never_requested():
    start = "https://www.linkedin.com/jobs/view/4242"
    target = "https://www.linkedin.com/jobs/search?trk=expired_jd_redirect"
    site = Site({start: reply(302, headers={"Location": target})})
    assert check_posting(posting(start), [], http=site.client) == "closed"
    assert site.seen == [start]


def test_a_text_marker_on_the_visible_page_is_closed_and_a_script_text_is_not():
    marked = PAGE.replace("<main>", "<main><p>This job is NO LONGER available.</p>")
    scripted = PAGE.replace("<main>", "<script>var s='no longer available'</script><main>")
    assert check_posting(posting(JOB), [], http=Site({JOB: reply(text=marked)}).client) == "closed"
    assert check_posting(posting(JOB), [],
                         http=Site({JOB: reply(text=scripted)}).client) == "available"


@pytest.mark.parametrize("answer", [
    reply(429), reply(503), reply(403), httpx.ReadTimeout("slow"), httpx.ConnectError("down")])
def test_a_rate_limit_a_server_error_or_a_failure_is_unknown(answer):
    site = Site({JOB: answer})
    assert check_posting(posting(JOB), [], http=site.client) == "unknown"
    assert site.seen == [JOB]  # not retried


def test_a_gone_link_beside_a_live_one_is_available():
    site = Site({JOB: reply(404)})
    assert check_posting(posting(JOB, OTHER), [], http=site.client) == "available"


@pytest.mark.parametrize("private", [
    "http://localhost:8710/pool", "http://127.0.0.1/job", "http://10.0.0.5/job", "file:///etc/hosts"])
def test_a_link_to_a_non_public_host_is_never_requested_and_leaves_the_posting_unknown(private):
    site = Site()
    assert check_posting(posting(private), [], http=site.client) == "unknown"
    assert check_posting(posting(private, JOB), [], http=site.client) == "available"
    assert site.seen == [JOB]


def test_a_gone_link_beside_an_unreachable_one_is_unknown():
    site = Site({JOB: reply(404), OTHER: httpx.ReadTimeout("slow")})
    assert check_posting(posting(JOB, OTHER), [], http=site.client) == "unknown"


def test_every_link_gone_is_closed():
    site = Site({JOB: reply(404), OTHER: reply(410)})
    assert check_posting(posting(JOB, OTHER), [], http=site.client) == "closed"


def test_a_refused_redirect_is_unknown():
    target = JOB + "?sid=TOKEN-1"
    site = Site({JOB: reply(302, headers={"Location": target})})
    assert check_posting(posting(JOB), [], http=site.client) == "unknown"
    assert site.seen == [JOB]


def test_a_stored_link_with_a_tracking_parameter_is_requested_and_decides():
    tracked = JOB + "?utm_source=x"
    site = Site()
    assert check_posting(posting(tracked), [], http=site.client) == "available"
    assert site.seen == [tracked]
    site = Site({tracked: reply(404)})
    assert check_posting(posting(tracked), [], http=site.client) == "closed"


@pytest.mark.parametrize("stored", ["https://JOBS.Example.org/job/1?utm_source=x",
                                    "https://jobs.example.org:443/job/1?utm_source=x"])
def test_a_tracked_link_in_another_spelling_is_still_the_start_link(stored):
    site = Site({JOB + "?utm_source=x": reply(404)})  # httpx normalises host case and port
    assert check_posting(posting(stored), [], http=site.client) == "closed"
    assert site.seen == [JOB + "?utm_source=x"]


def test_a_redirect_with_a_personal_parameter_stays_refused_from_a_tracked_link():
    tracked = JOB + "?utm_source=x"
    site = Site({tracked: reply(302, headers={"Location": JOB + "?sid=TOKEN-1"})})
    assert check_posting(posting(tracked), [], http=site.client) == "unknown"
    assert site.seen == [tracked]


def test_a_login_walled_link_is_neither_fetched_nor_counted():
    walled = "https://www.xing.com/jobs/1"
    site = Site({JOB: reply(404)})
    assert check_posting(posting(walled, JOB), ["xing.com"], http=site.client) == "closed"
    assert site.seen == [JOB]


def test_requests_to_one_host_are_spaced():
    clock, site = Clock(), Site()
    check_posting(posting(JOB, JOB + "b", OTHER), [], http=site.client, throttle=clock.throttle())
    assert clock.sleeps == []  # the first answer ends the check: one request, no wait
    site = Site({JOB: reply(404), JOB + "b": reply(404)})
    check_posting(posting(JOB, JOB + "b"), [], http=site.client, throttle=clock.throttle())
    assert clock.sleeps == [HOST_SPACING_SECONDS]


# --- check_batch: which postings a check covers

def test_the_batch_covers_open_postings_with_a_link_whatever_their_availability(tmp_path):
    root = tmp_path
    write_json(root / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(root / "policy-pack.json", POLICY_PACK)
    urls = {"urls": [JOB]}
    add_posting(root, "never-checked", "Engineer 1", **urls)
    add_posting(root, "by-check", "Engineer 2", **urls,
                availability={**BY_USER, "set_by": "check", "state": "unknown"})
    add_posting(root, "applied", "Engineer 3", schema_version="2", status="applied", **urls)
    add_posting(root, "done", "Engineer 4", schema_version="2", status="done", **urls)
    add_posting(root, "closed", "Engineer 5", **urls,
                availability={**BY_USER, "set_by": "check", "state": "closed"})
    add_posting(root, "by-user", "Engineer 6", **urls, availability=BY_USER)
    add_posting(root, "pasted", "Engineer 7", source_type="text")
    add_posting(root, "walled", "Engineer 8", urls=["https://www.xing.com/jobs/1"])
    add_posting(root, "walled-and-open", "Engineer 9",
                urls=["https://www.xing.com/jobs/2", OTHER])
    assert check_batch(load(root)) == [
        "by-check", "by-user", "closed", "never-checked", "walled-and-open"]


@pytest.mark.parametrize(("urls", "expected"), [
    ([JOB], True), (["https://www.xing.com/jobs/1"], False),
    (["http://[bad"], False), (["http://localhost/job"], False),
    (["https://www.xing.com/jobs/2", OTHER], True)])
def test_a_posting_is_checkable_by_the_links_the_batch_reads(urls, expected):
    """`checkable` uses the batch's link rule, whatever the posting's application status."""
    assert checkable(posting(*urls, status="applied"), ["xing.com"]) is expected


def test_a_pasted_posting_is_not_checkable():
    pasted = posting(JOB).model_copy(update={"source_type": "text", "urls": []})
    assert checkable(pasted, []) is False


# --- AvailabilityChecks: the run and its report

@pytest.fixture
def root(tmp_path):
    write_json(tmp_path / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(tmp_path / "policy-pack.json", POLICY_PACK)
    return tmp_path


def finished(checks: AvailabilityChecks, check_id: str) -> dict:
    for _ in range(500):
        state = checks.read(check_id)
        if state["status"] != "running":
            return state
        time.sleep(0.01)
    raise AssertionError("check did not finish")


def run(root, site: Site, clock: Clock | None = None) -> dict:
    checks = AvailabilityChecks(root, http=site.client, throttle=(clock or Clock()).throttle())
    return finished(checks, checks.start())


def test_a_check_stores_each_state_and_reports_the_counts_and_the_closed_postings(root):
    for number, link in enumerate(["https://a.example.org/1", "https://b.example.org/2",
                                   "https://c.example.org/3", "https://d.example.org/4"], 1):
        add_posting(root, f"p{number}", f"Engineer {number}", urls=[link])
    site = Site({"https://b.example.org/2": reply(404), "https://c.example.org/3": reply(429),
                 "https://d.example.org/4": reply(410)})
    before = datetime.now(UTC)
    state = run(root, site)
    assert state["status"] == "done" and state["error"] is None
    assert (state["total"], state["done"]) == (4, 4)
    assert state["counts"] == {"available": 1, "closed": 2, "unknown": 1}
    assert state["closed"] == [
        {"posting_id": "p2", "title": "Engineer 2", "company": "Example Corp"},
        {"posting_id": "p4", "title": "Engineer 4", "company": "Example Corp"}]
    stored = {i: read_posting(root, i).availability for i in ("p1", "p2", "p3", "p4")}
    assert [a.state for a in stored.values()] == ["available", "closed", "unknown", "closed"]
    assert all(a.set_by == "check" and before <= a.set_at for a in stored.values())
    assert read_posting(root, "p2").schema_version == "1"  # no new version, nothing else changed


def test_an_empty_batch_is_a_finished_check(root):
    add_posting(root, "pasted", "Engineer 1", source_type="text")
    state = run(root, Site())
    assert (state["status"], state["total"], state["done"]) == ("done", 0, 0)


def test_the_batch_alternates_between_hosts_and_spaces_each_host(root):
    for number in range(1, 5):
        host = "a" if number <= 2 else "b"
        add_posting(root, f"p{number}", f"Engineer {number}",
                    urls=[f"https://{host}.example.org/{number}"])
    site, clock = Site(), Clock()
    run(root, site, clock)
    assert site.seen == ["https://a.example.org/1", "https://b.example.org/3",
                         "https://a.example.org/2", "https://b.example.org/4"]
    assert clock.sleeps == [HOST_SPACING_SECONDS]  # a's second request waits, b's is already due


def test_two_postings_of_one_host_are_three_seconds_apart(root):
    add_posting(root, "p1", "Engineer 1", urls=[JOB])
    add_posting(root, "p2", "Engineer 2", urls=[JOB + "b"])
    clock = Clock()
    run(root, Site(), clock)
    assert clock.sleeps == [3.0]


def test_a_hand_setting_made_during_the_check_survives_it(root):
    add_posting(root, "p1", "Engineer 1", urls=["https://a.example.org/1"])
    add_posting(root, "p2", "Engineer 2", urls=["https://b.example.org/2"])
    site = Site({"https://b.example.org/2": reply(404)})
    site.on_request = lambda url: url.endswith("/1") and update_posting(
        root, "p2", {"availability": BY_USER})  # the user acts while the check reaches p1
    state = run(root, site)
    assert read_posting(root, "p2").availability.set_by == "user"
    assert read_posting(root, "p2").availability.state == "available"
    assert state["done"] == 2 and state["counts"] == {"available": 1, "closed": 0, "unknown": 0}
    assert state["closed"] == []


def test_a_value_changed_and_changed_back_during_the_check_survives_it(root):
    add_posting(root, "p1", "Engineer 1", urls=["https://a.example.org/1"])
    add_posting(root, "p2", "Engineer 2", urls=["https://b.example.org/2"], availability=BY_USER)
    again = {**BY_USER, "set_at": "2026-05-01T09:00:00Z"}

    def act(url):
        if url.endswith("/1"):  # the same state set again is still not what the check saw
            update_posting(root, "p2", {"availability": {**BY_USER, "state": "closed"}})
            update_posting(root, "p2", {"availability": again})
    site = Site({"https://b.example.org/2": reply(404)})
    site.on_request = act
    state = run(root, site)
    stored = read_posting(root, "p2").availability
    assert (stored.state, stored.set_by, stored.set_at.day, stored.set_at.month) == (
        "available", "user", 1, 5)
    assert state["counts"] == {"available": 1, "closed": 0, "unknown": 0} and state["closed"] == []


@pytest.mark.parametrize("set_by", ["user", "check"])
def test_a_closed_posting_whose_link_answers_ends_available_set_by_the_check(root, set_by):
    add_posting(root, "p1", "Engineer 1", urls=[JOB],
                availability={**BY_USER, "state": "closed", "set_by": set_by})
    before = datetime.now(UTC)
    state = run(root, Site())
    stored = read_posting(root, "p1").availability
    assert (stored.state, stored.set_by) == ("available", "check") and before <= stored.set_at
    assert state["counts"] == {"available": 1, "closed": 0, "unknown": 0}


def test_a_hand_available_posting_whose_link_answers_404_ends_closed_and_is_listed(root):
    add_posting(root, "p1", "Engineer 1", urls=[JOB], availability=BY_USER)
    state = run(root, Site({JOB: reply(404)}))
    stored = read_posting(root, "p1").availability
    assert (stored.state, stored.set_by) == ("closed", "check")
    assert [c["posting_id"] for c in state["closed"]] == ["p1"]
    assert (state["counts"]["closed"], state["still_closed"]) == (1, 0)


@pytest.mark.parametrize("answer", [reply(429), httpx.ReadTimeout("slow")])
def test_a_closed_posting_found_unknown_stays_closed_with_its_old_record(root, answer):
    old = {"state": "closed", "set_at": AT, "set_by": "user"}
    add_posting(root, "p1", "Engineer 1", urls=[JOB], availability=old)
    path = root / "postings" / "p1.json"
    before = path.read_text()
    state = run(root, Site({JOB: answer}))
    assert path.read_text() == before  # no write at all
    assert state["counts"] == {"available": 0, "closed": 0, "unknown": 1}
    assert state["closed"] == [] and state["still_closed"] == 0


def test_a_closed_posting_found_unknown_but_reopened_during_the_check_counts_nowhere(root):
    old = {"state": "closed", "set_at": AT, "set_by": "check"}
    add_posting(root, "p1", "Engineer 1", urls=["https://a.example.org/1"])
    add_posting(root, "p2", "Engineer 2", urls=["https://b.example.org/2"], availability=old)
    site = Site({"https://b.example.org/2": reply(429)})
    site.on_request = lambda url: url.endswith("/1") and update_posting(
        root, "p2", {"availability": BY_USER})  # the user reopens p2 while the check reaches p1
    state = run(root, site)
    assert read_posting(root, "p2").availability.set_by == "user"
    assert (state["done"], state["counts"]) == (2, {"available": 1, "closed": 0, "unknown": 0})
    assert state["closed"] == [] and state["still_closed"] == 0


def test_a_closed_posting_found_unknown_but_deleted_during_the_check_counts_nowhere(root):
    old = {"state": "closed", "set_at": AT, "set_by": "check"}
    add_posting(root, "p1", "Engineer 1", urls=["https://a.example.org/1"])
    add_posting(root, "p2", "Engineer 2", urls=["https://b.example.org/2"], availability=old)
    site = Site({"https://b.example.org/2": reply(429)})
    site.on_request = lambda url: url.endswith("/1") and (
        root / "postings" / "p2.json").unlink()
    state = run(root, site)
    assert not (root / "postings" / "p2.json").exists()
    assert (state["done"], state["counts"]) == (2, {"available": 1, "closed": 0, "unknown": 0})


def test_an_already_closed_posting_found_closed_again_is_counted_but_not_listed(root):
    old = {"state": "closed", "set_at": AT, "set_by": "check"}
    add_posting(root, "p1", "Engineer 1", urls=["https://a.example.org/1"], availability=old)
    add_posting(root, "p2", "Engineer 2", urls=["https://b.example.org/2"],
                availability={**old, "set_by": "user"})
    add_posting(root, "p3", "Engineer 3", urls=["https://c.example.org/3"])
    before = datetime.now(UTC)
    state = run(root, Site({f"https://{h}.example.org/{n}": reply(404)
                            for n, h in enumerate("abc", 1)}))
    assert state["counts"] == {"available": 0, "closed": 3, "unknown": 0}
    assert [c["posting_id"] for c in state["closed"]] == ["p3"]
    assert state["still_closed"] == 2
    renewed = read_posting(root, "p2").availability  # a fresh record by the check
    assert (renewed.state, renewed.set_by) == ("closed", "check") and before <= renewed.set_at


def test_a_posting_deleted_during_the_check_is_not_brought_back(root):
    add_posting(root, "p1", "Engineer 1", urls=["https://a.example.org/1"])
    add_posting(root, "p2", "Engineer 2", urls=["https://b.example.org/2"])
    site = Site()
    site.on_request = lambda url: url.endswith("/1") and (
        root / "postings" / "p2.json").unlink()
    state = run(root, site)
    assert not (root / "postings" / "p2.json").exists()
    assert (state["done"], state["counts"]["available"]) == (2, 1)


def test_the_policy_packs_closed_rules_reach_the_worker_thread(root):
    write_json(root / "policy-pack.json", {**POLICY_PACK, "closed_rules": [
        {"host": "board.example.net", "text_marker": "position closed"}]})
    add_posting(root, "p1", "Engineer 1", urls=["https://board.example.net/1"])
    site = Site({"https://board.example.net/1": reply(
        text=PAGE.replace("<main>", "<main><p>Position closed.</p>"))})
    state = run(root, site)
    assert state["counts"] == {"available": 0, "closed": 1, "unknown": 0}


def test_a_posting_with_only_malformed_or_non_public_links_is_not_in_the_batch(root):
    add_posting(root, "bad", "Engineer 1", urls=["http://[bad"])
    add_posting(root, "local", "Engineer 2", urls=["http://localhost:8710/pool"])
    add_posting(root, "good", "Engineer 3", urls=[JOB])
    assert check_batch(load(root)) == ["good"]  # and a malformed link does not raise
    site = Site()
    state = run(root, site)
    assert state["status"] == "done"
    assert (state["total"], state["counts"]) == (1, {"available": 1, "closed": 0, "unknown": 0})
    assert site.seen == [JOB]
    assert read_posting(root, "bad").availability is None


def test_a_posting_that_no_longer_validates_is_skipped_and_the_check_goes_on(root, monkeypatch):
    add_posting(root, "p1", "Engineer 1", urls=["https://a.example.org/1"])
    add_posting(root, "p2", "Engineer 2", urls=["https://b.example.org/2"])
    real = availability_module.write_availability

    def write(root_, posting_id, availability, expected):
        if posting_id == "p1":
            raise ValueError("p1.json does not validate")
        return real(root_, posting_id, availability, expected)
    monkeypatch.setattr(availability_module, "write_availability", write)
    state = run(root, Site())
    assert (state["status"], state["error"]) == ("done", None)
    assert (state["total"], state["done"]) == (2, 2)
    assert state["counts"] == {"available": 1, "closed": 0, "unknown": 0}  # p1 counts nowhere
    assert read_posting(root, "p2").availability.state == "available"


def test_a_second_start_is_refused_while_the_first_computes(root):
    add_posting(root, "p1", "Engineer 1", urls=[JOB])
    release, entered = threading.Event(), threading.Event()
    site = Site()
    site.on_request = lambda url: (entered.set(), release.wait(30))
    checks = AvailabilityChecks(root, http=site.client, throttle=Clock().throttle())
    first = checks.start()
    assert entered.wait(10)
    with pytest.raises(CheckBusyError) as refused:
        checks.start()
    assert refused.value.check_id == first
    assert checks.read(first)["status"] == "running"
    release.set()
    assert finished(checks, first)["status"] == "done"
    assert finished(checks, checks.start())["status"] == "done"  # free again


def test_an_unknown_check_reads_none(root):
    assert AvailabilityChecks(root).read("nope") is None


def test_a_crash_fails_the_check_and_frees_the_next(root, monkeypatch):
    add_posting(root, "p1", "Engineer 1", urls=[JOB])
    checks = AvailabilityChecks(root, http=Site().client, throttle=Clock().throttle())

    def crash(*args):
        raise KeyError("boom")
    monkeypatch.setattr(availability_module, "write_availability", crash)
    state = finished(checks, checks.start())
    assert (state["status"], state["error"]) == ("failed", "KeyError")
    monkeypatch.undo()
    assert finished(checks, checks.start())["status"] == "done"


def test_a_cancel_stops_after_the_posting_in_flight_and_keeps_its_results(root):
    for number, host in enumerate("abc", 1):
        add_posting(root, f"p{number}", f"Engineer {number}",
                    urls=[f"https://{host}.example.org/{number}"])
    release, entered = threading.Event(), threading.Event()
    site = Site({"https://a.example.org/1": reply(404)})
    site.on_request = lambda url: (entered.set(), release.wait(30))
    checks = AvailabilityChecks(root, http=site.client, throttle=Clock().throttle())
    check_id = checks.start()
    assert entered.wait(10)
    checks.cancel(check_id)
    assert checks.read(check_id)["cancel_requested"] is True
    release.set()
    state = finished(checks, check_id)
    assert state["status"] == "cancelled" and state["error"] is None
    assert (state["total"], state["done"]) == (3, 1)
    assert state["counts"] == {"available": 0, "closed": 1, "unknown": 0}
    assert [c["posting_id"] for c in state["closed"]] == ["p1"]
    assert site.seen == ["https://a.example.org/1"]  # no further posting was fetched
    assert read_posting(root, "p1").availability.state == "closed"
    assert read_posting(root, "p2").availability is None
    assert finished(checks, checks.start())["status"] == "done"  # the cancelled check freed it


def test_cancelling_an_ended_or_unknown_check_is_refused(root):
    add_posting(root, "p1", "Engineer 1", urls=[JOB])
    checks = AvailabilityChecks(root, http=Site().client, throttle=Clock().throttle())
    check_id = checks.start()
    assert finished(checks, check_id)["status"] == "done"
    with pytest.raises(CheckStateError):
        checks.cancel(check_id)
    with pytest.raises(KeyError):
        checks.cancel("nope")


# --- exclusive and running: what a delete needs of the checks (`113-posting-delete` D2)

def blocked_check(root, *posting_ids: str):
    """Postings `posting_ids` with a link each, and a check over them that waits inside its
    first request; returns `(checks, check_id, release)` once it has entered."""
    for posting_id in posting_ids:
        add_posting(root, posting_id, f"Engineer {posting_id}",
                    urls=[f"https://{posting_id}.example.org/1"])
    release, entered = threading.Event(), threading.Event()
    site = Site()
    site.on_request = lambda url: (entered.set(), release.wait(30))
    checks = AvailabilityChecks(root, http=site.client, throttle=Clock().throttle())
    check_id = checks.start()
    assert entered.wait(10)
    return checks, check_id, release


def test_exclusive_is_refused_while_a_check_computes_and_running_names_it(root):
    checks, check_id, release = blocked_check(root, "p1")
    assert checks.running() == check_id
    with pytest.raises(CheckBusyError) as refused:
        with checks.exclusive():
            pytest.fail("the block ran beside a running check")
    assert refused.value.check_id == check_id
    release.set()
    assert finished(checks, check_id)["status"] == "done"
    assert checks.running() is None
    with checks.exclusive():  # free again
        pass


def test_running_is_none_while_no_check_computes(root):
    assert AvailabilityChecks(root).running() is None


def test_a_check_started_inside_exclusive_waits_and_leaves_out_a_posting_deleted_there(root):
    for posting_id in ("p1", "p2"):
        add_posting(root, posting_id, f"Engineer {posting_id}",
                    urls=[f"https://{posting_id}.example.org/1"])
    checks = AvailabilityChecks(root, http=Site().client, throttle=Clock().throttle())
    started: list[str] = []
    starter = threading.Thread(target=lambda: started.append(checks.start()))
    with checks.exclusive():
        starter.start()
        starter.join(0.3)
        assert starter.is_alive() and not started  # it waits for the block to end
        delete_posting(root, "p2")
    starter.join(10)
    state = finished(checks, started[0])
    assert (state["status"], state["total"], state["done"]) == ("done", 1, 1)
    assert checks.read(started[0])["counts"]["available"] == 1


def test_the_lock_is_free_again_after_an_exception_inside_exclusive(root):
    checks = AvailabilityChecks(root, http=Site().client, throttle=Clock().throttle())
    with pytest.raises(RuntimeError):
        with checks.exclusive():
            raise RuntimeError("the block fails")
    assert finished(checks, checks.start())["status"] == "done"


def test_a_failed_load_in_start_frees_the_claim(root):
    write_json(root / "postings/broken.json", {"schema_version": "1"})
    checks = AvailabilityChecks(root, http=Site().client, throttle=Clock().throttle())
    with pytest.raises(DataRepositoryError):
        checks.start()
    assert checks.running() is None
    (root / "postings/broken.json").unlink()
    assert finished(checks, checks.start())["status"] == "done"


def test_a_second_start_while_the_first_loads_is_refused(root, monkeypatch):
    """`start` claims before it loads, so a delete or a second check cannot slip into the gap."""
    add_posting(root, "p1", "Engineer 1", urls=[JOB])
    loading, release = threading.Event(), threading.Event()
    real = availability_module.load

    def slow_load(location):
        loading.set()
        assert release.wait(10)
        return real(location)

    monkeypatch.setattr(availability_module, "load", slow_load)
    checks = AvailabilityChecks(root, http=Site().client, throttle=Clock().throttle())
    started: list[str] = []
    starter = threading.Thread(target=lambda: started.append(checks.start()))
    starter.start()
    assert loading.wait(10)
    with pytest.raises(CheckBusyError):
        checks.start()
    with pytest.raises(CheckBusyError):
        with checks.exclusive():
            pass
    release.set()
    starter.join(10)
    assert finished(checks, started[0])["status"] == "done"
