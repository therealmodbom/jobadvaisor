import json

import pytest
from conftest import FakeStructuredModel, ToolScriptModel, write_json
from fastapi.testclient import TestClient
from test_triage_graph import POLICY_PACK, Harness, StubClassifier

from jobadvaisor.api.app import create_app
from jobadvaisor.data.loader import load
from jobadvaisor.intake.ladder import DEFAULT_LOGIN_WALL_HOSTS, Attempt
from jobadvaisor.intake.loop import MAX_TOOL_CALLS, run_intake_loop
from jobadvaisor.intake.postings import Intake
from jobadvaisor.tools.guard import WITHHELD, ContentGuard
from jobadvaisor.triage.runs import Runs

WALLED = "https://www.linkedin.com/jobs/view/backend-engineer-at-harbor-freight-analytics-42"


def guard(classifier=None) -> ContentGuard:
    return ContentGuard(classifier, classifier.thresholds if classifier else {})


def loop(model, url=WALLED, attempts=(), classifier=None, walled=("linkedin.com",), **options):
    return run_intake_loop(url, list(attempts), list(walled), model, guard(classifier),
                           **options)


def test_loop_finds_the_posting_at_another_source(site):
    model = ToolScriptModel(plan=[
        ("search_alternative_source", {"query": "Backend Engineer Harbor Freight Analytics"}),
        ("fetch_plain", {"url": f"{site}/static.html"}),
        ("report_posting", {"url": f"{site}/static.html"})])
    result = loop(model, attempts=[Attempt("login_wall", WALLED, "skipped")],
                  search=lambda query: f"Harbor Freight careers: {site}/static.html")
    assert "PostgreSQL and Kafka" in result.page.text and result.page.url == f"{site}/static.html"
    assert [(a.step, a.outcome) for a in result.attempts] == [
        ("login_wall", "skipped"), ("loop:search_alternative_source", "ok"),
        ("loop:fetch_plain", "ok")]
    assert "harbor-freight-analytics" in model.seen_text()
    assert "<results>" in model.seen_text()


def test_without_a_search_provider_the_loop_gets_no_search_tool():
    model = ToolScriptModel()
    loop(model)
    assert "search_alternative_source" not in model.tool_names
    assert {"fetch_plain", "fetch_rendered", "report_posting"} <= set(model.tool_names)


def test_fields_the_user_supplied_reach_the_loop_as_hints():
    model = ToolScriptModel()
    loop(model, url="https://www.linkedin.com/jobs/view/4242", hints={
        "title": "Backend Engineer", "company": "Harbor Freight Analytics GmbH"})
    first_prompt = str(model.seen[0][-1].content)
    assert "<hints>" in first_prompt and "Harbor Freight Analytics GmbH" in first_prompt


def test_all_attempts_failing_lists_every_attempt(site):
    model = ToolScriptModel(plan=[("fetch_plain", {"url": f"{site}/nowhere.html"}),
                                  ("fetch_rendered", {"url": f"{site}/nowhere.html"})])
    result = loop(model, url=f"{site}/dead.html", walled=(),
                  attempts=[Attempt("plain", f"{site}/dead.html", "HTTP 404")])
    assert result.page is None
    assert [(a.step, a.outcome) for a in result.attempts] == [
        ("plain", "HTTP 404"), ("loop:fetch_plain", "HTTP 404"),
        ("loop:fetch_rendered", "HTTP 404")]


def test_a_flagged_page_never_reaches_the_model_and_the_loop_goes_on(site):
    model = ToolScriptModel(plan=[
        ("fetch_plain", {"url": f"{site}/injected.html"}),
        ("report_posting", {"url": f"{site}/injected.html"}),
        ("fetch_plain", {"url": f"{site}/static.html"}),
        ("report_posting", {"url": f"{site}/static.html"})])
    result = loop(model, classifier=StubClassifier())
    assert "INJECT" not in model.seen_text() and WITHHELD in model.seen_text()
    assert result.page.url == f"{site}/static.html"
    assert ("loop:fetch_plain", "withheld by the content guard") in [
        (a.step, a.outcome) for a in result.attempts]


