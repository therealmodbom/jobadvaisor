"""Link cleaning for mail links (ADR 0012): the rules' canonical URLs, the allow-list of query
parameters, and the redirect check."""

import pytest

from jobadvaisor.intake.alert_mail import clean_link
from jobadvaisor.intake.links import linkedin_job_id, navigation_allowed, strip_query

LINKEDIN = ("https://www.linkedin.com/comm/jobs/view/4100000101/?trackingId=TOKEN-21"
            "&refId=TOKEN-22&lipi=TOKEN-1&midToken=TOKEN-2&otpToken=TOKEN-7")


def test_linkedin_tracking_link_becomes_the_job_page():
    assert clean_link(LINKEDIN) == "https://www.linkedin.com/jobs/view/4100000101"


def test_bundesagentur_link_loses_its_search():
    url = "https://www.arbeitsagentur.de/jobsuche/jobdetail/10000-1000000001-S?was=TOKEN-2&wo=TOKEN-3"
    assert clean_link(url) == "https://www.arbeitsagentur.de/jobsuche/jobdetail/10000-1000000001-S"


def test_career_site_link_keeps_scheme_host_and_path():
    url = ("http://careers.example.com/job/Musterstadt-Java-Entwickler-%28wmd%29/2000000006/"
           "?from=TOKEN-1&refid=TOKEN-2&eid=TOKEN-5")
    assert clean_link(url) == \
        "http://careers.example.com/job/Musterstadt-Java-Entwickler-%28wmd%29/2000000006/"


def test_other_link_keeps_only_posting_parameters():
    url = "https://jobs.example.net/detail?jobId=700001&sessionToken=TOKEN-1&utm_source=alert"
    assert clean_link(url) == "https://jobs.example.net/detail?jobId=700001"


def test_hash_route_is_kept_and_a_token_fragment_dropped():
    assert strip_query("https://app.example.com/#/job/1") == "https://app.example.com/#/job/1"
    assert strip_query("https://app.example.com/job/1#access_token=TOKEN-1") == \
        "https://app.example.com/job/1"
    assert strip_query("https://app.example.com/#/job/1?token=TOKEN-1") == \
        "https://app.example.com/"


@pytest.mark.parametrize("url", [
    LINKEDIN, "https://jobs.example.net/detail?jobId=700001&sessionToken=TOKEN-1",
    "http://careers.example.com/job/A-%28wmd%29/2000000006/?refid=TOKEN-2",
    "https://app.example.com/#/job/1"])
def test_cleaning_is_idempotent(url):
    assert clean_link(clean_link(url)) == clean_link(url)


def test_clean_address_keeps_every_byte():
    url = "https://jobs.example.org/job/Ingenieur-in-%28wmd%29/9104-de_DE/?jobId=7%2B1&ID=2"
    assert strip_query(url) == url


@pytest.mark.parametrize(("url", "allowed"), [
    ("https://jobs.example.org/job/A/9104-de_DE", True),
    ("https://jobs.example.org/job/A/9104-de_DE/", True),
    ("https://jobs.example.org/job/A/9104-de_DE/?sid=TOKEN-1", False),
    ("https://www.linkedin.com/jobs/view/4100000101/", True),
    ("https://www.linkedin.com/jobs/view/4100000101/?otpToken=TOKEN-7", False),
])
def test_navigation_allowed(url, allowed):
    assert navigation_allowed(url) is allowed


@pytest.mark.parametrize(("url", "job_id"), [
    ("https://www.linkedin.com/jobs/view/4100000101", "4100000101"),
    ("https://de.linkedin.com/comm/jobs/view/4100000101/?otpToken=TOKEN-7", "4100000101"),
    ("https://www.linkedin.com/jobs/view/teamleitung-backend-at-papierwerk-4100000103/",
     "4100000103"),
    ("https://www.linkedin.com/jobs/search/?currentJobId=4100000104&keywords=TOKEN-1",
     "4100000104"),
    ("https://www.linkedin.com/company/example-group", None),
    ("https://www.linkedin.com/comm/jobs/search-results/?keywords=TOKEN-14", None),
    ("https://jobs.example.com/jobs/view/4100000101", None),
])
def test_linkedin_job_id(url, job_id):
    assert linkedin_job_id(url) == job_id
