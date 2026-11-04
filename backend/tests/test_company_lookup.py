"""The company lookup: sources and their order, what a completed or incomplete lookup stores, and
the request limits (`company-facts` spec). A fake fetcher stands in for the network."""

import json
from datetime import UTC, datetime

import httpx
import pytest
from conftest import POSTING, write_json

from jobadvaisor.data.loader import load
from jobadvaisor.data.models import company_id
from jobadvaisor.intake.company_facts import Reply, Throttle, fetch_page, look_up
from jobadvaisor.tools.research import employer_website

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
LINKEDIN = "https://www.linkedin.com/company/acme-solar"
WEBSITE = "https://acme-solar.example/"


def about(size="51-200 employees", founded="2019") -> str:
    return (f'<div data-test-id="about-us__size"><dt>Company size</dt><dd>{size}</dd></div>'
            f'<div data-test-id="about-us__foundedOn"><dt>Founded</dt><dd>{founded}</dd></div>')


def organization(**fields) -> str:
    return ('<script type="application/ld+json">'
            + json.dumps({"@type": "Organization", **fields}) + "</script>")


class FakeWeb:
    """Answers by URL with a `Reply`, an exception to raise, or a 404; records every request."""

    def __init__(self, **answers):
        self.answers = {url: answer for url, answer in answers.items()}
        self.requests: list[str] = []

    def __call__(self, url: str) -> Reply:
        self.requests.append(url)
        answer = self.answers.get(url, Reply(404, url, ""))
        if isinstance(answer, Exception):
            raise answer
        return answer


def ok(url: str, html: str) -> Reply:
    return Reply(200, url, html)


class FakeClock:
    def __init__(self):
        self.now, self.slept = 100.0, []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class NoWait:
    def wait(self, host: str) -> None:
        pass


@pytest.fixture
def repository(data_repository):
    """A repository whose only posting of Acme Solar sits on the employer's own career site."""
    write_json(data_repository / "postings/p1.json", {
        **POSTING, "company": "Acme Solar", "source_type": "url",
        "urls": ["https://jobs.acme-solar.example/1"]})
    return data_repository


def run(root, web, company="Acme Solar", company_url=LINKEDIN):
    return look_up(root, company, company_url, fetch=web, throttle=NoWait(), now=NOW)


def test_the_website_guess_is_the_researchs_own(repository):
    assert employer_website(load(repository), ["p1"]) == WEBSITE


def test_linkedin_with_both_facts_is_enough(repository):
    web = FakeWeb(**{LINKEDIN: ok(LINKEDIN, about())})
    record = run(repository, web)
    assert (record.size_class, record.founded, record.source) == ("51-200", 2019, "linkedin")
    assert (record.name, record.source_url, record.fetched_at) == ("Acme Solar", LINKEDIN, NOW)
    assert web.requests == [LINKEDIN]


def test_the_record_is_stored_and_loads(repository):
    run(repository, FakeWeb(**{LINKEDIN: ok(LINKEDIN, about())}))
    assert load(repository).companies[company_id("Acme Solar")].size_class == "51-200"


def test_linkedin_with_only_a_size_does_not_ask_the_website(repository):
    web = FakeWeb(**{LINKEDIN: ok(LINKEDIN, about(founded=""))})
    record = run(repository, web)
    assert (record.size_class, record.founded, record.source) == ("51-200", None, "linkedin")
    assert web.requests == [LINKEDIN]


def test_the_website_is_asked_when_linkedin_gave_no_facts(repository):
    web = FakeWeb(**{LINKEDIN: ok(LINKEDIN, "<p>nothing</p>"),
                     WEBSITE: ok(WEBSITE, organization(foundingDate="2012", numberOfEmployees=40))})
    record = run(repository, web)
    assert (record.size_class, record.founded) == ("11-50", 2012)
    assert (record.source, record.source_url) == ("website", WEBSITE)
    assert web.requests == [LINKEDIN, WEBSITE]


def test_a_gone_linkedin_page_gives_way_to_the_website(repository):
    web = FakeWeb(**{LINKEDIN: Reply(404, LINKEDIN, ""),
                     WEBSITE: ok(WEBSITE, organization(foundingDate="2012"))})
    assert run(repository, web).source == "website"


@pytest.mark.parametrize("status", [404, 410])
def test_a_gone_page_everywhere_stores_a_record_without_facts(repository, status):
    web = FakeWeb(**{LINKEDIN: Reply(status, LINKEDIN, ""), WEBSITE: Reply(status, WEBSITE, "")})
    record = run(repository, web)
    assert (record.size_class, record.founded, record.source) == (None, None, "website")
    assert load(repository).companies[company_id("Acme Solar")].size_class is None


def test_pages_read_without_facts_store_a_record_without_facts(repository):
    web = FakeWeb(**{LINKEDIN: ok(LINKEDIN, "<p>x</p>"), WEBSITE: ok(WEBSITE, "<p>y</p>")})
    record = run(repository, web)
    assert (record.size_class, record.founded) == (None, None)
    assert web.requests == [LINKEDIN, WEBSITE]


def test_without_a_linkedin_link_only_the_website_is_asked(repository):
    web = FakeWeb(**{WEBSITE: ok(WEBSITE, organization(foundingDate="2001"))})
    record = run(repository, web, company_url=None)
    assert (record.founded, record.source) == (2001, "website")
    assert web.requests == [WEBSITE]