def test_report_of_a_page_never_fetched_is_refused(site):
    model = ToolScriptModel(plan=[("report_posting", {"url": f"{site}/static.html"})])
    assert loop(model).page is None


def test_the_loop_stops_after_the_tool_call_cap(site):
    model = ToolScriptModel(plan=[("fetch_plain", {"url": f"{site}/gone-{n}.html"})
                                  for n in range(MAX_TOOL_CALLS + 3)])
    result = loop(model, walled=())
    assert len([a for a in result.attempts if a.step.startswith("loop:")]) == MAX_TOOL_CALLS


def test_parallel_tool_calls_in_one_turn_respect_the_cap(site):
    model = ToolScriptModel(plan=[[("fetch_plain", {"url": f"{site}/gone-{n}.html"})
                                   for n in range(MAX_TOOL_CALLS + 4)]])
    result = loop(model, walled=())
    assert len([a for a in result.attempts if a.step.startswith("loop:")]) == MAX_TOOL_CALLS


def test_the_model_call_cap_ends_a_model_that_never_stops(site):
    model = ToolScriptModel(plan=[("report_posting", {"url": f"{site}/never-fetched-{n}"})
                                  for n in range(30)])
    assert loop(model, walled=()).page is None
    assert len(model.seen) == MAX_TOOL_CALLS + 3


def test_a_malformed_link_is_an_attempt_and_the_loop_goes_on(site):
    model = ToolScriptModel(plan=[("fetch_plain", {"url": "https://example.test:abc/careers"}),
                                  ("fetch_plain", {"url": f"{site}/static.html"}),
                                  ("report_posting", {"url": f"{site}/static.html"})])
    result = loop(model, walled=())
    assert result.page.url == f"{site}/static.html"
    assert (result.attempts[0].step, result.attempts[0].outcome) == (
        "loop:fetch_plain", "invalid URL")


def test_an_unexpected_fetch_error_is_an_attempt_and_the_loop_goes_on():
    def broken(url):
        raise RuntimeError("driver crashed")

    model = ToolScriptModel(plan=[("fetch_rendered", {"url": "https://example.test/job"})])
    result = loop(model, walled=(), rendered=broken)
    assert [(a.step, a.outcome) for a in result.attempts] == [
        ("loop:fetch_rendered", "fetch failed: RuntimeError")]


class BrokenClassifier:
    name, thresholds = "broken", {"injection": 0.5}

    def classify(self, text):
        raise RuntimeError("classifier down")


def test_a_failing_classifier_withholds_the_page_and_the_loop_goes_on(site):
    model = ToolScriptModel(plan=[("fetch_plain", {"url": f"{site}/static.html"})])
    result = loop(model, walled=(), classifier=BrokenClassifier())
    assert result.page is None and "PostgreSQL" not in model.seen_text()
    assert result.attempts[0].outcome == "screening failed"


def test_a_failing_search_is_an_attempt(site):
    def search(query):
        raise RuntimeError("provider down")

    model = ToolScriptModel(plan=[("search_alternative_source", {"query": "x"})])
    result = loop(model, walled=(), search=search)
    assert [(a.step, a.outcome) for a in result.attempts] == [
        ("loop:search_alternative_source", "search failed")]


def test_the_loop_never_fetches_a_login_walled_host():
    model = ToolScriptModel(plan=[("fetch_rendered", {"url": WALLED})])
    result = loop(model)
    assert [(a.step, a.outcome) for a in result.attempts] == [
        ("loop:fetch_rendered", "login-walled host, not fetched")]


def test_tool_output_is_a_data_block_with_links(site):
    model = ToolScriptModel(plan=[("fetch_plain", {"url": f"{site}/jsonld.html"})])
    loop(model, walled=())
    tool_output = str(model.seen[-1][-1].content)
    assert tool_output.startswith("<page>") and "Own our sensor data warehouse" in tool_output


