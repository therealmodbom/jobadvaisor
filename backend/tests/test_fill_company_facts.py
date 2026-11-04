"""The one-off backfill of company facts for postings stored before the lookup existed."""

import pytest
from conftest import POSTING, write_json
from test_company_lookup import LINKEDIN, FakeWeb, NoWait, about, ok

from jobadvaisor.data.fill_company_facts import fill_repository, main
from jobadvaisor.data.loader import load
from jobadvaisor.data.models import company_id
from jobadvaisor.intake.company_facts import Reply
from jobadvaisor.intake.fetch import FetchError, Page

JOB = "https://de.linkedin.com/jobs/view/1"
OTHER_JOB = "https://de.linkedin.com/jobs/view/2"


class JobPages:
    """Serves job pages by URL (a `Page`, or an exception to raise) and records the requests."""

    def __init__(self, **pages):
        self.pages, self.requests = pages, []

    def __call__(self, url: str) -> Page:
        self.requests.append(url)
        page = self.pages.get(url, FetchError("HTTP 404"))
        if isinstance(page, Exception):
            raise page
        return page


def job_page(company_url=LINKEDIN) -> Page:
    return Page(JOB, "text", {}, company_url)


@pytest.fixture
def repository(data_repository):
    """p1: Acme Solar on LinkedIn; p2: the same company again; p3: a pasted text; p4: unknown."""
    posting = {**POSTING, "schema_version": "2", "company": "Acme Solar"}
    write_json(data_repository / "postings/p1.json", {**posting, "source_type": "url",
                                                      "urls": [JOB]})
    write_json(data_repository / "postings/p2.json", {**posting, "source_type": "url",
                                                      "urls": [OTHER_JOB]})
    write_json(data_repository / "postings/p3.json", {**posting, "company": "Pasted GmbH"})
    write_json(data_repository / "postings/p4.json", {**posting, "company": "unknown",
                                                      "source_type": "url", "urls": [JOB]})
    return data_repository


def fill(root, apply, jobs=None, web=None):
    return fill_repository(root, apply, fetch_job_page=jobs or JobPages(),
                           fetch=web or FakeWeb(), throttle=NoWait())


def snapshot(root):
    return {path.name: path.read_bytes() for path in (root / "postings").glob("*.json")}


def test_a_dry_run_lists_the_companies_and_requests_nothing(repository):
    jobs, web = JobPages(**{JOB: job_page()}), FakeWeb()
    before = snapshot(repository)
    report = fill(repository, False, jobs, web)
    assert report.companies == ["Acme Solar"]
    assert jobs.requests == [] and web.requests == []
    assert not (repository / "companies").exists() and snapshot(repository) == before


def test_apply_refetches_the_job_page_once_per_company_and_stores_the_record(repository):
    jobs = JobPages(**{JOB: job_page(), OTHER_JOB: job_page()})
    web = FakeWeb(**{LINKEDIN: ok(LINKEDIN, about())})
    before = snapshot(repository)
    report = fill(repository, True, jobs, web)
    assert jobs.requests == [JOB] and web.requests == [LINKEDIN]
    assert report.stored["Acme Solar"].size_class == "51-200"
    assert load(repository).companies[company_id("Acme Solar")].founded == 2019
    assert snapshot(repository) == before  # no posting file changes


def test_a_rerun_is_a_no_op(repository):
    fill(repository, True, JobPages(**{JOB: job_page()}),
         FakeWeb(**{LINKEDIN: ok(LINKEDIN, about())}))
    jobs, web = JobPages(), FakeWeb()
    report = fill(repository, True, jobs, web)
    assert (report.companies, report.stored, report.missed) == ([], {}, [])
    assert jobs.requests == [] and web.requests == []


def test_a_company_that_could_not_be_looked_up_is_reported_and_retried_next_time(repository):
    report = fill(repository, True, JobPages(), FakeWeb())  # job page gone, no website
    assert report.missed == ["Acme Solar"] and report.stored == {}
    assert not (repository / "companies").exists()
    jobs = JobPages(**{JOB: job_page()})
    assert fill(repository, True, jobs, FakeWeb(**{LINKEDIN: ok(LINKEDIN, about())})).stored


@pytest.fixture
def board_first(data_repository):
    """Acme Solar's first posting sits on a job board, a later one on LinkedIn."""
    posting = {**POSTING, "schema_version": "2", "company": "Acme Solar", "source_type": "url"}
    write_json(data_repository / "postings/p1.json",
               {**posting, "urls": ["https://jobs.board.example/1"]})
    write_json(data_repository / "postings/p2.json", {**posting, "urls": [JOB]})
    write_json(data_repository / "postings/p3.json", {**posting, "urls": [OTHER_JOB]})
    return data_repository


