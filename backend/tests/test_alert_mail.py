"""The alert-mail finder (`openspec/changes/alert-mail-intake/design.md` → Link extraction,
Rules, Model fallback, Cleaning)."""

import json

import pytest

from jobadvaisor.intake.alert_mail import MAX_ENTRIES, Link, find_postings, read_mail
from jobadvaisor.settings import REPOSITORY_ROOT

FIXTURES = REPOSITORY_ROOT / "fixtures" / "intake" / "alert-mails"
RULE_CASES = ["linkedin-digest.html", "linkedin-single.html", "ba-list.html", "ba-plain.txt",
              "career-site-a.html", "career-site-b.html"]


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


class Untouchable:
    """A model or classifier that fails the test when the finder calls it."""

    def __getattr__(self, name):
        raise AssertionError(f"called {name} on a model or classifier")


class NoGuard:
    """A content guard whose classifier fails the test when used."""

    classifier = Untouchable()

    def screen(self, text):
        raise AssertionError("screened")


def find(name: str):
    content = fixture(name)
    html, text = (content, "") if name.endswith(".html") else (None, content)
    return find_postings(html, text, model=Untouchable(), guard=NoGuard())


def links(items) -> list[Link]:
    return [item for item in items if isinstance(item, Link)]


def test_linkedin_job_has_three_links_in_order():
    job = [link for link in links(read_mail(fixture("linkedin-digest.html"), ""))
           if "/4100000101/" in link.url]
    assert [link.image_only for link in job] == [True, False, False]
    assert job[0].text == "Nordlicht Systeme GmbH"  # the image's alt
    assert job[1].text.startswith("Leitung Softwareplattform (m/w/d)")  # the card around it
    assert job[2].text == "Leitung Softwareplattform (m/w/d)"


def test_text_blocks_and_links_keep_mail_order():
    items = read_mail('<p>Hallo</p><a href="https://jobs.example.com/job/1">Erste</a>'
                      '<p>Mitte</p><a href="https://jobs.example.com/job/2">Zweite</a>', "")
    assert items == ["Hallo", Link("https://jobs.example.com/job/1", "Erste", False), "Mitte",
                     Link("https://jobs.example.com/job/2", "Zweite", False)]


def test_script_and_style_are_dropped():
    items = read_mail('<style>a{color:red}</style><script>var x = "https://evil.example.com/x";'
                      '</script><a href="https://jobs.example.com/job/1">Job</a>', "")
    assert items == [Link("https://jobs.example.com/job/1", "Job", False)]


def test_alt_is_the_text_only_of_a_link_without_text():
    items = read_mail('<a href="https://jobs.example.com/job/1"><img alt="Logo"> Titel</a>', "")
    assert links(items) == [Link("https://jobs.example.com/job/1", "Titel", False)]


def test_plain_text_link_takes_the_first_line_of_its_block():
    found = links(read_mail(None, fixture("ba-plain.txt")))
    jobs = [link for link in found if "/jobdetail/" in link.url]
    assert [link.text for link in jobs] == [
        "Assistenz der Bereichsleitung (m/w/d)", "Teamassistenz (m/w/d), Teilzeit (bis zu 20 h)",
        "Senior Data Scientist (m/w/d)"]
    search = next(link for link in found if "/jobsuche/suche" in link.url)
    assert search.text == "Alle aktuellen Stellenangebote zu Ihrer Stellensuche:"


def test_plain_text_link_on_the_line_after_its_title():
    items = read_mail(None, "Hallo,\n\nEntwickler (m/w/d)\nhttps://jobs.example.com/job/1\n")
    assert links(items) == [Link("https://jobs.example.com/job/1", "Entwickler (m/w/d)", False)]


def test_html_wins_when_present():
    items = read_mail('<a href="https://jobs.example.com/job/1">Aus HTML</a>',
                      "Aus Text\nhttps://jobs.example.com/job/2")
    assert links(items) == [Link("https://jobs.example.com/job/1", "Aus HTML", False)]


def test_only_public_absolute_http_links_are_kept():
    hrefs = ["mailto:a@example.com", "javascript:alert(1)", "/job/1", "http://localhost:8000/job/1",
             "http://192.168.1.10/job/2", "http://10.0.0.1/job/3", "http://[::1]/job/4",
             "http://intranet/job/5", "ftp://jobs.example.com/job/6", "https://jobs.example.com/job/7"]
    html = "".join(f'<a href="{href}">Job</a>' for href in hrefs)
    assert [link.url for link in links(read_mail(html, ""))] == ["https://jobs.example.com/job/7"]


