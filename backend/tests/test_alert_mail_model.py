"""The finder's model fallback (`design.md` → Model fallback): screening first, the model sees
link numbers, hosts and paths only, and answers link numbers and titles."""

import re
import time

import pytest
from conftest import FakeStructuredModel
from test_alert_mail import NoGuard, Untouchable, fixture
from test_guard import THRESHOLDS, StubClassifier

from jobadvaisor.evals.alert_mail import load_cases
from jobadvaisor.intake import alert_mail
from jobadvaisor.intake.alert_mail import FinderError, find_postings, model_view, read_mail
from jobadvaisor.tools.guard import ContentGuard


class FlagAll(StubClassifier):
    def classify(self, text):
        self.calls += 1
        return {"jailbreaking": 0.9, "dangerous": 0.1}


class Broken(StubClassifier):
    def classify(self, text):
        raise RuntimeError("classifier down")


def number_of(html: str, needle: str) -> int:
    """The link number the model sees for the first kept link whose text holds `needle`."""
    _, links = model_view(read_mail(html, ""))
    return next(n for n, link in enumerate(links, 1) if needle in link.text)


def answer(*postings: tuple[int, str]) -> FakeStructuredModel:
    return FakeStructuredModel({"postings": [{"link": n, "title": t} for n, t in postings]})


def run(html: str, model, classifier=None):
    guard = ContentGuard(classifier or StubClassifier(), THRESHOLDS)
    return find_postings(html, "", model=model, guard=guard)


def test_screening_off_skips_the_model():
    found = find_postings(fixture("unknown-jobid.html"), "", model=Untouchable(),
                          guard=ContentGuard(None, {}))
    assert found.entries == [] and found.model_skipped == "screening off"


def test_mail_without_postings_calls_nothing():
    found = find_postings(fixture("no-postings.html"), "", model=Untouchable(), guard=NoGuard())
    assert found.entries == [] and found.model_skipped is None and not found.held


def test_model_input_holds_no_query_and_no_path_token():
    html = fixture("unknown-jobid.html")
    model = answer((number_of(html, "Produktmanager"), "Produktmanager Fertigungsdaten (f/m/d)"))
    run(html, model)
    prompt = model.prompts[0][-1].content
    assert "TOKEN" not in prompt and not re.search(r"\?\w+=", prompt)
    assert "Xk9fQ2mLp7RtZ4vWb8NsYc3D" not in prompt and "/Apply/…" in prompt
    assert "jobs.example.net/de_DE/externaljobs/JobDetail" in prompt


def test_found_entries_carry_cleaned_links_in_link_order():
    html = fixture("unknown-jobid.html")
    first, second = number_of(html, "Produktmanager"), number_of(html, "Senior Berater")
    found = run(html, answer((second, "Senior Berater Datenanalyse (f/m/d)"),
                             (first, "Produktmanager Fertigungsdaten (f/m/d)")))
    assert [(e.url, e.title) for e in found.entries] == [
        ("https://jobs.example.net/de_DE/externaljobs/JobDetail?jobId=700001",
         "Produktmanager Fertigungsdaten (f/m/d)"),
        ("https://jobs.example.net/de_DE/externaljobs/JobDetail?jobId=700002",
         "Senior Berater Datenanalyse (f/m/d)")]
    assert found.read_by == ["model"] and found.unread_hosts == []


def test_unknown_number_and_written_url_yield_nothing():
    html = fixture("unknown-jobid.html")
    found = run(html, answer((999, "Erfunden"), (0, "Null"),
                             (number_of(html, "Senior Berater"), "https://evil.example.com/job")))
    assert found.entries == []


def test_two_titles_behind_one_redirect_address_are_ambiguous():
    html = fixture("unknown-redirect.html")
    found = run(html, answer((number_of(html, "Leitung Technik"), "Leitung Technik:in (m/w/d)"),
                             (number_of(html, "Leitung Daten"), "Leitung Daten:in (m/w/d)"),
                             (number_of(html, "Plattform"), "Plattform Engineer:in (m/w/d)")))
    assert [(e.url, e.title, e.ambiguous) for e in found.entries] == [
        ("https://trk.example.com/ls/click", "Leitung Technik:in (m/w/d)", True),
        ("https://trk.example.com/ls/click", "Leitung Daten:in (m/w/d)", True),
        ("https://app.example.com/jobs/plattform-engineer-4711", "Plattform Engineer:in (m/w/d)",
         False)]


