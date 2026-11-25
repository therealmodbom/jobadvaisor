import time

import httpx
import pytest
from conftest import FakeStructuredModel, SpacingClock

from jobadvaisor.data.models import ClosedRule, PolicyPack
from jobadvaisor.intake.fetch import (
    CLOSED_REDIRECT,
    CLOSED_TEXT,
    DEFAULT_CLOSED_RULES,
    FetchError,
    closed_by_text,
    download_plain,
    download_rendered,
    fetch_plain,
    fetch_rendered,
    host_throttle,
    page_from_html,
    page_links,
)
from jobadvaisor.intake.fetch import closed_rules as closed_rules_in_force
from jobadvaisor.intake.ladder import (
    DEFAULT_LOGIN_WALL_HOSTS,
    closed_rules,
    fetch_posting,
    gone_disputed,
    is_gone,
    login_wall_hosts,
)
from jobadvaisor.intake.postings import Intake, Submission, store_posting
from jobadvaisor.tools.guard import ContentGuard


def test_plain_fetch_reads_json_ld_job_posting(site):
    page = fetch_plain(f"{site}/jsonld.html")
    assert page.supplied == {"title": "Senior Data Engineer",
                             "company": "Lindqvist Instruments AB",
                             "location_raw": "Uppsala, SE; Hamburg, DE"}
    assert "Own our sensor data warehouse" in page.text and "<li>" not in page.text
    assert "Products" not in page.text


def test_a_short_json_ld_description_gives_way_to_the_longer_page_text():
    body = "<main><p>" + "Responsibilities include building data pipelines. " * 20 + "</p></main>"
    html = ('<script type="application/ld+json">{"@type": "JobPosting", "title": "Analyst", '
            '"description": "A short teaser of the role…"}</script>' + body)
    page = page_from_html("https://example.test/job", html)
    assert page.text.startswith("Responsibilities") and page.supplied == {"title": "Analyst"}


BODY = "<p>" + "You build data pipelines in Python and SQL for our sensor fleet. " * 14 + "</p>"


@pytest.mark.parametrize("html", [
    f"<html><body><form id='aspnet'>{BODY}</form></body></html>",
    f"<html><head><title>Job</title><body>{BODY}</body></html>",
    f"<header><nav>Home</header><main>{BODY}</main>",
])
def test_text_survives_forms_and_unclosed_tags(html):
    assert "sensor fleet" in page_from_html("https://example.test/job", html).text


def test_form_controls_are_not_posting_text():
    controls = ("<label>Location filter</label><select><option>Every country</option></select>"
                "<button>Apply now</button><textarea>Cover letter</textarea>")
    text = page_from_html("https://example.test/job", f"<form>{BODY}{controls}</form>").text
    assert "sensor fleet" in text
    for control in ("Location filter", "Every country", "Apply now", "Cover letter"):
        assert control not in text


@pytest.mark.parametrize("banner", [
    '<div id="cookie-banner"><p>We and our 120 partners store data.</p><br><img src="x"></div>',
    '<form data-cookieman-dnt-enabled><p>We and our 120 partners store data.</p></form>',
    '<section class="cmp-consent"><p>We and our 120 partners store data.</p></section>',
])
def test_cookie_consent_dialogs_are_not_posting_text(banner):
    text = page_from_html("https://example.test/job", f"{banner}<main>{BODY}</main>").text
    assert "sensor fleet" in text and "partners" not in text


def test_links_keep_hash_routes_but_drop_plain_anchors():
    html = ('<a href="#/jobs/1">Job one</a><a href="#!/jobs/2">Job two</a>'
            '<a href="/careers#apply">Apply</a><a href="/careers">Careers</a>')
    assert page_links("https://example.test/", html) == [
        ("Job one", "https://example.test/#/jobs/1"),
        ("Job two", "https://example.test/#!/jobs/2"),
        ("Apply", "https://example.test/careers")]


def test_a_page_under_the_minimum_text_is_no_posting():
    html = "<main><p>" + "Visit our applicant portal. " * 20 + "</p></main>"  # 560 characters
    with pytest.raises(FetchError, match="no posting text"):
        page_from_html("https://example.test/job", html)


