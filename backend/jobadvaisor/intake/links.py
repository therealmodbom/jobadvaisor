"""Link cleaning shared by the alert-mail finder, the fetch's redirect check and duplicate
detection (ADR 0012). No intake imports, so `fetch` can use it."""

import ipaddress
import re
import socket
from urllib.parse import parse_qsl, unquote_plus, urlsplit

POSTING_PARAMETERS = {"id", "jobid", "job_id", "job", "jid", "reqid", "req_id", "requisitionid",
                      "postingid", "posting_id", "vacancyid", "positionid"}
LINKEDIN_JOB_PATH = re.compile(r"^(?:/comm)?/jobs/view/(?:[^/]*-)?(\d+)/?$")
LINKEDIN_JOBS_PATH = re.compile(r"^(?:/comm)?/jobs/")


USER_INFO = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*://)[^/?#]*@")


def strip_query(url: str) -> str:
    """`url` without user info (`user:password@`), with only the query parameters whose
    lowercased name is in `POSTING_PARAMETERS`, and its fragment only when that is a hash route
    (`#/…`, `#!…`) without `=`. Everything else is kept byte for byte, so a clean address comes
    back unchanged."""
    base, has_fragment, fragment = url.partition("#")
    base, _, query = base.partition("?")
    base = USER_INFO.sub(r"\1", base)
    kept = [pair for pair in query.split("&")
            if pair and unquote_plus(pair.split("=", 1)[0]).lower() in POSTING_PARAMETERS]
    out = base + (f"?{'&'.join(kept)}" if kept else "")
    if has_fragment and fragment.startswith(("/", "!")) and "=" not in fragment:
        out += f"#{fragment}"
    return out


def navigation_allowed(url: str) -> bool:
    """Whether a redirect may go to `url`: it carries nothing `strip_query` would remove (no
    user info, no personal parameter)."""
    return strip_query(url) == url


def public_link(url: str) -> bool:
    """Whether `url` is an absolute http(s) address on a public host: not `localhost`, not a
    single-label host, and no IP address in a loopback, private, link-local or reserved range,
    in any form the resolver reads (`127.1`, `0x7f.0.0.1`, `0177.0.0.1`, `2130706433`). The
    host name is not resolved, so a public name that points at a private address passes."""
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").rstrip(".").lower()
    except ValueError:
        return False
    if parts.scheme.lower() not in ("http", "https") or not host:
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        pass
    try:
        return ipaddress.ip_address(socket.inet_aton(host)).is_global
    except OSError:
        return "." in host and host != "localhost" and not host.endswith(".localhost")


def linkedin_job_id(url: str) -> str | None:
    """The job ID of a LinkedIn job page in any of its forms (`/jobs/view/<id>`,
    `/comm/jobs/view/<id>`, `/jobs/view/<slug>-<id>`, `currentJobId=<id>` on a `/jobs/` path),
    or `None` for any other address."""
    try:
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower()
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not (
            host == "linkedin.com" or host.endswith(".linkedin.com")):
        return None
    if match := LINKEDIN_JOB_PATH.match(parts.path):
        return match.group(1)
    if LINKEDIN_JOBS_PATH.match(parts.path):
        current = dict(parse_qsl(parts.query)).get("currentJobId", "")
        return current if current.isdigit() else None
    return None