def test_one_title_behind_two_links_is_one_entry():
    html = ('<a href="https://jobs.example.org/stelle/1?s=TOKEN-1"><img alt="Logo"></a>'
            '<a href="https://jobs.example.org/stelle/1?s=TOKEN-2">Entwickler (m/w/d)</a>')
    found = run(html, answer((1, "Entwickler (m/w/d)"), (2, "entwickler  (m/w/d)")))
    assert [(e.url, e.ambiguous) for e in found.entries] == [
        ("https://jobs.example.org/stelle/1", False)]


def test_flagged_mail_is_held_without_a_model_call():
    classifier = FlagAll()
    found = run(fixture("injection.html"), Untouchable(), classifier)
    assert found.held and found.entries == [] and classifier.calls == 1


def test_failing_classifier_stops_before_the_model():
    with pytest.raises(FinderError, match="screening failed"):
        run(fixture("unknown-jobid.html"), Untouchable(), Broken())


def test_failing_model_is_a_finder_error():
    class Failing:
        def with_structured_output(self, schema):
            raise RuntimeError("provider down")

    with pytest.raises(FinderError, match="finder failed"):
        run(fixture("unknown-jobid.html"), Failing())


def test_links_beyond_the_model_text_limit_are_not_numbered_and_the_cut_is_reported():
    filler = "<p>" + "Neuigkeiten aus der Branche. " * 1200 + "</p>"
    html = JOB_LINK + filler + (
        '<a href="https://jobs.example.net/de_DE/externaljobs/JobDetail?jobId=700002">Berater</a>')
    text, numbered = model_view(read_mail(html, ""))
    assert len(text) <= 30_000 and [link.text for link in numbered] == ["Produktmanager"]
    model = answer((1, "Produktmanager"), (2, "Berater"))
    found = run(html, model)
    assert [e.title for e in found.entries] == ["Produktmanager"] and found.truncated


JOB_LINK = ('<a href="https://jobs.example.net/de_DE/externaljobs/JobDetail?jobId=700001">'
            "Produktmanager</a>")


def test_model_input_holds_no_query_of_a_url_written_without_scheme():
    html = (f"<p>{JOB_LINK}</p><p>Link kaputt? www.jobs.example.org/a?sessionToken=SECRET1</p>"
            '<a href="https://jobs.example.org/job/9">jobs.example.org/x?sid=SECRET2</a>')
    text, _ = model_view(read_mail(html, ""))
    assert "SECRET" not in text and "sessionToken" not in text and "sid=" not in text


def test_model_input_holds_no_dotted_path_token():
    token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r"
    html = f'<a href="https://jobs.example.org/job/{token}">Produktmanager</a>'
    text, _ = model_view(read_mail(html, ""))
    assert "eyJ" not in text and "dBjft" not in text


# The pattern before #154: its bare-domain alternative had no anchor, so one long unbroken word
# took quadratic time. Kept here so the fixtures can show that the new one masks the same text.
QUADRATIC_MASKED_URL = re.compile(
    r"(?i)https?://[^\s<>\"')\]]+|(?:www\.)?[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}[/?][^\s<>\"')\]]*")
LONG_WORD = 2_000_000


@pytest.mark.parametrize("word", ["a" * LONG_WORD, "a." * (LONG_WORD // 2)],
                         ids=["unbroken", "dotted"])
def test_masking_one_long_word_takes_linear_time(word):
    """#154: a 2,000,000-character word without a space, or one of the form `a.a.a.…`, is masked
    in well under a second (the quadratic pattern needed hours). The bound is generous for a
    slow machine, not a benchmark."""
    started = time.perf_counter()
    model_view([word])
    assert time.perf_counter() - started < 1


@pytest.mark.parametrize("case", [case.name for case in load_cases()])
def test_masking_leaves_the_model_view_of_every_fixture_unchanged(case, monkeypatch):
    """The anchored pattern gives the same model view as the quadratic one on every alert-mail
    fixture, `.eml` ones included."""
    mail = next(mail for mail in load_cases() if mail.name == case)
    items = read_mail(mail.html, mail.text)
    anchored = model_view(items)
    monkeypatch.setattr(alert_mail, "MASKED_URL", QUADRATIC_MASKED_URL)
    assert model_view(items) == anchored