def test_json_ld_in_a_graph_without_company_supplies_title_and_remote(site):
    page = fetch_plain(f"{site}/jsonld-no-company.html")
    assert page.supplied == {"title": "Frontend Developer", "location_raw": "Remote"}


def test_plain_fetch_of_a_static_page_extracts_the_main_text(site):
    page = fetch_plain(f"{site}/static.html")
    assert page.supplied == {}
    assert "PostgreSQL and Kafka" in page.text and "Go or a willingness" in page.text
    for noise in ("tracking code", "font-family", "About us", "Imprint"):
        assert noise not in page.text


def test_plain_fetch_of_a_script_rendered_page_yields_no_posting_text(site):
    with pytest.raises(FetchError, match="no posting text"):
        fetch_plain(f"{site}/rendered.html")


def test_rendered_fetch_captures_text_that_scripts_add(site):
    page = fetch_rendered(f"{site}/rendered.html")
    assert "anomalous blood test results" in page.text


def test_ladder_falls_through_to_the_browser_for_a_script_rendered_page(site):
    result = fetch_posting(f"{site}/rendered.html", [])
    assert "PyTorch" in result.page.text
    assert [(a.step, a.outcome) for a in result.attempts] == [
        ("plain", "no posting text"), ("rendered", "ok")]


def test_ladder_stops_at_the_first_step_with_posting_text(site):
    result = fetch_posting(f"{site}/static.html", [])
    assert [a.step for a in result.attempts] == ["plain"]


@pytest.mark.parametrize("url", ["https://www.xing.com/jobs/1", "https://xing.com/x",
                                 "https://de.xing.com/jobs/a-1"])
def test_a_login_walled_host_is_never_fetched(url):
    def never(url):
        raise AssertionError(f"fetched {url}")

    result = fetch_posting(url, DEFAULT_LOGIN_WALL_HOSTS, plain=never, rendered=never)
    assert result.page is None
    assert [(a.step, a.outcome) for a in result.attempts] == [("login_wall", "skipped")]


def test_a_host_that_only_ends_like_a_listed_one_is_fetched():
    calls = []
    fetch_posting("https://notlinkedin.com/job", DEFAULT_LOGIN_WALL_HOSTS,
                  plain=lambda url: calls.append(url) or page_from_html(url, "<p>" + "x " * 200),
                  rendered=None)
    assert calls == ["https://notlinkedin.com/job"]


def test_linkedin_guest_pages_are_fetched_by_default():
    calls = []
    fetch_posting("https://www.linkedin.com/jobs/view/1", DEFAULT_LOGIN_WALL_HOSTS,
                  plain=lambda url: calls.append(url) or page_from_html(url, "<p>" + "x " * 400),
                  rendered=None)
    assert calls == ["https://www.linkedin.com/jobs/view/1"]


def test_login_wall_hosts_default_to_xing_unless_configured():
    pack = PolicyPack(schema_version="1")
    assert login_wall_hosts(pack) == ["xing.com"]
    assert login_wall_hosts(pack.model_copy(update={"login_wall_hosts": []})) == []


def test_plain_fetch_retries_once_after_a_server_error():
    replies = iter([httpx.Response(503), httpx.Response(200, text="<p>" + "word " * 200)])
    http = httpx.Client(transport=httpx.MockTransport(lambda request: next(replies)))
    assert fetch_plain("https://example.test/job", http=http).text.startswith("word")


@pytest.mark.parametrize("reply", [httpx.Response(404), httpx.Response(503)])
def test_plain_fetch_reports_a_failing_status(reply):
    http = httpx.Client(transport=httpx.MockTransport(lambda request: reply))
    with pytest.raises(FetchError, match=f"HTTP {reply.status_code}"):
        fetch_plain("https://example.test/job", http=http)


def test_json_ld_page_without_company_gets_the_company_filled(site, tmp_path):
    page = fetch_plain(f"{site}/jsonld-no-company.html")
    model = FakeStructuredModel({"company": "Orchard Lane Software GmbH"})
    (tmp_path / "postings").mkdir()
    _, posting = store_posting(Intake(tmp_path, model, ContentGuard(None, {})),
                               Submission(page.text, "url", [page.url], page.supplied))
    assert (posting.title, posting.company, posting.location_raw) == (
        "Frontend Developer", "Orchard Lane Software GmbH", "Remote")
    assert list(model.schemas[0].model_fields) == ["company"]


