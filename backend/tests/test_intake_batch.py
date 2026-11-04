import pytest
from conftest import FakeStructuredModel, ToolScriptModel, write_json
from fastapi.testclient import TestClient
from test_intake_duplicates import FIELDS
from test_triage_graph import POLICY_PACK, Harness

from jobadvaisor.api.app import create_app
from jobadvaisor.data.loader import load
from jobadvaisor.intake.postings import Intake
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.triage.runs import Runs


@pytest.fixture
def api(tmp_path):
    root = tmp_path / "data"
    write_json(root / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(root / "policy-pack.json", POLICY_PACK)
    harness = Harness(tmp_path, root)
    http = TestClient(create_app(
        Runs(harness.graph, harness.context),
        Intake(root, FakeStructuredModel(*[FIELDS] * 5), ContentGuard(None, {}),
               loop_model=ToolScriptModel(plan=[]))),  # a dead link ends the loop at once
        raise_server_exceptions=False)
    return http, root


def batch(http, *urls):
    return http.post("/postings/batch", json={"urls": list(urls)})


def test_a_failed_link_does_not_stop_the_others(api, site):
    http, root = api
    response = batch(http, f"{site}/static.html", f"{site}/dead.html", f"{site}/jsonld.html")
    assert response.status_code == 200, response.text
    first, second, third = response.json()["results"]
    assert [first["outcome"], second["outcome"], third["outcome"]] == [
        "stored", "failed", "stored"]
    assert [first["url"], second["url"], third["url"]] == [
        f"{site}/static.html", f"{site}/dead.html", f"{site}/jsonld.html"]
    assert [a["step"] for a in second["attempts"]] == ["plain", "rendered"]
    assert "paste" in second["detail"]
    assert set(load(root).postings) == {first["posting_id"], third["posting_id"]}


def test_a_link_to_a_stored_posting_is_a_duplicate_of_it(api, site):
    http, root = api
    first, again = batch(http, f"{site}/static.html",
                         f"{site}/static.html?utm_source=newsletter").json()["results"]
    assert (first["outcome"], again["outcome"]) == ("stored", "duplicate")
    assert again["posting_id"] == first["posting_id"] and len(load(root).postings) == 1


def test_an_address_that_is_no_http_link_fails_alone(api, site):
    http, root = api
    bad, good = batch(http, "not a url", f"{site}/static.html").json()["results"]
    assert bad["outcome"] == "failed" and "http" in bad["detail"]
    assert good["outcome"] == "stored" and len(load(root).postings) == 1


@pytest.mark.parametrize("body", [{"urls": []}, {"urls": [3]}, {}])
def test_a_submission_without_links_is_invalid(api, body):
    response = api[0].post("/postings/batch", json=body)
    assert response.status_code == 422 and response.json()["error"] == "invalid request"
