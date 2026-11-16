"""The public side of the alert-mail fixtures (`design.md` → Eval): every case has its expectation,
and no fixture holds a real token, address or host."""

import html
import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import pytest

from jobadvaisor.settings import REPOSITORY_ROOT

FIXTURES = REPOSITORY_ROOT / "fixtures" / "intake" / "alert-mails"
ALLOWED_IDS = {"700001", "700002", "700003", "700004", "799999"}  # invented job IDs
URL = re.compile(r"https?://[^\s\"'<>]+")
ADDRESS = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
EXAMPLE = re.compile(r"(^|\.)example\.(com|org|net)$")


def mails() -> list[Path]:
    return sorted(p for p in FIXTURES.iterdir() if p.suffix in (".html", ".txt"))


def leaks(text: str) -> list[str]:
    """What breaks the fixture rules in `text`: a query value that is neither `TOKEN-<n>` nor an
    allowed invented ID, an address outside `example.*`, a host other than LinkedIn, the
    Bundesagentur and `example.*`, or an image content ID other than `cid:image-<n>`."""
    text = html.unescape(text)
    found = []
    for url in URL.findall(text):
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if not (host == "linkedin.com" or host.endswith(".linkedin.com")
                or host == "arbeitsagentur.de" or host.endswith(".arbeitsagentur.de")
                or EXAMPLE.search(host)):
            found.append(f"host {host}")
        for name, value in parse_qsl(parts.query, keep_blank_values=True):
            if not (re.fullmatch(r"TOKEN-\d+", value) or value in ALLOWED_IDS):
                found.append(f"query value of {name}")
    found += [f"address at {domain}" for domain in ADDRESS.findall(text)
              if not EXAMPLE.search(domain.lower())]
    found += [f"content ID {cid}" for cid in re.findall(r"cid:[^\"'\s>]+", text)
              if not re.fullmatch(r"cid:image-\d+", cid)]
    return found


def test_there_are_cases():
    assert len(mails()) >= 10


@pytest.mark.parametrize("mail", mails(), ids=lambda p: p.name)
def test_case_has_its_expectation(mail):
    expected = json.loads(mail.with_suffix(".json").read_text())
    assert expected == {"held": True} or all(set(e) == {"url", "title"} for e in expected)


@pytest.mark.parametrize("mail", mails(), ids=lambda p: p.name)
def test_fixture_holds_no_real_value(mail):
    assert leaks(mail.read_text()) == []


def test_the_check_finds_planted_values():
    planted = ('<a href="https://www.linkedin.com/comm/jobs/view/1/?otpToken=abc123">x</a> '
               'https://jobs.realcorp.de/job/1 mail: someone@gmx.de '
               'https://jobs.example.com/?jobId=12345&amp;s=TOKEN-1 '
               '<img src="cid:17942807406af28d"><img src="cid:image-1">')
    assert leaks(planted) == ["query value of otpToken", "host jobs.realcorp.de",
                              "query value of jobId", "address at gmx.de",
                              "content ID cid:17942807406af28d"]