@pytest.mark.parametrize("url", ["file:///etc/hosts", "chrome://settings", "ftp://x.example/a"])
def test_non_http_urls_are_never_fetched(url):
    for download in (download_plain, download_rendered):
        with pytest.raises(FetchError, match="invalid URL"):
            download(url)
    result = fetch_posting(url, [])
    assert result.page is None
    assert [attempt.outcome for attempt in result.attempts] == ["invalid URL", "invalid URL"]


LINKEDIN_URL = "https://de.linkedin.com/jobs/view/1"
LINKEDIN_CHROME = ["Skip to main content", "Sign in", "Join now", "Forgot password",
                   "Report this job", "Referrals increase", "Similar jobs", "Network Administrator",
                   "Sign in to create job alert", "Agree & Join LinkedIn", "Show more",
                   "Platform Engineer (all genders)", "30 applicants"]


@pytest.fixture
def linkedin_guest_html():
    from jobadvaisor.settings import REPOSITORY_ROOT
    return (REPOSITORY_ROOT / "fixtures/intake/pages/linkedin-guest.html").read_text()


def test_a_linkedin_page_keeps_the_description_and_criteria_but_no_chrome(linkedin_guest_html):
    text = page_from_html(LINKEDIN_URL, linkedin_guest_html).text
    assert "Kafka ingestion" in text and "Experience with event streaming" in text
    assert "Seniority level" in text and "Mid-Senior level" in text and "Full-time" in text
    assert [mark for mark in LINKEDIN_CHROME if mark in text] == []


def test_a_linkedin_page_keeps_the_pay_range_the_employer_provides(linkedin_guest_html):
    text = page_from_html(LINKEDIN_URL, linkedin_guest_html).text
    assert "provided pay range" in text and "€70,000.00/yr - €90,000.00/yr" in text
    assert text.index("Base pay range") < text.index("Kafka ingestion")


def test_a_linkedin_page_without_a_pay_range_stores_none():
    html = ('<div class="description__text"><div class="show-more-less-html__markup">'
            'Join our small team.</div></div>')
    assert "pay range" not in page_from_html(LINKEDIN_URL, html).text


def test_a_linkedin_page_with_criteria_but_no_description_falls_back_to_its_visible_text():
    html = (f"<main>{BODY}<ul class='description__job-criteria-list'><li>Seniority level</li>"
            "</ul><h2>Similar jobs</h2></main>")
    page = page_from_html(LINKEDIN_URL, html)
    assert "data pipelines" in page.text and "Similar jobs" in page.text


def test_a_linkedin_page_supplies_title_company_and_location_from_its_header(linkedin_guest_html):
    page = page_from_html(LINKEDIN_URL, linkedin_guest_html)
    assert page.supplied == {"title": "Platform Engineer (all genders)",
                             "company": "Brightwater Analytics", "location_raw": "Berlin, Germany"}


def test_a_short_linkedin_description_is_kept_without_chrome():
    html = ('<h1 class="top-card-layout__title">Analyst</h1>'
            '<div class="description__text"><div class="show-more-less-html__markup">'
            'Join our small team.</div></div>'
            '<h2>Similar jobs</h2><p>Network Administrator</p>')
    page = page_from_html(LINKEDIN_URL, html)
    assert page.text == "Join our small team."
    assert page.supplied == {"title": "Analyst"}


def test_a_linkedin_page_without_a_description_falls_back_to_its_visible_text():
    page = page_from_html(LINKEDIN_URL, f"<main>{BODY}<h2>Similar jobs</h2></main>")
    assert "data pipelines" in page.text and "Similar jobs" in page.text
    assert page.supplied == {}


def test_a_linkedin_page_with_a_json_ld_description_is_read_like_any_other():
    description = "Responsibilities include building data pipelines. " * 20
    html = ('<script type="application/ld+json">{"@type": "JobPosting", "title": "Analyst", '
            f'"description": "{description}"}}</script>'
            '<div class="description__text">Not this one.</div>')
    assert page_from_html(LINKEDIN_URL, html).text == description.strip()