class Api:
    def __init__(self, tmp_path, root, *plan, classifier=None):
        self.model = ToolScriptModel(plan=list(plan))
        self.fields = FakeStructuredModel({"company": "Harbor Freight Analytics GmbH",
                                           "title": "Backend Engineer",
                                           "location_raw": "Bremen"})
        harness = Harness(tmp_path, root, classifier)
        self.http = TestClient(create_app(
            Runs(harness.graph, harness.context),
            Intake(root, self.fields, guard(classifier), loop_model=self.model)),
            raise_server_exceptions=False)


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "data"
    write_json(root / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(root / "policy-pack.json", POLICY_PACK)
    return root


def test_url_intake_stores_a_json_ld_posting(tmp_path, root, site):
    api = Api(tmp_path, root)
    response = api.http.post("/postings", data={"url": f"{site}/jsonld.html"})
    assert response.status_code == 201, response.text
    posting = load(root).postings[response.json()["posting_id"]]
    assert posting.source_type == "url" and posting.urls == [f"{site}/jsonld.html"]
    assert posting.company == "Lindqvist Instruments AB" and api.fields.prompts == []
    assert response.json()["attempts"] == [
        {"step": "plain", "url": f"{site}/jsonld.html", "outcome": "ok"}]


def test_url_intake_records_the_submitted_and_the_alternative_url(tmp_path, root, site):
    api = Api(tmp_path, root, ("fetch_plain", {"url": f"{site}/static.html"}),
              ("report_posting", {"url": f"{site}/static.html"}))
    response = api.http.post("/postings", data={"url": WALLED})
    assert response.status_code == 201, response.text
    posting = load(root).postings[response.json()["posting_id"]]
    assert posting.urls == [WALLED, f"{site}/static.html"]


def test_failed_url_intake_lists_the_attempts_and_offers_text_or_pdf(tmp_path, root, site):
    api = Api(tmp_path, root)
    response = api.http.post("/postings", data={"url": f"{site}/dead.html"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "posting not found" and "paste" in body["detail"]
    assert [a["step"] for a in body["attempts"]] == ["plain", "rendered"]
    assert not (root / "postings").exists() or not any((root / "postings").iterdir())


@pytest.mark.parametrize("url", ["file:///etc/passwd", "not a url", "ftp://example.test/x"])
def test_only_http_urls_are_accepted(tmp_path, root, url):
    response = Api(tmp_path, root).http.post("/postings", data={"url": url})
    assert response.status_code == 422 and response.json()["error"] == "invalid request"


def test_login_wall_hosts_default_while_the_policy_pack_names_none(tmp_path, root):
    response = Api(tmp_path, root).http.get("/policy-pack/login-wall-hosts")
    assert response.status_code == 200 and response.json() == {"hosts": DEFAULT_LOGIN_WALL_HOSTS}


def test_a_saved_login_wall_host_is_skipped_by_the_next_intake(tmp_path, root, site):
    api = Api(tmp_path, root)
    saved = api.http.put("/policy-pack/login-wall-hosts",
                         json={"hosts": [" LinkedIn.com", "127.0.0.1", "linkedin.com"]})
    assert saved.status_code == 200 and saved.json() == {"hosts": ["linkedin.com", "127.0.0.1"]}
    assert json.loads((root / "policy-pack.json").read_text()) == POLICY_PACK | {
        "login_wall_hosts": ["linkedin.com", "127.0.0.1"]}
    response = api.http.post("/postings", data={"url": f"{site}/jsonld.html"})
    assert response.status_code == 422
    assert response.json()["attempts"] == [
        {"step": "login_wall", "url": f"{site}/jsonld.html", "outcome": "skipped"}]


def test_an_invalid_login_wall_host_is_rejected_and_nothing_written(tmp_path, root):
    before = (root / "policy-pack.json").read_text()
    response = Api(tmp_path, root).http.put("/policy-pack/login-wall-hosts",
                                            json={"hosts": ["xing.com", "https://x.com/jobs"]})
    assert response.status_code == 422 and "https://x.com/jobs" in response.json()["detail"]
    assert (root / "policy-pack.json").read_text() == before