def test_a_later_linkedin_posting_supplies_the_company_link_when_the_first_is_elsewhere(
        board_first):
    jobs = JobPages(**{JOB: job_page()})
    web = FakeWeb(**{LINKEDIN: ok(LINKEDIN, about())})
    report = fill(board_first, True, jobs, web)
    assert jobs.requests == [JOB] and report.stored["Acme Solar"].source == "linkedin"


REFUSED = FetchError("connection failed: ConnectError")  # may pass, so it settles nothing
BOARD = "https://board.example/"
BOARD_FACTS = ok(BOARD, '<script type="application/ld+json">{"@type": "Organization", '
                        '"foundingDate": "2001"}</script>')


def test_the_next_linkedin_posting_is_tried_when_a_job_page_cannot_be_fetched(board_first):
    jobs = JobPages(**{JOB: REFUSED, OTHER_JOB: job_page()})
    web = FakeWeb(**{LINKEDIN: ok(LINKEDIN, about())})
    report = fill(board_first, True, jobs, web)
    assert jobs.requests == [JOB, OTHER_JOB] and report.stored["Acme Solar"].size_class == "51-200"


def test_every_linkedin_posting_is_tried_until_one_gives_the_link(data_repository):
    posting = {**POSTING, "schema_version": "2", "company": "Acme Solar", "source_type": "url"}
    urls = [f"https://de.linkedin.com/jobs/view/{number}" for number in range(1, 7)]
    for number, url in enumerate(urls, 1):
        write_json(data_repository / f"postings/p{number}.json", {**posting, "urls": [url]})
    jobs = JobPages(**{url: REFUSED for url in urls[:-1]}, **{urls[-1]: job_page()})
    report = fill(data_repository, True, jobs, FakeWeb(**{LINKEDIN: ok(LINKEDIN, about())}))
    assert jobs.requests == urls and report.stored["Acme Solar"].source == "linkedin"


def test_a_company_whose_job_pages_all_failed_is_missed_and_gets_no_website_record(board_first):
    web = FakeWeb(**{BOARD: BOARD_FACTS})
    report = fill(board_first, True, JobPages(**{JOB: REFUSED, OTHER_JOB: REFUSED}), web)
    assert report.missed == ["Acme Solar"] and web.requests == []
    assert not (board_first / "companies").exists()  # a rerun can still find the LinkedIn facts


def test_job_pages_that_are_gone_or_name_no_company_fall_back_to_the_website(board_first):
    jobs = JobPages(**{JOB: FetchError("HTTP 404"), OTHER_JOB: job_page(company_url=None)})
    web = FakeWeb(**{BOARD: BOARD_FACTS})
    report = fill(board_first, True, jobs, web)
    assert jobs.requests == [JOB, OTHER_JOB] and web.requests == [BOARD]
    assert (report.stored["Acme Solar"].source, report.stored["Acme Solar"].founded) == (
        "website", 2001)


def test_a_blocked_company_page_stores_nothing_and_is_reported(repository):
    report = fill(repository, True, JobPages(**{JOB: job_page()}),
                  FakeWeb(**{LINKEDIN: Reply(429, LINKEDIN, "")}))
    assert report.missed == ["Acme Solar"] and report.stored == {}
    assert not (repository / "companies").exists()


def test_a_posting_without_a_linkedin_page_goes_straight_to_the_website(data_repository):
    write_json(data_repository / "postings/p1.json", {
        **POSTING, "schema_version": "2", "company": "Acme Solar", "source_type": "url",
        "urls": ["https://jobs.acme-solar.example/1"]})
    jobs = JobPages()
    web = FakeWeb(**{"https://acme-solar.example/": ok(
        "https://acme-solar.example/",
        '<script type="application/ld+json">{"@type": "Organization", "foundingDate": "2001"}'
        "</script>")})
    report = fill(data_repository, True, jobs, web)
    assert jobs.requests == [] and report.stored["Acme Solar"].founded == 2001


def test_the_job_page_request_is_spaced_like_the_company_requests(repository):
    waited = []

    class Recording:
        def wait(self, host):
            waited.append(host)

    fill_repository(repository, True, fetch_job_page=JobPages(**{JOB: job_page()}),
                    fetch=FakeWeb(**{LINKEDIN: ok(LINKEDIN, about())}), throttle=Recording())
    assert waited == ["de.linkedin.com", "www.linkedin.com"]


def test_the_command_prints_one_line_per_company_and_a_summary(repository, capsys):
    main([str(repository)])
    out = capsys.readouterr().out
    assert "would look up Acme Solar" in out and "1 would look up" in out
    assert not (repository / "companies").exists()


def test_the_command_refuses_a_directory_that_is_no_repository(tmp_path, capsys):
    with pytest.raises(SystemExit):
        main([str(tmp_path / "missing")])
    assert "missing" in capsys.readouterr().err