def test_a_linkedin_page_gives_the_company_page_without_query_or_country_host(
        linkedin_guest_html):
    page = page_from_html(LINKEDIN_URL, linkedin_guest_html)
    assert page.company_url == "https://www.linkedin.com/company/brightwater-analytics"


def _linkedin_header(link: str) -> str:
    return (f'<div class="description__text">Join our small team.</div>'
            f'<a class="topcard__org-name-link" {link}>Acme</a>')


@pytest.mark.parametrize("link", [
    "",  # an anchor without href
    'href="https://example.test/company/acme"',  # not a LinkedIn host
    'href="https://notlinkedin.com/company/acme"',  # a host that only ends like LinkedIn
    'href="https://www.linkedin.com/in/someone"',  # not a company page
    'href="https://www.linkedin.com/company/"',  # no company named
    'href="javascript:void(0)"',
])
def test_a_company_link_that_is_no_company_page_gives_none(link):
    assert page_from_html(LINKEDIN_URL, _linkedin_header(link)).company_url is None


def test_a_linkedin_page_without_a_company_link_gives_none():
    html = '<div class="description__text">Join our small team.</div>'
    assert page_from_html(LINKEDIN_URL, html).company_url is None


def test_a_linkedin_page_read_through_its_json_ld_still_gives_the_company_page():
    description = "Responsibilities include building data pipelines. " * 20
    html = ('<script type="application/ld+json">{"@type": "JobPosting", "title": "Analyst", '
            f'"description": "{description}"}}</script>'
            + _linkedin_header('href="https://www.linkedin.com/company/acme?trk=x"'))
    assert page_from_html(LINKEDIN_URL, html).company_url == \
        "https://www.linkedin.com/company/acme"


def test_a_company_link_on_a_page_outside_linkedin_is_ignored(linkedin_guest_html):
    assert page_from_html("https://notlinkedin.com/job", linkedin_guest_html).company_url is None


def test_the_linkedin_cut_applies_to_linkedin_hosts_only(linkedin_guest_html):
    text = page_from_html("https://notlinkedin.com/job", linkedin_guest_html).text
    assert "Similar jobs" in text


JOBS_RULE = ClosedRule(host="jobs.example.com", text_marker="position has been filled")


@pytest.fixture
def jobs_rule():
    """The closed rules of a fetch: the defaults and `JOBS_RULE`."""
    token = closed_rules_in_force.set([*DEFAULT_CLOSED_RULES, JOBS_RULE])
    yield
    closed_rules_in_force.reset(token)


def test_the_default_rules_hold_linkedins_redirect_marker():
    assert DEFAULT_CLOSED_RULES == [
        ClosedRule(host="linkedin.com", redirect_marker="trk=expired_jd_redirect")]
    assert closed_rules_in_force.get() == DEFAULT_CLOSED_RULES


def test_the_policy_packs_closed_rules_add_to_the_defaults():
    pack = PolicyPack(schema_version="1")
    assert closed_rules(pack) == DEFAULT_CLOSED_RULES
    own = pack.model_copy(update={"closed_rules": [JOBS_RULE]})
    assert closed_rules(own) == [*DEFAULT_CLOSED_RULES, JOBS_RULE]
    assert closed_rules(pack.model_copy(update={"closed_rules": []})) == DEFAULT_CLOSED_RULES


@pytest.mark.parametrize(("url", "closed"), [
    ("https://jobs.example.com/job/1", True),
    ("https://careers.jobs.example.com/job/1", True),
    ("https://notjobs.example.com/job/1", False),
    ("https://example.com/job/1", False),
])
def test_a_rule_matches_its_host_and_subdomains(jobs_rule, url, closed):
    assert closed_by_text(url, "<main>The position has been filled.</main>") is closed


def test_a_text_marker_is_compared_without_case(jobs_rule):
    assert closed_by_text("https://jobs.example.com/1", "<p>THE POSITION HAS BEEN FILLED</p>")


def test_a_text_marker_does_not_match_script_style_or_navigation_text(jobs_rule):
    phrase = "position has been filled"
    html = (f"<head><style>.x::after{{content:'{phrase}'}}</style></head>"
            f"<nav>{phrase}</nav><script>var notice = '{phrase}';</script><main>Open role</main>")
    assert closed_by_text("https://jobs.example.com/1", html) is False


