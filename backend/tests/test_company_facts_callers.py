"""Every caller of the extraction passes the posting company's record, so evals and the benchmark
measure what production sends."""

from conftest import AT, POSTING, PROFILE, ScriptedModel, unknown_features, write_json
from test_eval_decider import FakeDecider
from test_extractor_benchmark import unknown_choices
from test_triage_graph import POLICY_PACK, Harness

from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import load
from jobadvaisor.data.models import company_id
from jobadvaisor.evals import extractor_benchmark
from jobadvaisor.evals.feature_extraction import run as run_feature_extraction
from jobadvaisor.llm import Decider
from jobadvaisor.tools.extraction import DEFAULT_FEATURE_SET

RECORD = {"schema_version": "1", "name": "Example Corp", "size_class": "201-500",
          "founded": 2016, "source": "linkedin",
          "source_url": "https://www.linkedin.com/company/example-corp", "fetched_at": AT}
BLOCK = "Size class: 201-500 employees. Founded: 2016. Looked up on LinkedIn on 2026-01-05."
CLEAN = {"flagged": False, "checked_by": "test", "checked_at": AT}


def test_the_triage_graph_sends_the_block_for_a_company_with_a_record(tmp_path):
    data = tmp_path / "data"
    write_json(data / "profile.json", PROFILE)
    write_json(data / "policy-pack.json", POLICY_PACK)
    write_json(data / "postings/p1.json", {**POSTING, "guard": CLEAN})
    write_json(data / "postings/p2.json", {**POSTING, "company": "Other Co", "guard": CLEAN})
    write_json(data / f"companies/{company_id('Example Corp')}.json", RECORD)
    harness = Harness(tmp_path, data)
    harness.start("run-1")
    sent = {call.split("Company: ")[1].split("\n")[0]: BLOCK in call
            for call in harness.extractor.calls}
    assert sent == {"Example Corp": True, "Other Co": False}


def test_the_benchmark_sends_the_block_for_a_company_with_a_record(data_repository):
    write_json(data_repository / f"companies/{company_id('Example Corp')}.json", RECORD)
    write_json(data_repository / "postings/p2.json", {**POSTING, "company": "Other Co"})
    model = ScriptedModel(unknown_features)
    extractor_benchmark.extract_postings(load(data_repository), model, DEFAULT_FEATURE_SET)
    sent = {call.split("Company: ")[1].split("\n")[0]: BLOCK in call for call in model.calls}
    assert sent == {"Example Corp": True, "Other Co": False}


def test_a_decision_model_in_the_benchmark_gets_no_facts_block(data_repository):
    write_json(data_repository / f"companies/{company_id('Example Corp')}.json", RECORD)
    client = FakeDecider(unknown_choices)
    calls = extractor_benchmark.extract_postings(
        load(data_repository), Decider(client, "typesafe/jev"), DEFAULT_FEATURE_SET,
        extract=extractor_benchmark.extract_choices_without_facts)
    assert [call.error for call in calls] == [None, None]
    assert client.requests and not any(
        "company_facts" in str(request) for request in client.requests)


def test_the_feature_extraction_eval_sends_the_block_on_the_demo_persona():
    demo, model = load(FIXTURE_DIRECTORY), ScriptedModel(unknown_features)
    run_feature_extraction(demo, model, "stub")
    named = {posting.company for posting in demo.postings.values()}
    sent = {call.split("Company: ")[1].split("\n")[0]: "<company_facts>" in call
            for call in model.calls}
    assert any(sent.values())
    assert all(has_block == (company != "unknown") for company, has_block in sent.items()
               if company in named)
