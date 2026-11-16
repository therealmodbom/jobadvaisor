"""The redirect check for links from a mail (`design.md` → Cleaning): while `guarded_link`
names the URL a fetch starts at, no redirect hop with personal parameters is requested."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from jobadvaisor.intake.fetch import FetchError, download_plain, download_rendered, guarded_link

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
                       "/metadata": "http://169.254.169.254/latest"}
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
