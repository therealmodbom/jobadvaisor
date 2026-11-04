import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from conftest import FakeStructuredModel, write_json
from fastapi.testclient import TestClient
from test_triage_graph import POLICY_PACK, Harness

from jobadvaisor.api.app import create_app
from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import load
from jobadvaisor.data.models import Posting
from jobadvaisor.data.writer import create_posting
from jobadvaisor.intake.duplicates import (
    CONTAINMENT_THRESHOLD,
    containment,
    duplicate_of,
    normalize_url,
    shingles,
    text_hash,
)
from jobadvaisor.intake.postings import Intake, Submission, add_submission, posting_urls
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.triage.runs import Runs

SENTENCES = [
    "Harbor Freight Analytics GmbH tracks container shipments across European ports",
    "We sell forecasts of arrival times and port congestion to logistics companies",
    "As a backend engineer you design and run the Go services behind our forecasting API",
    "You work with PostgreSQL, Kafka and Kubernetes on a platform that handles a few "
    "thousand events per second",
    "You share on-call duty with four colleagues and get a day off after every on-call week",
    "You review code, write design notes and mentor a working student",
    "We expect three or more years of backend development in a typed language",
    "Experience with Go is welcome but not required, since we help you switch",
    "Our office is in Bremen near the main station, and we work hybrid with two office days",
    "We offer thirty days of vacation, a learning budget and a public transport ticket",
    "Apply with a CV and a few lines about a system you are proud of",
    "Our hiring process has a short call, a take-home task and a conversation with the team",
]
TEXT = ". ".join(SENTENCES) + "."
OTHER = ". ".join(SENTENCES[:2] + [  # same company boilerplate, another role
    "As a data analyst you build the dashboards our customers use to plan berth slots",
    "You model delays from vessel positions and weather data in Python and SQL",
    "You present findings to customers together with our account managers",
    "You keep our metric definitions consistent across reports and the API",
    "We expect a degree in statistics, economics or a related field",
    "Experience with dbt and a BI tool such as Metabase is a plus",
    "Our office is in Bremen near the main station, and we work hybrid with two office days",
] + SENTENCES[9:]) + "."
FIELDS = {"title": "Backend Engineer", "company": "Harbor Freight Analytics GmbH",
          "location_raw": "Bremen"}


def posting(text: str) -> Posting:
    return Posting(schema_version="1", text=text, source_type="text", added_at=datetime.now(UTC),
                   **FIELDS)


class SlowClassifier:
    """A clean verdict after a pause, so concurrent submissions overlap."""

    name, thresholds = "slow", {"injection": 0.5}

    def classify(self, text):
        time.sleep(0.2)
        return {"injection": 0.0}


def test_concurrent_identical_submissions_store_one_posting(tmp_path):
    (tmp_path / "postings").mkdir()
    write_json(tmp_path / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(tmp_path / "policy-pack.json", POLICY_PACK)
    intake = Intake(tmp_path, FakeStructuredModel(), ContentGuard(SlowClassifier(),
                                                                  SlowClassifier.thresholds))
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: add_submission(
            intake, Submission(TEXT, "text", supplied=FIELDS)), range(4)))
    assert len({posting_id for posting_id, _, _ in results}) == 1
    assert len(list((tmp_path / "postings").glob("*.json"))) == 1


def test_concurrent_postings_with_one_name_get_distinct_files(tmp_path):
    texts = [f"{TEXT} Variant {n}." for n in range(8)]
    with ThreadPoolExecutor(8) as pool:
        ids = list(pool.map(lambda text: create_posting(tmp_path, "20261011-acme-engineer",
                                                        posting(text)), texts))
    assert len(set(ids)) == 8
    for posting_id, text in zip(ids, texts, strict=True):
        assert load_text(tmp_path, posting_id) == text


def load_text(root, posting_id) -> str:
    return json.loads((root / "postings" / f"{posting_id}.json").read_text())["text"]


@pytest.mark.parametrize("variant", [
    "https://www.example.test/jobs/42/",
    "HTTPS://Example.test/jobs/42?utm_source=mail&utm_medium=x#apply",
    "https://example.test/jobs/42?gclid=abc&trk=feed",
])
def test_url_variants_normalize_to_the_same_key(variant):
    assert normalize_url(variant) == normalize_url("https://example.test/jobs/42")


def test_hash_routes_are_part_of_the_url_key():
    assert normalize_url("https://example.test/#/jobs/1") != normalize_url(
        "https://example.test/#/jobs/2")
    assert normalize_url("https://example.test/#!/jobs/1") != normalize_url(
        "https://example.test/#!/jobs/2")


