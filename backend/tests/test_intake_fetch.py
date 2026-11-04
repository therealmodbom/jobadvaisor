import httpx
import pytest
from conftest import FakeStructuredModel

from jobadvaisor.data.models import PolicyPack
from jobadvaisor.intake.fetch import (
    FetchError,
    download_plain,
    download_rendered,
    fetch_plain,
    fetch_rendered,
    page_from_html,
    page_links,
)
from jobadvaisor.intake.ladder import DEFAULT_LOGIN_WALL_HOSTS, fetch_posting, login_wall_hosts
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
