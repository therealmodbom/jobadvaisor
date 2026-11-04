import json

from jobadvaisor.data.trim_linkedin import trim_repository, trim_text

WHOLE_PAGE = "\n".join([
    "Skip to main content", "Platform Engineer", "Brightwater Analytics", "Berlin, Germany",
    "Join or sign in to find your next job", "Report this job",
    "You build and run the data platform.", "Several years of Python.",
    "Seniority level", "Mid-Senior level", "Employment type", "Full-time",
    "Referrals increase your chances of interviewing at Brightwater Analytics", "See who you know",
    "Get notified about new jobs", "Sign in to create job alert", "Similar jobs",
    "Network Administrator", "Chief Information Officer", "Agree & Join LinkedIn"])
BODY = ("You build and run the data platform.\nSeveral years of Python.\n"
        "Seniority level\nMid-Senior level\nEmployment type\nFull-time")


def write_posting(root, name, text, url):
    (root / "postings").mkdir(exist_ok=True)
    path = root / "postings" / f"{name}.json"
    path.write_text(json.dumps({
        "schema_version": "2", "title": "Platform Engineer", "company": "Brightwater Analytics",
        "location_raw": "Berlin, Germany", "text": text, "source_type": "url", "urls": [url],
        "added_at": "2026-10-26T21:38:43Z", "status": "open"}))
    return path


def test_trim_text_keeps_the_lines_between_the_report_and_the_referral_marker():
    assert trim_text(WHOLE_PAGE) == BODY


SIGN_IN_BLOCK = ["Use AI to assess how you fit", "Get AI-powered advice on this job."] + [
    line for topic in ("access AI-powered advices", "evaluate your skills", "tailor your resume")
    for line in (f"Sign in to {topic}", "Forgot password?", "or", "New to LinkedIn? Join now",
                 "By clicking Continue to join or sign in, you agree to the terms.")]
POSTER_BLOCK = ["Direct message the job poster from Brightwater Analytics", "Jane Doe", "Jane Doe",
                "Recruiting lead at Brightwater Analytics"]


def whole_page_with(*blocks):
    before, after = WHOLE_PAGE.split("Report this job\n")
    inner, rest = after.split("Seniority level", 1)
    extra = [line for block in blocks for line in block]
    return "\n".join([before + "Report this job", *extra, inner.rstrip("\n"),
                      "Seniority level" + rest])


def test_trim_text_also_drops_the_sign_in_block_and_the_poster_block():
    assert trim_text(whole_page_with(SIGN_IN_BLOCK, POSTER_BLOCK)) == BODY
    assert trim_text(whole_page_with(POSTER_BLOCK)) == BODY


def test_trim_text_gives_up_on_a_poster_block_of_an_unknown_shape():
    assert trim_text(whole_page_with(POSTER_BLOCK[:2], ["Not a name twice"])) is None


def test_trim_text_gives_up_on_a_text_without_the_whole_page_layout():
    assert trim_text(BODY) is None
    assert trim_text("Report this job\nA body, but no end marker.") is None


def test_a_dry_run_reports_what_it_would_trim_and_writes_nothing(tmp_path):
    path = write_posting(tmp_path, "one", WHOLE_PAGE, "https://www.linkedin.com/jobs/view/1")
    report = trim_repository(tmp_path, apply=False)
    assert [name for name, _, _ in report.trimmed] == ["one"] and report.unchanged == []
    assert json.loads(path.read_text())["text"] == WHOLE_PAGE


def test_apply_trims_linkedin_texts_and_leaves_everything_else_alone(tmp_path):
    trimmed = write_posting(tmp_path, "one", WHOLE_PAGE, "https://de.linkedin.com/jobs/view/1")
    odd = write_posting(tmp_path, "two", "Some other layout\n" * 3, "https://www.linkedin.com/jobs/view/2")
    other = write_posting(tmp_path, "three", WHOLE_PAGE, "https://jobs.example.test/3")
    report = trim_repository(tmp_path, apply=True)
    assert [name for name, _, _ in report.trimmed] == ["one"]
    assert report.unchanged == ["two"]
    after = json.loads(trimmed.read_text())
    assert after["text"] == BODY and after["title"] == "Platform Engineer"
    assert json.loads(odd.read_text())["text"] == "Some other layout\n" * 3
    assert json.loads(other.read_text())["text"] == WHOLE_PAGE
