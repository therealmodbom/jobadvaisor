"""The alert-mail finder (`openspec/changes/alert-mail-intake/design.md` → Link extraction,
Rules, Model fallback, Cleaning)."""

from jobadvaisor.intake.alert_mail import Link, read_mail
from jobadvaisor.settings import REPOSITORY_ROOT

FIXTURES = REPOSITORY_ROOT / "fixtures" / "intake" / "alert-mails"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


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
