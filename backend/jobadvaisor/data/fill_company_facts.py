"""One-off backfill: look up company facts (`company-facts`) for the postings stored before intake
did, fetching each company's first LinkedIn job page again to find its company link (the
LinkedIn cut dropped it).

    python -m jobadvaisor.data.fill_company_facts <data repository>           # dry run
    python -m jobadvaisor.data.fill_company_facts <data repository> --apply   # look up and store

Companies that already have a record are skipped, so a rerun continues where a blocked or
interrupted run stopped. No posting file changes.
"""

import argparse
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from jobadvaisor.data.loader import DataRepositoryError, load
from jobadvaisor.data.models import Company, company_id
from jobadvaisor.intake.company_facts import THROTTLE, Reply, Throttle, fetch_page, look_up
from jobadvaisor.intake.fetch import FetchError, Page, fetch_plain, is_linkedin
from jobadvaisor.intake.ladder import GONE_OUTCOMES
from jobadvaisor.tools.extraction import UNKNOWN


@dataclass
class Report:
    """`companies` are the names without a record that postings from URLs name; of those,
    `stored` holds the record per name a run wrote (`--apply` only) and `missed` the names for
    which nothing was stored (blocked, failed or nothing to ask), which a rerun tries again."""

    companies: list[str] = field(default_factory=list)
    stored: dict[str, Company] = field(default_factory=dict)
    missed: list[str] = field(default_factory=list)


def fill_repository(root: Path, apply: bool, *,
                    fetch_job_page: Callable[[str], Page] = fetch_plain,
                    fetch: Callable[[str], Reply] = fetch_page,
                    throttle: Throttle = THROTTLE) -> Report:
    """Look up the facts of every company named by a stored URL posting and lacking a record
    ("unknown" and pasted or PDF postings excluded). Without `apply` nothing is requested or
    written. With it, the company's LinkedIn job pages (first URL of each posting) are fetched
    in posting-ID order until one gives the company link, then `look_up` runs with the same
    limits as at intake. Job pages that could not be fetched (not just gone) leave the outcome
    open: if none gave a link, the company is reported as missed without asking its website, so
    a rerun can still find the LinkedIn facts; gone pages and pages without a link fall back to
    the website like a company without LinkedIn postings. Raises `DataRepositoryError` for an
    invalid repository."""
    repository = load(root)
    companies: dict[str, tuple[str, list[str]]] = {}  # company ID → (name, job URLs by ID)
    for posting_id in sorted(repository.postings):
        posting = repository.postings[posting_id]
        key = company_id(posting.company)
        if (posting.source_type == "url" and posting.urls and posting.company != UNKNOWN and key
                and key not in repository.companies):
            companies.setdefault(key, (posting.company, []))[1].append(posting.urls[0])
    report = Report(companies=[name for name, _ in companies.values()])
    if not apply:
        return report
    for name, urls in companies.values():
        link, open_pages = None, False
        for url in filter(is_linkedin, urls):
            link, settled = _company_link(url, fetch_job_page, throttle)
            open_pages = open_pages or not settled
            if link:
                break
        record = None if open_pages and not link else look_up(
            root, name, link, fetch=fetch, throttle=throttle)
        if record is None:
            report.missed.append(name)
        else:
            report.stored[name] = record
    return report


def _company_link(url: str, fetch_job_page: Callable[[str], Page], throttle: Throttle
                  ) -> tuple[str | None, bool]:
    """`(company link or None, settled)` for the LinkedIn job page at `url`: settled when the
    page was read or is gone (HTTP 404/410), so a later run would find nothing new; not settled
    for any other failure to fetch it, which may pass."""
    try:
        throttle.wait(urlsplit(url).hostname or "")
        return fetch_job_page(url).company_url, True
    except FetchError as error:
        return None, str(error) in GONE_OUTCOMES
    except OSError:
        return None, False


def main(argv: list[str] | None = None) -> None:
    """Command-line entry: one line per company, then a summary; a dry run unless `--apply`."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repository", type=Path, help="data repository holding postings/")
    parser.add_argument("--apply", action="store_true", help="look the facts up and store them")
    args = parser.parse_args(argv)
    try:
        report = fill_repository(args.repository, args.apply)
    except DataRepositoryError as error:
        parser.exit(1, f"{error}\n")
    if not args.apply:
        for name in report.companies:
            print(f"would look up {name}")
        print(f"{len(report.companies)} would look up")
        return
    for name, record in report.stored.items():
        print(f"stored {name}: size {record.size_class or '-'}, founded {record.founded or '-'} "
              f"({record.source})")
    for name in report.missed:
        print(f"missed {name}: nothing stored, a rerun tries again")
    print(f"{len(report.stored)} stored, {len(report.missed)} missed")


if __name__ == "__main__":
    main()