def test_a_redirect_rule_never_matches_page_text():
    html = "<p>trk=expired_jd_redirect</p>"
    assert closed_by_text("https://www.linkedin.com/jobs/view/1", html) is False


def page_with(notice: str, body: str = "") -> str:
    return f"<html><body><p>{notice}</p>{body}</body></html>"


def test_a_short_page_with_a_marker_is_closed(jobs_rule):
    with pytest.raises(FetchError) as error:
        page_from_html("https://jobs.example.com/1",
                       page_with("Sorry, the position has been filled."))
    assert str(error.value) == CLOSED_TEXT


def test_a_long_page_with_a_marker_is_a_page_marked_closed(jobs_rule):
    page = page_from_html("https://jobs.example.com/1",
                          page_with("The position has been filled.", BODY))
    assert page.closed and "sensor fleet" in page.text


def test_a_long_page_without_a_marker_is_not_closed(jobs_rule):
    page = page_from_html("https://jobs.example.com/1", page_with("Apply now.", BODY))
    assert page.closed is False


def test_a_short_page_without_a_marker_is_still_no_posting_text(jobs_rule):
    with pytest.raises(FetchError, match="no posting text"):
        page_from_html("https://jobs.example.com/1", page_with("Apply now."))


def test_a_marker_outside_its_host_is_ignored(jobs_rule):
    with pytest.raises(FetchError, match="no posting text"):
        page_from_html("https://other.example.com/1", page_with("The position has been filled."))


def test_plain_download_without_retry_sends_one_request_after_a_429():
    seen = []

    def handle(request):
        seen.append(str(request.url))
        return httpx.Response(429)
    http = httpx.Client(transport=httpx.MockTransport(handle))
    with pytest.raises(FetchError, match="HTTP 429"):
        download_plain("https://example.test/job", http, retry=False)
    assert len(seen) == 1


def test_plain_download_without_retry_sends_one_request_after_a_transport_error():
    seen = []

    def handle(request):
        seen.append(str(request.url))
        raise httpx.ConnectError("down")
    http = httpx.Client(transport=httpx.MockTransport(handle))
    with pytest.raises(FetchError, match="connection failed"):
        download_plain("https://example.test/job", http, retry=False)
    assert len(seen) == 1


def answering(*replies):
    """An `httpx.Client` whose transport answers each request with the next of `replies`: a
    response is returned, an exception is raised."""
    queue = iter(replies)

    def handle(request):
        reply = next(queue)
        if isinstance(reply, Exception):
            raise reply
        return reply
    return httpx.Client(transport=httpx.MockTransport(handle))


def test_a_retried_download_names_the_failure_of_its_first_attempt():
    http = answering(httpx.Response(429), httpx.Response(404))
    with pytest.raises(FetchError) as error:
        download_plain("https://jobs.example.org/job", http)
    assert str(error.value) == "HTTP 404" and error.value.earlier == ("HTTP 429",)


def test_a_retried_download_names_a_transport_failure_of_its_first_attempt():
    http = answering(httpx.ConnectError("down"), httpx.Response(404))
    with pytest.raises(FetchError) as error:
        download_plain("https://jobs.example.org/job", http)
    assert str(error.value) == "HTTP 404"
    assert error.value.earlier == ("connection failed: ConnectError",)


def test_a_refused_hop_of_the_retry_keeps_the_first_failure():
    marker = DEFAULT_CLOSED_RULES[0].redirect_marker

    def handle(request):
        if request.url.path == "/job" and not calls:
            calls.append(1)
            return httpx.Response(429)
        return httpx.Response(302, headers={"location": f"https://www.linkedin.com/x?{marker}"})
    calls = []
    http = httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=True)
    with pytest.raises(FetchError) as error:
        download_plain("https://www.linkedin.com/job", http)
    assert str(error.value) == CLOSED_REDIRECT and error.value.earlier == ("HTTP 429",)


def test_a_download_that_fails_once_and_then_succeeds_returns_the_page():
    http = answering(httpx.Response(503), httpx.Response(200, text="<p>ok</p>"))
    assert download_plain("https://jobs.example.org/job", http)[1] == "<p>ok</p>"


