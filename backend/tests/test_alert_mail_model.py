"""The finder's model fallback (`design.md` → Model fallback): screening first, the model sees
link numbers, hosts and paths only, and answers link numbers and titles."""

import re

import pytest
from conftest import FakeStructuredModel
from test_alert_mail import NoGuard, Untouchable, fixture
from test_guard import THRESHOLDS, StubClassifier

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
