"""`/unsettled-links` and the list upkeep of `POST /alert-mails/runs`
(`openspec/changes/archive/2026-11-27-182-unsettled-links-list/design.md` D7). Regression tests,
no model call."""

import threading
from datetime import UTC, datetime

import pytest
from conftest import write_json
from test_api_alert_mails import client, settled
from test_triage_graph import POLICY_PACK, add_posting

import jobadvaisor.data.writer as writer_module
import jobadvaisor.intake.alert_runs as runs_module
from jobadvaisor.data.models import UnsettledLink, UnsettledLinks
from jobadvaisor.data.writer import (
    read_unsettled_links,
    update_mailbox_account,
    update_unsettled_links,
)
from jobadvaisor.intake.postings import PostingNotFoundError

A, B = "https://jobs.example.org/stelle/1", "https://jobs.example.org/stelle/2"
LINKEDIN = "https://www.linkedin.com/jobs/view/4100000101"
EARLIER = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
RATE_LIMITED = [{"step": "plain", "url": A, "outcome": "HTTP 429"}]
FIELDS = {"url", "title", "source", "state", "tries", "added_at", "last_tried_at", "attempts",
          "reason", "in_run"}


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DIRECTORY", str(tmp_path / "state"))
    root = tmp_path / "data"
    write_json(root / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(root / "policy-pack.json", POLICY_PACK)
    add_posting(root, "p1", "Engineer 1")
    return root


def answering(outcomes: dict):
    """An `add_from_url` stand-in: per URL a posting ID, or an exception to raise."""
    def add(intake, url, *, allow_text_duplicate=False):
        outcome = outcomes[url]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome, None, None, []
    return add


def holding(monkeypatch):
    """An `add_from_url` that stores every link once `release` is set; `entered` is set once
    the first call is inside."""
    entered, release = threading.Event(), threading.Event()

    def add(intake, url, *, allow_text_duplicate=False):
        entered.set()
        assert release.wait(30)
        return "p", None, None, []
    monkeypatch.setattr(runs_module, "add_from_url", add)
    return entered, release


def listed(root, *links: UnsettledLink) -> None:
    update_unsettled_links(root, lambda current: UnsettledLinks(schema_version="1",
                                                                links=list(links)))


def row(url: str, **changes) -> UnsettledLink:
    """A row a mailbox run left unread with one try."""
    return UnsettledLink.model_validate({
        "url": url, "title": "Old title", "source": "mailbox", "state": "unread", "tries": 1,
        "added_at": EARLIER, "last_tried_at": EARLIER,
        "attempts": [{"step": "plain", "outcome": "HTTP 429"}]} | changes)


def run(http, entries: list[dict], **body) -> dict:
    answer = http.post("/alert-mails/runs", json={"entries": entries} | body)
    assert answer.status_code == 202, answer.text
    return settled(http, answer.json()["run_id"])


def test_a_pasted_runs_failed_entry_is_listed_with_the_source_paste(tmp_path, root,
                                                                     monkeypatch):
    """posting-intake → Scenario: Pasted mail."""
    monkeypatch.setattr(runs_module, "add_from_url", answering({
        A: PostingNotFoundError(RATE_LIMITED), B: "b"}))
    http = client(tmp_path, root)
    run(http, [{"url": A, "title": "Platform Engineer"}, {"url": B, "title": "B"}])
    answer = http.get("/unsettled-links")
    assert answer.status_code == 200
    body = answer.json()
    assert body["run_id"] is None and len(body["links"]) == 1
    link, = body["links"]
    assert set(link) == FIELDS
    assert (link["url"], link["title"], link["source"], link["state"], link["tries"],
            link["in_run"]) == (A, "Platform Engineer", "paste", "unread", 1, False)
    assert link["attempts"] == [{"step": "plain", "outcome": "HTTP 429"}]


def test_a_retry_that_stores_the_link_empties_the_list_and_marks_no_mail(tmp_path, root,
                                                                         monkeypatch):
    """posting-intake → Scenario: Retry stores a link."""
    update_mailbox_account(root, "imap.example.org", 993, "name@example.org")
    before = (root / "mailbox.json").read_bytes()
    listed(root, row(A))
    monkeypatch.setattr(runs_module, "add_from_url", answering({A: "a"}))
    http = client(tmp_path, root)
    run(http, [{"url": A, "title": "Old title"}])
    assert http.get("/unsettled-links").json()["links"] == []
    assert (root / "mailbox.json").read_bytes() == before


def test_a_retry_that_fails_again_keeps_the_row_its_source_and_first_date(tmp_path, root,
                                                                         monkeypatch):
    """posting-intake → Scenario: Retry fails again; the route cleans the posted link first,
    and the cleaned link still matches the row."""
    listed(root, row(LINKEDIN))
    monkeypatch.setattr(runs_module, "add_from_url", answering({
        LINKEDIN: PostingNotFoundError([{"step": "plain", "url": LINKEDIN,
                                         "outcome": "HTTP 999"}])}))
    http = client(tmp_path, root)
    raw = f"{LINKEDIN.replace('/jobs/', '/comm/jobs/')}/?trk=TOKEN-4"
    run(http, [{"url": raw, "title": "Old title"}])  # no `source`: a retry from the list
    again, = read_unsettled_links(root).links
    assert (again.url, again.source, again.added_at, again.tries, again.state) == (
        LINKEDIN, "mailbox", EARLIER, 2, "unread")
    assert again.last_tried_at > EARLIER
    assert [a.outcome for a in again.attempts] == ["HTTP 999"]


def test_a_retry_while_a_run_computes_is_409_naming_it(tmp_path, root, monkeypatch):
    """posting-intake → Scenario: Retry during a run."""
    listed(root, row(B))
    entered, release = holding(monkeypatch)
    http = client(tmp_path, root)
    first = http.post("/alert-mails/runs", json={"entries": [{"url": A, "title": "A"}]})
    assert entered.wait(10)
    retry = http.post("/alert-mails/runs", json={"entries": [{"url": B, "title": "B"}]})
    assert retry.status_code == 409 and retry.json()["error"] == "alert run in progress"
    assert retry.json()["run_id"] == first.json()["run_id"]
    release.set()
    settled(http, first.json()["run_id"])


def test_the_list_names_the_computing_run_and_none_after_it(tmp_path, root, monkeypatch):
    """posting-intake → Scenario: List names the computing run."""
    entered, release = holding(monkeypatch)
    http = client(tmp_path, root)
    run_id = http.post("/alert-mails/runs", json={"entries": [{"url": A, "title": "A"}]}
                       ).json()["run_id"]
    assert entered.wait(10)
    during = http.get("/unsettled-links").json()
    assert during["run_id"] == run_id
    assert [(link["url"], link["state"], link["in_run"]) for link in during["links"]] == [
        (A, "waiting", True)]
    release.set()
    settled(http, run_id)
    assert http.get("/unsettled-links").json() == {"links": [], "run_id": None}


def test_a_run_takes_up_to_1000_entries(tmp_path, root, monkeypatch):
    """posting-intake → Scenario: More than 100 links."""
    links = [f"https://jobs.example.org/stelle/{n}" for n in range(1001)]
    monkeypatch.setattr(runs_module, "add_from_url", answering(dict.fromkeys(links, "p")))
    http = client(tmp_path, root)
    state = run(http, [{"url": url, "title": "t"} for url in links[:140]])
    assert state["total"] == 140 and state["status"] == "done"
    refused = http.post("/alert-mails/runs",
                        json={"entries": [{"url": url, "title": "t"} for url in links]})
    assert refused.status_code == 422 and refused.json()["error"] == "invalid request"


@pytest.mark.parametrize("source", ["mailbox", "paste"])
def test_a_run_lists_a_new_link_with_the_source_it_names(tmp_path, root, monkeypatch, source):
    monkeypatch.setattr(runs_module, "add_from_url", answering({
        A: PostingNotFoundError(RATE_LIMITED)}))
    http = client(tmp_path, root)
    run(http, [{"url": A, "title": "A"}], source=source)
    assert read_unsettled_links(root).links[0].source == source


def test_an_unknown_source_is_refused(tmp_path, root):
    answer = client(tmp_path, root).post("/alert-mails/runs", json={
        "entries": [{"url": A, "title": "A"}], "source": "mail"})
    assert answer.status_code == 422


# --- removal ----------------------------------------------------------------------------------


def delete(http, url: str):
    return http.request("DELETE", "/unsettled-links", json={"url": url})


def test_a_removal_answers_the_list_without_the_link(tmp_path, root):
    """posting-intake → Scenario: Remove a link."""
    listed(root, row(A), row(B, last_tried_at=datetime(2026, 11, 21, tzinfo=UTC)))
    http = client(tmp_path, root)
    answer = delete(http, A)
    assert answer.status_code == 200
    assert [link["url"] for link in answer.json()["links"]] == [B]
    assert set(answer.json()) == {"links"}
    assert [r.url for r in read_unsettled_links(root).links] == [B]


def test_a_removal_of_an_unknown_link_is_404(tmp_path, root):
    """posting-intake → Scenario: Unknown link."""
    listed(root, row(A))
    answer = delete(client(tmp_path, root), B)
    assert answer.status_code == 404 and answer.json()["error"] == "not found"


def test_a_removal_of_a_link_in_the_computing_run_is_409(tmp_path, root, monkeypatch):
    """posting-intake → Scenario: Remove during the run."""
    entered, release = holding(monkeypatch)
    http = client(tmp_path, root)
    run_id = http.post("/alert-mails/runs", json={"entries": [{"url": A, "title": "A"}]}
                       ).json()["run_id"]
    assert entered.wait(10)
    answer = delete(http, A)
    assert answer.status_code == 409 and answer.json()["error"] == "link in run"
    release.set()
    settled(http, run_id)


# --- an unreadable list -----------------------------------------------------------------------


def refuse_list_writes(monkeypatch) -> None:
    """Make every write of `unsettled-links.json` fail with an `OSError`; other files write."""
    replace = writer_module._replace

    def refusing(path, entity):
        if path.name == "unsettled-links.json":
            raise PermissionError("read-only")
        replace(path, entity)
    monkeypatch.setattr(writer_module, "_replace", refusing)


@pytest.mark.parametrize("call", ["list", "remove", "run", "remove: write fails",
                                  "run: write fails"])
def test_an_invalid_list_file_is_503_and_starts_nothing(tmp_path, root, monkeypatch, call):
    """posting-intake → Scenarios: Invalid list file, List cannot be written."""
    if call.endswith("write fails"):
        listed(root, row(A))
        refuse_list_writes(monkeypatch)
        call = call.split(":")[0]
    else:
        (root / "unsettled-links.json").write_text('{"schema_version": "1", "links": [{}]}')
    seen = []
    monkeypatch.setattr(runs_module, "add_from_url", lambda *args, **kwargs: seen.append(args))
    http = client(tmp_path, root)
    answer = {"list": lambda: http.get("/unsettled-links"),
              "remove": lambda: delete(http, A),
              "run": lambda: http.post("/alert-mails/runs",
                                       json={"entries": [{"url": A, "title": "A"}]})}[call]()
    assert answer.status_code == 503, answer.text
    assert answer.json()["error"] == "unsettled links unreadable"
    assert answer.json()["detail"].startswith("unsettled-links.json")
    assert "\n" not in answer.json()["detail"] and seen == []
