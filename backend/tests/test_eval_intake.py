"""The intake and field-filling evals' harnesses, with fake models. The evals themselves make
real calls and run only through `python -m jobadvaisor.evals`."""

import json

from conftest import ScriptedModel, ToolScriptModel

from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import load
from jobadvaisor.evals import __main__ as cli
from jobadvaisor.evals.field_filling import EXPECTED_FILE, normalize
from jobadvaisor.evals.field_filling import run as run_fields
from jobadvaisor.evals.intake import CASES
from jobadvaisor.evals.intake import run as run_intake
from jobadvaisor.tools.guard import ContentGuard

EXPECTED = json.loads(EXPECTED_FILE.read_text())


def test_field_expectations_cover_three_pages_ten_texts_and_five_pdfs():
    demo = load(FIXTURE_DIRECTORY)
    assert len(EXPECTED["pages"]) == 3 and len(EXPECTED["text"]) == 10
    assert len(EXPECTED["pdf"]) == 5
    assert set(EXPECTED["text"]) | set(EXPECTED["pdf"]) <= set(demo.postings)


PAGE_MARKERS = {"Harbor Freight": "static.html", "Brightwater Health": "rendered.html",
                "Orchard Lane": "jsonld-no-company.html"}


def expected_fields(prompt: str) -> dict:
    """The expectations of the posting whose text `prompt` holds."""
    postings, flat = load(FIXTURE_DIRECTORY).postings, " ".join(prompt.split())
    for group in ("text", "pdf"):
        for posting_id, fields in EXPECTED[group].items():
            if " ".join(postings[posting_id].text.split())[:200] in flat:
                return fields
    return next(EXPECTED["pages"][page] for marker, page in PAGE_MARKERS.items()
                if marker in prompt)


def expected_answer(schema, prompt):
    """The first accepted value of every requested field, for the posting in `prompt`."""
    fields = expected_fields(prompt)
    answer = {"title": fields["title"][0], "company": fields["company"][0],
              "location_raw": fields["location"]}
    return {name: answer[name] for name in schema.model_fields}


def test_field_filling_reports_per_field_accuracy_by_source():
    report = run_fields(load(FIXTURE_DIRECTORY), ScriptedModel(expected_answer), "fake")
    assert report["accuracy"] == {"title": 1.0, "company": 1.0, "location": 1.0}
    assert report["cases"] == 18 and report["by_source"]["pdf"]["company"] == 1.0
    assert report["errors"] == [] and report["mismatches"] == []


def test_field_filling_counts_a_wrong_answer_as_a_mismatch():
    def wrong_company(schema, prompt):
        return expected_answer(schema, prompt) | (
            {"company": "Acme"} if "company" in schema.model_fields else {})

    report = run_fields(load(FIXTURE_DIRECTORY), ScriptedModel(wrong_company), "fake")
    assert report["accuracy"]["company"] == 0.0 and report["accuracy"]["title"] == 1.0
    assert len(report["mismatches"]) == 18


def test_titles_match_without_a_seniority_level_phrase():
    assert normalize("Mid-level Flutter Developer", "title") == normalize("Flutter Developer",
                                                                          "title")


def test_intake_eval_counts_ladder_hits_and_the_unrecoverable_case():
    report = run_intake(lambda target: ToolScriptModel(), ContentGuard(None, {}), "fake")
    results = {case["case"]: case for case in report["cases"]}
    assert set(results) == {case.name for case in CASES}
    assert all(results[name]["success"] for name in ("json_ld", "static", "script_rendered",
                                                     "unrecoverable"))
    assert not results["login_walled_with_alternative"]["success"]
    assert report["success_rate"] == round(4 / 6, 3) and report["mean_tool_calls"] == 0.0


def test_intake_eval_loop_cases_succeed_when_the_model_follows_the_search():
    def follow(target):
        alternative = target.alternative_url or target.url
        return ToolScriptModel(plan=[
            ("search_alternative_source", {"query": target.hints["company"]}),
            ("fetch_plain", {"url": alternative}), ("report_posting", {"url": alternative})])

    report = run_intake(follow, ContentGuard(None, {}), "fake")
    results = {case["case"]: case for case in report["cases"]}
    assert results["login_walled_with_alternative"]["success"]
    assert results["dead_link_with_alternative"]["success"]
    assert results["login_walled_with_alternative"]["tool_calls"] == 2
    assert results["unrecoverable"]["success"] and report["success_rate"] == 1.0


def test_both_evals_are_registered():
    assert {"intake", "field_filling"} <= set(cli.EVALS)
