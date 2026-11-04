"""Intake calls the company lookup once per new company, after the posting is stored."""

from functools import partial

import pytest
from conftest import FakeStructuredModel, write_json
from fastapi.testclient import TestClient
from test_company_lookup import LINKEDIN, FakeWeb, NoWait, about, ok, organization
from test_intake_duplicates import FIELDS
from test_triage_graph import POLICY_PACK, Harness

from jobadvaisor.api.app import create_app
from jobadvaisor.data.loader import load
from jobadvaisor.data.models import company_id
from jobadvaisor.intake import postings as postings_module
from jobadvaisor.intake.company_facts import look_up
from jobadvaisor.intake.fetch import Page
from jobadvaisor.intake.ladder import LadderResult
from jobadvaisor.intake.postings import Intake, add_from_url
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.triage.runs import Runs

TEXT = "You build data pipelines in Python and SQL for our sensor fleet. " * 5


@pytest.fixture
def intake(data_repository):
    return Intake(data_repository, FakeStructuredModel({"company": "unknown"}),
                  ContentGuard(None, {}))


@pytest.fixture
def pages(monkeypatch):
    """`find_posting` answers by URL from the dict the test fills; `web` serves the lookup."""
    served: dict[str, Page] = {}
    web = FakeWeb(**{LINKEDIN: ok(LINKEDIN, about())})
    monkeypatch.setattr(postings_module, "find_posting", lambda intake, url, *a, **k: LadderResult(
        served.get(url), []))
    monkeypatch.setattr(postings_module, "look_up",
                        partial(look_up, fetch=web, throttle=NoWait()))
    return served, web


def page(url: str, company: str | None = "Acme Solar", company_url: str | None = LINKEDIN):
    supplied = {"title": "Analyst", "location_raw": "Remote"}
    return Page(url, TEXT + url, supplied | ({"company": company} if company else {}),
                company_url)


def test_a_new_posting_gets_its_company_looked_up_once(intake, pages):
    served, web = pages
    served["https://jobs.example/1"] = page("https://jobs.example/1")
    served["https://jobs.example/2"] = page("https://jobs.example/2")
    add_from_url(intake, "https://jobs.example/1")
    add_from_url(intake, "https://jobs.example/2")
    assert web.requests == [LINKEDIN]
    assert load(intake.root).companies[company_id("Acme Solar")].size_class == "51-200"


def test_a_duplicate_url_makes_no_request(intake, pages):
    served, web = pages
    served["https://jobs.example/1"] = page("https://jobs.example/1")
    add_from_url(intake, "https://jobs.example/1")
    web.requests.clear()
    _, _, duplicate_by, _ = add_from_url(intake, "https://jobs.example/1")
    assert duplicate_by == "url"
    assert web.requests == []


def test_an_unknown_company_makes_no_request(intake, pages):
    served, web = pages
    served["https://jobs.example/1"] = page("https://jobs.example/1", company=None)
    _, posting, _, _ = add_from_url(intake, "https://jobs.example/1")
    assert posting.company == "unknown"
    assert web.requests == []


def test_a_failing_lookup_leaves_the_stored_posting_and_the_result_as_before(
        intake, pages, monkeypatch):
    served, _ = pages
    served["https://jobs.example/1"] = page("https://jobs.example/1")
    monkeypatch.setattr(postings_module, "look_up", partial(
        look_up, fetch=FakeWeb(**{LINKEDIN: RuntimeError("boom")}), throttle=NoWait()))
    posting_id, posting, duplicate_by, _ = add_from_url(intake, "https://jobs.example/1")
    assert duplicate_by is None
    assert load(intake.root).postings[posting_id] == posting
    assert not (intake.root / "companies").exists()


def test_adding_a_link_through_the_api_stores_the_posting_and_its_company_record(
        tmp_path, site, monkeypatch):
    """The real route: the endpoint, the fetch ladder on a local page, intake, then the lookup
    of the employer's website (served by a fake, since it would be https://127.0.0.1/)."""
    root = tmp_path / "data"
    write_json(root / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(root / "policy-pack.json", POLICY_PACK)
    harness = Harness(tmp_path, root)
    http = TestClient(create_app(
        Runs(harness.graph, harness.context),
        Intake(root, FakeStructuredModel(FIELDS), ContentGuard(None, {}))),
        raise_server_exceptions=False)
    home = "https://127.0.0.1/"
    web = FakeWeb(**{home: ok(home, organization(foundingDate="2005-04-01",
                                                 numberOfEmployees=40))})
    monkeypatch.setattr(postings_module, "look_up",
                        partial(look_up, fetch=web, throttle=NoWait()))
    response = http.post("/postings", data={"url": f"{site}/static.html"})
    assert response.status_code == 201, response.text
    repository = load(root)
    assert list(repository.postings) == [response.json()["posting_id"]]
    record = repository.companies[company_id("Harbor Freight Analytics GmbH")]
    assert (record.size_class, record.founded, record.source) == ("11-50", 2005, "website")
    assert web.requests == [home]


def test_the_lookup_runs_after_the_posting_is_stored(intake, pages, monkeypatch):
    served, _ = pages
    served["https://jobs.example/1"] = page("https://jobs.example/1")
    seen = []
    monkeypatch.setattr(postings_module, "look_up", lambda root, company, company_url: seen.append(
        (company, company_url, sorted(load(root).postings))))
    posting_id, *_ = add_from_url(intake, "https://jobs.example/1")
    assert seen == [("Acme Solar", LINKEDIN, sorted(["p1", "p2", posting_id]))]