def test_a_short_posting_contained_in_a_longer_different_one_is_no_duplicate():
    short = ". ".join(SENTENCES[:2] + ["We are hiring a backend engineer"] + SENTENCES[9:]) + "."
    assert duplicate_of({"other": posting(OTHER)}, text=short) is None


def test_a_redirect_target_is_stored_after_the_submitted_url():
    assert posting_urls("https://lnk.example/x", "https://example.test/jobs/42") == [
        "https://lnk.example/x", "https://example.test/jobs/42"]


def test_the_page_url_is_not_stored_twice_under_another_spelling():
    assert posting_urls("https://example.test/jobs/42/",
                        "https://www.example.test/jobs/42?utm_source=a") == [
        "https://example.test/jobs/42/"]


def test_identity_bearing_query_parameters_are_kept():
    assert normalize_url("https://example.test/job?gh_jid=1") != normalize_url(
        "https://example.test/job?gh_jid=2")
    assert normalize_url("https://example.test/job?b=2&a=1") == normalize_url(
        "https://example.test/job?a=1&b=2")


def test_job_board_detail_urls_normalize_to_their_reference_number():
    assert normalize_url("https://www.arbeitsagentur.de/jobsuche/jobdetail/12-3-S?pos=4") == \
        normalize_url("https://arbeitsagentur.de/jobsuche/jobdetail/12-3-S")


def test_text_hash_ignores_case_and_whitespace():
    assert text_hash("Go  services\n\nBremen ") == text_hash("go services bremen")
    assert text_hash("Go services") != text_hash("Rust services")


def test_distinct_demo_postings_stay_below_the_threshold():
    sets = [shingles(posting.text) for posting in load(FIXTURE_DIRECTORY).postings.values()]
    nearest = max(containment(a, b) for i, a in enumerate(sets) for b in sets[i + 1:])
    assert nearest < CONTAINMENT_THRESHOLD


class Api:
    def __init__(self, tmp_path, root):
        harness = Harness(tmp_path, root)
        self.http = TestClient(create_app(
            Runs(harness.graph, harness.context),
            Intake(root, FakeStructuredModel(*[FIELDS] * 5), ContentGuard(None, {}))),
            raise_server_exceptions=False)

    def post(self, **form):
        return self.http.post("/postings", data=form)


@pytest.fixture
def api(tmp_path):
    root = tmp_path / "data"
    write_json(root / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(root / "policy-pack.json", POLICY_PACK)
    return Api(tmp_path, root), root


def stored(root) -> list[str]:
    return sorted(path.stem for path in (root / "postings").glob("*.json"))


def test_same_url_again_returns_the_existing_posting_without_fetching(api, site):
    client, root = api
    first = client.post(url=f"{site}/static.html")
    again = client.post(url=f"{site}/static.html?utm_source=newsletter")
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["duplicate_by"] == "url" and again.json()["attempts"] == []
    assert again.json()["posting_id"] == first.json()["posting_id"]
    assert stored(root) == [first.json()["posting_id"]]


def test_same_text_again_returns_the_existing_posting(api):
    client, root = api
    first = client.post(text=TEXT)
    again = client.post(text=TEXT.upper().replace(". ", ".\n\n"))
    assert again.status_code == 200 and again.json()["duplicate_by"] == "text"
    assert again.json()["posting_id"] == first.json()["posting_id"] and len(stored(root)) == 1


@pytest.mark.parametrize("variant", [
    f"Posted 3 days ago · 120 applicants\n{TEXT}\nApply now. Report this job.",
    TEXT.replace(SENTENCES[8], "Our office is in Hamburg, and we work fully remote"),
])
def test_near_identical_text_is_a_duplicate(api, variant):
    client, root = api
    first = client.post(text=TEXT)
    again = client.post(text=variant)
    assert again.status_code == 200 and again.json()["duplicate_by"] == "similar_text"
    assert again.json()["posting_id"] == first.json()["posting_id"] and len(stored(root)) == 1


def test_a_different_posting_sharing_boilerplate_is_stored(api):
    client, root = api
    client.post(text=TEXT)
    assert client.post(text=OTHER).status_code == 201
    assert len(stored(root)) == 2


def test_a_short_text_is_compared_by_hash_only(api):
    client, root = api
    client.post(text=TEXT)
    teaser = ". ".join(SENTENCES[:2]) + "."
    assert client.post(text=teaser).status_code == 201
