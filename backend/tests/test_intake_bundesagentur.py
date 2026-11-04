import base64
import json

import httpx
import pytest
from conftest import FakeStructuredModel

from jobadvaisor.intake.bundesagentur import (
    DETAIL_URL,
    fetch_bundesagentur,
    reference_number,
)
from jobadvaisor.intake.fetch import FetchError, Page
from jobadvaisor.intake.ladder import fetch_posting
from jobadvaisor.intake.postings import Intake, Submission, store_posting
from jobadvaisor.settings import REPOSITORY_ROOT, Settings
from jobadvaisor.tools.guard import ContentGuard

RECORDED = json.loads((REPOSITORY_ROOT / "fixtures/intake/bundesagentur/jobdetail.json")
                      .read_text())
URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/10000-0000000001-S?pos=3"


def client(reply) -> httpx.Client:
    """An HTTP client whose every request gets `reply(request)`; requests are recorded."""
    client.requests = []

    def handle(request):
        client.requests.append(request)
        return reply(request)

    return httpx.Client(transport=httpx.MockTransport(handle))


def test_job_detail_urls_yield_their_reference_number():
    assert reference_number(URL) == "10000-0000000001-S"
    assert reference_number("https://arbeitsagentur.de/jobsuche/jobdetail/12-3") == "12-3"
    assert reference_number("https://www.arbeitsagentur.de/jobsuche/suche?was=x") is None
    assert reference_number("https://arbeitsagentur.de.example.com/jobsuche/jobdetail/1") is None


def test_the_adapter_maps_the_job_detail_fields():
    http = client(lambda request: httpx.Response(200, json=RECORDED))
    page = fetch_bundesagentur(URL, http=http)
    request = client.requests[0]
    assert str(request.url) == DETAIL_URL.format(
        base64.b64encode(b"10000-0000000001-S").decode())
    assert request.headers["X-API-Key"] == "jobboerse-jobsuche"
    assert page.supplied == {"title": "Softwareentwickler Backend (m/w/d)",
                             "company": "Kranich Logistiksysteme GmbH",
                             "location_raw": "Kassel; Göttingen"}
    assert page.text == RECORDED["stellenangebotsBeschreibung"] and page.url == URL


@pytest.mark.parametrize("reply", [
    lambda request: httpx.Response(403),
    lambda request: httpx.Response(200, text="<html>not json</html>"),
    lambda request: httpx.Response(200, json=[]),
    lambda request: httpx.Response(200, json={**RECORDED, "stellenangebotsBeschreibung": " "}),
    lambda request: httpx.Response(200, json={**RECORDED, "stellenangebotsBeschreibung": None}),
])
def test_every_failure_kind_raises_a_fetch_error(reply):
    with pytest.raises(FetchError):
        fetch_bundesagentur(URL, http=client(reply))


@pytest.mark.parametrize("error", [httpx.ConnectTimeout("slow"), httpx.ConnectError("down")])
def test_timeouts_and_connection_errors_raise_a_fetch_error(error):
    def fail(request):
        raise error

    with pytest.raises(FetchError):
        fetch_bundesagentur(URL, http=client(fail))


def test_a_failing_adapter_falls_through_to_the_plain_fetch():
    def adapter(url):
        raise FetchError("HTTP 403")

    page = Page(URL, "posting text")
    result = fetch_posting(URL, [], adapter=adapter, plain=lambda url: page, rendered=None)
    assert result.page is page
    assert [(a.step, a.outcome) for a in result.attempts] == [
        ("bundesagentur", "HTTP 403"), ("plain", "ok")]


def test_the_adapter_runs_first_for_job_board_urls_only():
    page = Page(URL, "posting text")
    result = fetch_posting(URL, [], adapter=lambda url: page, plain=None, rendered=None)
    assert result.page is page and [a.step for a in result.attempts] == ["bundesagentur"]
    other = fetch_posting("https://example.test/job", [], adapter=None,
                          plain=lambda url: page, rendered=None)
    assert [a.step for a in other.attempts] == ["plain"]


def test_a_response_without_a_company_gets_it_filled(tmp_path):
    reply = {**RECORDED, "firma": None}
    page = fetch_bundesagentur(URL, http=client(lambda request: httpx.Response(200, json=reply)))
    model = FakeStructuredModel({"company": "Kranich Logistiksysteme GmbH"})
    (tmp_path / "postings").mkdir()
    _, posting = store_posting(Intake(tmp_path, model, ContentGuard(None, {})),
                               Submission(page.text, "url", [URL], page.supplied))
    assert posting.company == "Kranich Logistiksysteme GmbH"
    assert list(model.schemas[0].model_fields) == ["company"]


@pytest.mark.skipif(not Settings().ba_live_test, reason="set BA_LIVE_TEST=1 for the live check")
def test_live_job_detail_interface_still_answers():
    from jobadvaisor.intake.bundesagentur import live_reference_number

    page = fetch_bundesagentur(
        f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{live_reference_number()}")
    assert page.text and {"title", "company", "location_raw"} <= page.supplied.keys()
