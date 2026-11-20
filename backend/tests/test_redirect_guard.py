"""The redirect check for links from a mail (`design.md` → Cleaning): while `guarded_link`
names the URL a fetch starts at, no redirect hop with personal parameters is requested."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from jobadvaisor.data.models import ClosedRule
from jobadvaisor.intake.fetch import (
    CLOSED_REDIRECT,
    FetchError,
    closed_rules,
    download_plain,
    download_rendered,
    guarded_link,
)
from jobadvaisor.intake.ladder import fetch_posting

PAGE = "<html><body><main>" + "Eine Stelle. " * 60 + "</main></body></html>"


def mock_client(routes: dict[str, httpx.Response], seen: list[str]) -> httpx.Client:
    def handle(request):
        seen.append(str(request.url))
        return routes.get(str(request.url), httpx.Response(200, text=PAGE))
    return httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=True)


def guarded(url: str):
    class Scope:
        def __enter__(self):
            self.token = guarded_link.set(url)

        def __exit__(self, *exc):
            guarded_link.reset(self.token)
    return Scope()


START = "https://jobs.example.org/job/A/9101"


def test_plain_redirect_to_a_tokenised_address_is_never_requested():
    seen = []
    client = mock_client({START: httpx.Response(
        302, headers={"Location": "https://jobs.example.org/job/A/9101?sid=TOKEN-1"})}, seen)
    with guarded(START), pytest.raises(FetchError, match="redirect with personal parameters"):
        download_plain(START, client)
    assert seen == [START]


@pytest.mark.parametrize("target", ["http://169.254.169.254/latest", "http://127.1:8000/",
                                    "http://localhost/admin", "http://10.0.0.5/job/1"])
def test_plain_redirect_to_a_non_public_address_is_never_requested(target):
    seen = []
    client = mock_client({START: httpx.Response(302, headers={"Location": target})}, seen)
    with guarded(START), pytest.raises(FetchError, match="redirect to a non-public address"):
        download_plain(START, client)
    assert seen == [START]


def test_plain_redirect_to_the_same_path_with_a_slash_is_followed():
    seen = []
    client = mock_client({START: httpx.Response(301, headers={"Location": START + "/"})}, seen)
    with guarded(START):
        final, _ = download_plain(START, client)
    assert final == START + "/" and seen == [START, START + "/"]


@pytest.mark.parametrize("guard", [None, "https://other.example.org/job/1"])
def test_other_fetches_follow_redirects_as_before(guard):
    seen = []
    target = "https://jobs.example.org/job/A/9101?sid=TOKEN-1"
    client = mock_client({START: httpx.Response(302, headers={"Location": target})}, seen)
    with guarded(guard):
        final, _ = download_plain(START, client)
    assert final == target and seen == [START, target]


EXPIRED = "https://www.linkedin.com/jobs/view/1"
SEARCH_PAGE = "https://www.linkedin.com/jobs/search?trk=expired_jd_redirect"


@pytest.mark.parametrize("guard", [None, EXPIRED])
def test_a_redirect_to_a_closed_marker_is_never_requested(guard):
    seen = []
    client = mock_client({EXPIRED: httpx.Response(302, headers={"Location": SEARCH_PAGE})}, seen)
    with guarded(guard), pytest.raises(FetchError) as error:
        download_plain(EXPIRED, client)
    assert str(error.value) == CLOSED_REDIRECT
    assert seen == [EXPIRED]


def test_a_closed_marker_wins_over_the_refusal_of_a_personal_parameter():
    seen = []
    target = "https://www.linkedin.com/jobs/search?trk=expired_jd_redirect&sid=TOKEN-1"
    client = mock_client({EXPIRED: httpx.Response(302, headers={"Location": target})}, seen)
    with guarded(EXPIRED), pytest.raises(FetchError) as error:
        download_plain(EXPIRED, client)
    assert str(error.value) == CLOSED_REDIRECT and seen == [EXPIRED]


def test_a_marker_on_another_host_does_not_close_the_redirect():
    seen = []
    target = "https://jobs.example.org/search?trk=expired_jd_redirect"
    client = mock_client({START: httpx.Response(302, headers={"Location": target})}, seen)
    final, _ = download_plain(START, client)
    assert final == target and seen == [START, target]


def test_the_policy_packs_marker_is_read_from_the_context_variable():
    seen = []
    token = closed_rules.set([ClosedRule(host="example.org", redirect_marker="/gone")])
    client = mock_client({START: httpx.Response(
        302, headers={"Location": "https://jobs.example.org/gone"})}, seen)
    try:
        with pytest.raises(FetchError) as error:
            download_plain(START, client)
    finally:
        closed_rules.reset(token)
    assert str(error.value) == CLOSED_REDIRECT and seen == [START]


@pytest.fixture
def redirecting_site(monkeypatch):
    """A local server: `/start` answers 302 to `/target?sid=TOKEN-1`, `/clean` 302 to
    `/page/`, `/metadata` 302 to a link-local address; every request path is logged. The
    loopback server counts as public here: only link-local addresses are refused."""
    monkeypatch.setattr("jobadvaisor.intake.fetch.public_link", lambda url: "169.254" not in url)
    log = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            log.append(self.path)
            targets = {"/start": "/target?sid=TOKEN-1", "/clean": "/page/", "/chain": "/start",
                       "/metadata": "http://169.254.169.254/latest",
                       "/expired": "/search?trk=gone"}
            if self.path in targets:
                self.send_response(302)
                self.send_header("Location", targets[self.path])
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(PAGE.encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", log
    server.shutdown()


def test_rendered_redirect_to_a_tokenised_address_is_never_requested(redirecting_site):
    base, log = redirecting_site
    with guarded(f"{base}/start"), pytest.raises(FetchError, match="personal parameters"):
        download_rendered(f"{base}/start")
    assert not any(path.startswith("/target") for path in log)


def test_rendered_redirect_to_a_non_public_address_is_never_requested(redirecting_site):
    base, log = redirecting_site
    with guarded(f"{base}/metadata"), pytest.raises(FetchError, match="non-public address"):
        download_rendered(f"{base}/metadata")
    assert log == ["/metadata"]


def test_rendered_second_hop_is_checked_too(redirecting_site):
    base, log = redirecting_site
    with guarded(f"{base}/chain"), pytest.raises(FetchError, match="personal parameters"):
        download_rendered(f"{base}/chain")
    assert log == ["/chain", "/start"]


def test_rendered_clean_redirect_is_followed(redirecting_site):
    base, log = redirecting_site
    with guarded(f"{base}/clean"):
        final, _ = download_rendered(f"{base}/clean")
    assert final == f"{base}/page/"


def test_rendered_fetch_without_the_guard_follows_redirects(redirecting_site):
    base, log = redirecting_site
    final, _ = download_rendered(f"{base}/start")
    assert final == f"{base}/target?sid=TOKEN-1"


@pytest.fixture
def gone_marker():
    """A closed rule for the loopback server: a redirect to an address with `trk=gone`."""
    token = closed_rules.set([ClosedRule(host="127.0.0.1", redirect_marker="trk=gone")])
    yield
    closed_rules.reset(token)


@pytest.mark.parametrize("guard", [False, True])
def test_rendered_redirect_to_a_closed_marker_is_never_requested(
        redirecting_site, gone_marker, guard):
    base, log = redirecting_site
    with guarded(f"{base}/expired" if guard else None), pytest.raises(FetchError) as error:
        download_rendered(f"{base}/expired")
    assert str(error.value) == CLOSED_REDIRECT
    assert log == ["/expired"]


def test_a_429_then_a_rendered_redirect_to_a_closed_marker_is_closed(
        redirecting_site, gone_marker):
    """Without the route check, Chromium would follow the redirect and render the search page."""
    base, log = redirecting_site

    def rate_limited(url):
        raise FetchError("HTTP 429")
    result = fetch_posting(f"{base}/expired", [], plain=rate_limited)
    assert result.page is None
    assert [attempt.outcome for attempt in result.attempts] == ["HTTP 429", CLOSED_REDIRECT]
    assert log == ["/expired"]