def test_without_a_source_nothing_is_requested_and_nothing_stored(repository):
    write_json(repository / "postings/p1.json", {**POSTING, "company": "Acme Solar"})
    web = FakeWeb()
    assert run(repository, web, company_url=None) is None
    assert web.requests == []
    assert not (repository / "companies").exists()


@pytest.mark.parametrize("answer", [
    Reply(429, LINKEDIN, ""), Reply(500, LINKEDIN, ""), Reply(503, LINKEDIN, ""),
    Reply(999, LINKEDIN, ""), Reply(403, LINKEDIN, ""),
    httpx.ConnectError("refused"), httpx.ReadTimeout("slow"),
    Reply(200, "https://www.linkedin.com/authwall?trk=x", about()),  # redirected to a login wall
    Reply(200, "https://www.linkedin.com/uas/login", about()),
])
def test_a_blocked_or_failing_linkedin_page_ends_the_lookup_and_stores_nothing(
        repository, answer):
    web = FakeWeb(**{LINKEDIN: answer, WEBSITE: ok(WEBSITE, organization(foundingDate="2001"))})
    assert run(repository, web) is None
    assert web.requests == [LINKEDIN]
    assert not (repository / "companies").exists()


def test_a_failing_website_after_linkedin_without_facts_stores_nothing(repository):
    web = FakeWeb(**{LINKEDIN: ok(LINKEDIN, "<p>x</p>"), WEBSITE: Reply(500, WEBSITE, "")})
    assert run(repository, web) is None
    assert not (repository / "companies").exists()


def test_an_unexpected_error_never_escapes_the_lookup(repository):
    assert run(repository, FakeWeb(**{LINKEDIN: RuntimeError("boom")})) is None


def test_a_company_with_a_record_is_not_looked_up_again(repository):
    run(repository, FakeWeb(**{LINKEDIN: ok(LINKEDIN, about())}))
    web = FakeWeb(**{LINKEDIN: ok(LINKEDIN, about("11-50 employees"))})
    assert run(repository, web) is None
    assert web.requests == []
    assert load(repository).companies[company_id("Acme Solar")].size_class == "51-200"


def test_a_record_without_facts_also_stops_a_second_lookup(repository):
    run(repository, FakeWeb(**{LINKEDIN: ok(LINKEDIN, "<p>x</p>"), WEBSITE: Reply(404, "", "")}))
    web = FakeWeb()
    assert run(repository, web) is None
    assert web.requests == []


def test_two_employers_whose_names_slug_alike_each_get_their_own_record(repository):
    run(repository, FakeWeb(**{LINKEDIN: ok(LINKEDIN, about())}), company="Acme+Solar")
    web = FakeWeb(**{LINKEDIN: ok(LINKEDIN, about("11-50 employees"))})
    record = run(repository, web, company="Acme Solar")
    assert record.size_class == "11-50" and web.requests == [LINKEDIN]
    companies = load(repository).companies
    assert {c.name: c.size_class for c in companies.values()} == {
        "Acme+Solar": "51-200", "Acme Solar": "11-50"}
    assert load(repository).company_of(load(repository).postings["p1"]).size_class == "11-50"


@pytest.mark.parametrize("company", ["unknown", "", "   ", "!!!"])
def test_a_company_without_a_usable_name_is_not_looked_up(repository, company):
    web = FakeWeb(**{LINKEDIN: ok(LINKEDIN, about())})
    assert run(repository, web, company=company) is None
    assert web.requests == []


def test_requests_to_one_host_are_spaced():
    clock = FakeClock()
    throttle = Throttle(2.0, clock=clock.time, sleep=clock.sleep)
    throttle.wait("www.linkedin.com")
    clock.now += 0.5
    throttle.wait("www.linkedin.com")
    throttle.wait("acme-solar.example")  # another host is not held back
    assert clock.slept == [pytest.approx(1.5)]


def test_the_lookup_waits_for_each_host_before_its_request(repository):
    waited = []

    class Recording:
        def wait(self, host):
            waited.append(host)

    web = FakeWeb(**{LINKEDIN: ok(LINKEDIN, "<p>x</p>"), WEBSITE: ok(WEBSITE, "<p>y</p>")})
    look_up(repository, "Acme Solar", LINKEDIN, fetch=web, throttle=Recording(), now=NOW)
    assert waited == ["www.linkedin.com", "acme-solar.example"]


def test_fetch_page_reports_status_final_url_and_text():
    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "https://x.example/end"})
        return httpx.Response(200, text="<p>done</p>")

    http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    assert fetch_page("https://x.example/start", http) == Reply(
        200, "https://x.example/end", "<p>done</p>")


def test_fetch_page_gives_an_error_status_as_a_reply_and_a_transport_error_as_an_exception():
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429)))
    assert fetch_page("https://x.example/", http).status == 429

    def refuse(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(httpx.ConnectError):
        fetch_page("https://x.example/", httpx.Client(transport=httpx.MockTransport(refuse)))


def test_fetch_page_never_fetches_a_non_http_address():
    with pytest.raises(Exception, match="invalid URL"):
        fetch_page("file:///etc/passwd")
