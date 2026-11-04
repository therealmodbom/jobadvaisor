"""Ladder step 0 for the Bundesagentur für Arbeit job board (`design.md` → Intake).

The job-detail interface is undocumented (described by the community project
bundesAPI/jobsuche-api) and changes without notice, so every endpoint detail lives here only.
"""

import base64
import re

import httpx

from jobadvaisor.intake.fetch import TIMEOUT_SECONDS, FetchError, Page

URL_PATTERN = re.compile(
    r"^https?://(?:www\.)?arbeitsagentur\.de/jobsuche/jobdetail/([A-Za-z0-9-]+)")
DETAIL_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/{}"
SEARCH_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs"
HEADERS = {"X-API-Key": "jobboerse-jobsuche"}


def reference_number(url: str) -> str | None:
    """The posting's reference number when `url` is a job-board detail URL, else `None`."""
    match = URL_PATTERN.match(url)
    return match.group(1) if match else None


def fetch_bundesagentur(url: str, http: httpx.Client | None = None) -> Page:
    """The posting behind a job-board detail URL from the job-detail interface: description as
    text, title, company and locations as supplied fields (those the answer names). Raises
    `FetchError` for a non-200 answer, a timeout, a connection error, an unparseable body or an
    empty description, so the ladder continues with the plain fetch."""
    number = reference_number(url)
    if number is None:
        raise FetchError("no job-board detail URL")
    http = http or httpx.Client(timeout=TIMEOUT_SECONDS)
    try:
        response = http.get(DETAIL_URL.format(base64.b64encode(number.encode()).decode()),
                            headers=HEADERS)
    except httpx.HTTPError as error:
        raise FetchError(f"connection failed: {type(error).__name__}") from None
    if response.status_code != 200:
        raise FetchError(f"HTTP {response.status_code}")
    try:
        detail = response.json()
    except ValueError:
        raise FetchError("unparseable answer") from None
    if not isinstance(detail, dict):
        raise FetchError("unparseable answer")
    text = detail.get("stellenangebotsBeschreibung")
    if not isinstance(text, str) or not text.strip():
        raise FetchError("no posting text")
    places = [location.get("adresse") or {} for location in detail.get("stellenlokationen") or []
              if isinstance(location, dict)]
    towns = [place.get("ort") or place.get("region") for place in places
             if isinstance(place, dict)]
    fields = {"title": detail.get("stellenangebotsTitel"), "company": detail.get("firma"),
              "location_raw": "; ".join(dict.fromkeys(
                  town.strip() for town in towns if isinstance(town, str) and town.strip()))}
    return Page(url, text.strip(), {name: value.strip() for name, value in fields.items()
                                    if isinstance(value, str) and value.strip()})


def live_reference_number() -> str:
    """The reference number of one current posting, from the job board's search interface;
    for the opt-in live smoke test only."""
    response = httpx.get(SEARCH_URL, params={"was": "Softwareentwickler", "size": 1},
                         headers=HEADERS, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()["ergebnisliste"][0]["referenznummer"]