@pytest.mark.parametrize("name", RULE_CASES)
def test_rule_fixture_gives_its_expected_entries(name):
    found = find(name)
    expected = json.loads((FIXTURES / name).with_suffix(".json").read_text())
    assert [{"url": e.url, "title": e.title} for e in found.entries] == expected
    assert found.unread_hosts == [] and not found.truncated and found.model_skipped is None


@pytest.mark.parametrize(("name", "rule"), [
    ("linkedin-digest.html", "linkedin"), ("ba-list.html", "bundesagentur"),
    ("ba-plain.txt", "bundesagentur"), ("career-site-a.html", "career_site")])
def test_rule_fixture_names_its_rule(name, rule):
    assert find(name).read_by == [rule]


@pytest.mark.parametrize("url", [
    "https://www.linkedin.com/jobs/view/4100000101",
    "https://www.linkedin.com/comm/jobs/view/4100000101/?otpToken=TOKEN-1",
    "https://www.linkedin.com/jobs/view/leitung-softwareplattform-4100000101/",
    "https://www.linkedin.com/jobs/search/?currentJobId=4100000101"])
def test_linkedin_rule_reads_four_forms(url):
    html = f'<a href="{url}"><img alt="Firma"></a><a href="{url}">Leitung (m/w/d)</a>'
    found = find_postings(html, "", model=Untouchable(), guard=NoGuard())
    assert [(e.url, e.title) for e in found.entries] == [
        ("https://www.linkedin.com/jobs/view/4100000101", "Leitung (m/w/d)")]


def test_footer_and_search_links_are_not_entries():
    urls = [e.url for e in find("linkedin-digest.html").entries]
    assert all("/jobs/view/" in url for url in urls) and len(urls) == 6


def test_job_path_without_refid_is_not_a_career_site_link():
    html = ('<a href="https://news.example.com/job/Leitung/12345/?utm_source=TOKEN-1">Leitung</a>'
            '<a href="https://careers.example.com/job/A/2000000001/?refid=TOKEN-2">A - Ort, DE</a>')
    found = find_postings(html, "", model=Untouchable(), guard=NoGuard())
    assert [e.url for e in found.entries] == ["https://careers.example.com/job/A/2000000001/"]
    assert found.unread_hosts == [{"host": "news.example.com", "links": 1}]


def test_a_title_is_never_a_url_or_an_image():
    url = "https://www.linkedin.com/jobs/view/4100000101"
    html = (f'<a href="{url}"><img alt="Firma"></a><a href="{url}">{url}</a>'
            f'<a href="{url}">linkedin.com</a>'
            f'<a href="{url}">Firma · Ort</a><a href="{url}">Leitung (m/w/d)</a>')
    found = find_postings(html, "", model=Untouchable(), guard=NoGuard())
    assert found.entries[0].title == "Leitung (m/w/d)"


def test_more_than_the_limit_is_truncated():
    html = "".join(f'<a href="https://www.linkedin.com/jobs/view/{4100000000 + n}">Job {n}</a>'
                   for n in range(120))
    found = find_postings(html, "", model=Untouchable(), guard=NoGuard())
    assert len(found.entries) == MAX_ENTRIES == 100 and found.truncated
    assert found.entries[-1].title == "Job 99"


def test_two_senders_in_one_paste_name_the_unread_hosts():
    found = find_postings(fixture("linkedin-digest.html") + fixture("unknown-jobid.html"), "",
                          model=Untouchable(), guard=NoGuard())
    assert len(found.entries) == 6 and found.read_by == ["linkedin"]
    assert found.unread_hosts == [{"host": "jobs.example.net", "links": 4},
                                  {"host": "social.example.com", "links": 4},
                                  {"host": "www.linkedin.com", "links": 1}]


def test_unread_link_on_a_host_a_rule_read_is_named():
    html = ('<a href="https://careers.example.com/job/A/2000000001/?refid=TOKEN-1">A - Ort, DE</a>'
            '<a href="https://careers.example.com/stellen/4711?sid=TOKEN-2">Zweite Stelle</a>'
            '<a href="https://careers.example.com/stellen/4711?sid=TOKEN-3">Zweite Stelle</a>')
    found = find_postings(html, "", model=Untouchable(), guard=NoGuard())
    assert [e.title for e in found.entries] == ["A"]
    assert found.unread_hosts == [{"host": "careers.example.com", "links": 1}]


def test_unread_hosts_are_capped():
    html = '<a href="https://www.linkedin.com/jobs/view/4100000101">Job</a>' + "".join(
        f'<a href="https://jobs{n:02}.example.com/stelle/1">Stelle</a>' for n in range(12))
    found = find_postings(html, "", model=Untouchable(), guard=NoGuard())
    assert [h["host"] for h in found.unread_hosts] == [
        f"jobs{n:02}.example.com" for n in range(10)]