def test_a_download_without_a_retry_has_no_earlier_failures():
    with pytest.raises(FetchError) as error:
        download_plain("https://jobs.example.org/job", answering(httpx.Response(404)))
    assert error.value.earlier == ()


def test_the_ladder_records_the_first_answer_of_a_retried_fetch_and_the_404_stays_disputed():
    url = "https://jobs.example.org/job"
    http = answering(httpx.Response(429), httpx.Response(404))

    def rendered(address):
        raise FetchError("no posting text")
    result = fetch_posting(url, [], plain=lambda address: fetch_plain(address, http),
                           rendered=rendered)
    attempts = [vars(a) for a in result.attempts]
    assert [a["outcome"] for a in attempts] == ["HTTP 429", "HTTP 404", "no posting text"]
    assert [a["step"] for a in attempts] == ["plain", "plain", "rendered"]
    assert not is_gone(attempts, url) and gone_disputed(attempts, url)


# --- spacing in an alert run (`fetch.host_throttle`) ----------------------------------------


@pytest.fixture
def clock():
    """A fake clock and the 3 s throttle on it, set as `host_throttle` for the test."""
    spacing = SpacingClock()
    token = host_throttle.set(spacing.throttle())
    yield spacing
    host_throttle.reset(token)


def test_plain_download_waits_for_its_host_before_every_request_the_retry_included(clock):
    replies = iter([httpx.Response(429), httpx.Response(200, text="<p>ok</p>")])
    http = httpx.Client(transport=httpx.MockTransport(lambda request: next(replies)))
    download_plain("https://jobs.example.org/job", http)
    assert clock.sleeps == [3]  # the retry lies 3 s behind the first request


def redirecting(target: str) -> httpx.Client:
    """A client whose `/start` pages redirect to `target` and everything else answers 200."""
    def handle(request):
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": target})
        return httpx.Response(200, text="<p>ok</p>")
    return httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=True)


def test_a_redirect_hop_on_the_same_host_waits_before_it_is_sent(clock):
    download_plain("https://jobs.example.org/start", redirecting("https://jobs.example.org/job"))
    assert clock.sleeps == [3]


def test_a_redirect_hop_to_another_host_reserves_that_host(clock):
    http = redirecting("https://careers.example.net/job")
    download_plain("https://jobs.example.org/start", http)
    assert clock.sleeps == []  # a hop to a host not used before is due at once
    download_plain("https://careers.example.net/other", http)
    assert clock.sleeps == [3]


def test_a_refused_hop_takes_no_slot(clock):
    marker = DEFAULT_CLOSED_RULES[0].redirect_marker
    http = redirecting(f"https://www.linkedin.com/x?{marker}")
    with pytest.raises(FetchError, match="closed page"):
        download_plain("https://jobs.example.org/start", http)
    download_plain("https://www.linkedin.com/job", http)
    assert clock.sleeps == []


def test_a_redirect_hop_outside_a_run_waits_for_nothing(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda seconds: pytest.fail("slept"))
    download_plain("https://jobs.example.org/start", redirecting("https://jobs.example.org/job"))


def test_plain_downloads_of_two_hosts_do_not_wait_for_each_other(clock):
    http = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    download_plain("https://jobs.example.org/a", http)
    download_plain("https://careers.example.net/b", http)
    assert clock.sleeps == []
    download_plain("https://JOBS.example.org/c", http)
    assert clock.sleeps == [3]


def test_a_download_outside_a_run_waits_for_nothing(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda seconds: pytest.fail("slept"))
    http = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    assert host_throttle.get() is None
    download_plain("https://jobs.example.org/a", http)
    download_plain("https://jobs.example.org/b", http)


def test_a_rendered_download_waits_once_for_its_host_before_the_navigation(clock, monkeypatch):
    from playwright import sync_api

    def no_browser():
        raise sync_api.Error("no browser in this test")
    monkeypatch.setattr(sync_api, "sync_playwright", no_browser)
    for _ in range(2):
        with pytest.raises(FetchError, match="browser failed"):
            download_rendered("https://jobs.example.org/a")
    assert clock.sleeps == [3]  # the first call is due at once, the second waits
