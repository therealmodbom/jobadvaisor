"""The extractor benchmark (`openspec/changes/extractor-benchmark`), with stub models: no test
here makes a paid call."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import POSTING, ScriptedModel, unknown_features, write_json
from test_eval_agent import PricedModel
from test_eval_decider import FakeDecider

from jobadvaisor.data.loader import load
from jobadvaisor.evals import extraction_accuracy as accuracy
from jobadvaisor.evals import extractor_benchmark
from jobadvaisor.llm import Decider
from jobadvaisor.settings import REPOSITORY_ROOT, Settings
from jobadvaisor.tools.extraction import DEFAULT_FEATURE_SET, INSTRUCTIONS


@pytest.fixture
def repository(data_repository):
    """The `data_repository` fixture plus a third posting: p1 Backend, p2 Data, p3 Cloud."""
    write_json(data_repository / "postings/p3.json", {**POSTING, "title": "Cloud Engineer"})
    return load(data_repository)


class PricedScripted(ScriptedModel):
    """A scripted extractor whose every answer costs one `PricedModel` call (0.25)."""

    def _answer(self, schema, messages):
        PricedModel().invoke(messages)
        return super()._answer(schema, messages)


def failing_on(title):
    """An extractor answering "unknown" everywhere, except that it fails on the posting `title`."""
    def answer(schema, prompt):
        if title in prompt:
            raise ValueError("model answered outside the schema")
        return unknown_features(schema, prompt)
    return ScriptedModel(answer)


def test_a_failing_call_is_an_error_and_the_run_goes_on(repository):
    calls = extractor_benchmark.extract_postings(repository, failing_on("Data Engineer"),
                                       DEFAULT_FEATURE_SET)
    assert [call.posting for call in calls] == ["p1", "p2", "p3"]
    assert [call.error for call in calls] == [None, "model answered outside the schema", None]
    assert calls[1].values is None
    assert set(calls[0].values) == {feature.id for feature in DEFAULT_FEATURE_SET}


def test_limit_takes_the_first_postings_in_id_order(repository):
    calls = extractor_benchmark.extract_postings(repository, ScriptedModel(unknown_features),
                                       DEFAULT_FEATURE_SET, limit=2)
    assert [call.posting for call in calls] == ["p1", "p2"]


def test_each_call_is_metered_for_cost_and_wall_clock_latency(repository):
    calls = extractor_benchmark.extract_postings(repository, PricedScripted(unknown_features),
                                       DEFAULT_FEATURE_SET)
    assert [(call.cost, call.uncosted) for call in calls] == [(0.25, 0)] * 3
    assert all(call.latency_s > 0 for call in calls)


def test_approach_hashes_stay_equal_for_equal_input_and_follow_the_input():
    first = extractor_benchmark.approach_parameters(DEFAULT_FEATURE_SET)
    assert extractor_benchmark.approach_parameters(DEFAULT_FEATURE_SET) == first
    other_instructions = extractor_benchmark.approach_parameters(DEFAULT_FEATURE_SET,
                                                       instructions=INSTRUCTIONS + " Be brief.")
    other_features = extractor_benchmark.approach_parameters(DEFAULT_FEATURE_SET[:-1])
    assert other_instructions["instructions_hash"] != first["instructions_hash"]
    assert other_instructions["feature_set_hash"] == first["feature_set_hash"]
    assert other_features["feature_set_hash"] != first["feature_set_hash"]
    assert other_features["instructions_hash"] == first["instructions_hash"]


def test_approach_names_the_apps_commit_and_none_outside_git(tmp_path):
    assert re.fullmatch(r"[0-9a-f]{40}", extractor_benchmark.approach_parameters([])["commit"])
    assert extractor_benchmark.approach_parameters([], root=tmp_path)["commit"] is None


@pytest.fixture
def data_root(tmp_path):
    """An empty directory standing in for a data repository, with `tmp_path / "state"` beside it."""
    (tmp_path / "data").mkdir()
    return tmp_path / "data"


def test_state_directory_inside_this_repository_is_refused(data_root):
    with pytest.raises(extractor_benchmark.StateDirectoryError,
                       match="STATE_DIRECTORY.*this repository"):
        extractor_benchmark.check_state_directory(REPOSITORY_ROOT / "state", data_root)


def test_state_directory_inside_the_data_repository_is_refused(data_root):
    with pytest.raises(extractor_benchmark.StateDirectoryError,
                       match="STATE_DIRECTORY.*data repository"):
        extractor_benchmark.check_state_directory(data_root / "state", data_root)


def test_state_directory_reached_through_a_symlink_or_dots_is_refused(data_root, tmp_path):
    (tmp_path / "link").symlink_to(data_root)
    for sneaky in (tmp_path / "link" / "state", data_root / "x" / ".." / "state"):
        with pytest.raises(extractor_benchmark.StateDirectoryError, match="data repository"):
            extractor_benchmark.check_state_directory(sneaky, data_root)


def test_state_directory_beside_the_repositories_is_accepted(data_root, tmp_path):
    extractor_benchmark.check_state_directory(tmp_path / "state", data_root)


SENTINEL_TEXT = "SENTINEL-POSTING-TEXT"
SENTINEL_VALUE = "SENTINEL-EXTRACTED-ROLE"
NOW = datetime(2026, 10, 28, 9, 30, 15, tzinfo=UTC)


def settings(tmp_path) -> Settings:
    return Settings(_env_file=None, state_directory=tmp_path / "state")


@pytest.fixture
def labelled(repository, data_repository):
    """The three-posting repository with labels for p1 and p2, p1's text a sentinel."""
    write_json(data_repository / "postings/p1.json", {**POSTING, "text": SENTINEL_TEXT})
    write_json(data_repository / "extraction-labels.json", {
        "schema_version": "1",
        "labels": {"p1": {"seniority": "senior"}, "p2": {"seniority": "junior"}}})
    return load(data_repository)


def extractor(role=SENTINEL_VALUE):
    """p1 is senior, the others junior, all with `role` as role type; p3's call fails, with the
    sentinel text in its error."""
    def answer(schema, prompt):
        if "Cloud Engineer" in prompt:
            raise ValueError(f"cannot parse {SENTINEL_TEXT}")
        senior = "Backend Engineer" in prompt
        return unknown_features(schema, prompt) | {"seniority": "senior" if senior else "junior",
                                                   "role_type": role}
    return PricedScripted(answer)


def run_benchmark(repository, tmp_path, deepeval, **changes):
    arguments = {"model": "vendor/model-a", "base_url": None, "chat": extractor(), "limit": None,
                 "now": NOW, "langfuse": None} | changes
    return extractor_benchmark.run(repository, settings(tmp_path), deepeval, **arguments)


def test_a_run_stores_one_record_with_figures_and_parameters_only(labelled, tmp_path, deepeval):
    record, errors = run_benchmark(labelled, tmp_path, deepeval)
    state = extractor_benchmark.state_path(settings(tmp_path), labelled.root)
    [line] = (state / "benchmark" / "records.jsonl").read_text().splitlines()
    stored = json.loads(line)
    assert stored == record
    assert (stored["run_id"], stored["role"], stored["model"], stored["base_url"]) == (
        "20261028T093015Z-vendor_model-a", "extractor", "vendor/model-a", None)
    assert stored["date"] == "2026-10-28T09:30:15+00:00"
    assert stored["data"] == state.name
    assert {"instructions_hash", "feature_set_hash", "commit"} <= stored.keys()
    assert (stored["postings"], stored["cost_per_posting_usd"], stored["uncosted_calls"]) == (
        3, 0.25, 0)
    assert stored["mean_latency_s"] > 0
    assert stored["errors"] == [{"posting": "p3", "error_type": "ValueError"}]
    assert stored["metrics"] == [{"name": "extraction accuracy", "value": 1.0, "cases": 2,
                                  "per_feature": {"seniority": {"value": 1.0, "cases": 2}}}]
    assert errors == {"p3": f"cannot parse {SENTINEL_TEXT}"}
    assert SENTINEL_TEXT not in line and SENTINEL_VALUE not in line


def test_the_values_file_holds_the_extracted_values_and_the_error_messages(labelled, tmp_path,
                                                                           deepeval):
    record, _ = run_benchmark(labelled, tmp_path, deepeval)
    state = extractor_benchmark.state_path(settings(tmp_path), labelled.root)
    stored = json.loads((state / "benchmark" / "runs" / f"{record['run_id']}.json").read_text())
    assert stored["run_id"] == record["run_id"]
    assert stored["values"]["p1"]["seniority"] == "senior"
    assert stored["values"]["p1"]["role_type"] == SENTINEL_VALUE
    assert "p3" not in stored["values"]
    assert stored["errors"] == {"p3": f"cannot parse {SENTINEL_TEXT}"}


def test_a_run_without_labels_stores_no_accuracy(repository, tmp_path, deepeval):
    record, _ = run_benchmark(repository, tmp_path, deepeval)
    assert record["metrics"] == []


def test_runs_append_and_an_existing_run_file_is_never_overwritten(labelled, tmp_path, deepeval):
    run_benchmark(labelled, tmp_path, deepeval)
    run_benchmark(labelled, tmp_path, deepeval, model="vendor/model-b")
    with pytest.raises(FileExistsError, match="20261028T093015Z-vendor_model-a"):
        run_benchmark(labelled, tmp_path, deepeval, chat=ScriptedModel(failing_answer))
    state = extractor_benchmark.state_path(settings(tmp_path), labelled.root)
    assert len((state / "benchmark" / "records.jsonl").read_text().splitlines()) == 2


def failing_answer(schema, prompt):
    raise AssertionError("no model call may happen for a refused run")


def unknown_choices(request, senior_in="Backend Engineer"):
    """A decision model answering every choice question "unknown", except seniority: "senior"
    for a posting whose message names `senior_in`, "junior" for the others."""
    text = request["messages"][-1]["content"]
    return {question: {"type": "choice", "choice": (
        ("senior" if senior_in in text else "junior") if question == "seniority" else "unknown")}
        for question in request["response_format"]["questions"]}


def decision_run(repository, tmp_path, deepeval, **changes):
    """A run of the stub decision model; `client.requests` holds what it was asked."""
    client = FakeDecider(unknown_choices)
    record, errors = run_benchmark(repository, tmp_path, deepeval, model="typesafe/jev",
                                   chat=Decider(client, "typesafe/jev"), role="decider", **changes)
    return record, errors, client


def test_a_decision_model_is_asked_the_categorical_features_only(labelled, tmp_path, deepeval):
    record, errors, client = decision_run(labelled, tmp_path, deepeval)
    categorical = {feature.id for feature in DEFAULT_FEATURE_SET if feature.type == "categorical"}
    assert [set(request["response_format"]["questions"]) for request in client.requests] == [
        categorical] * 3
    assert (record["role"], record["model"], errors) == ("decider", "typesafe/jev", {})
    state = extractor_benchmark.state_path(settings(tmp_path), labelled.root)
    stored = json.loads((state / "benchmark" / "runs" / f"{record['run_id']}.json").read_text())
    assert set(stored["values"]["p1"]) == categorical
    assert stored["values"]["p1"]["seniority"] == "senior"
    assert record["cost_per_posting_usd"] == 0.001


def test_a_decision_run_is_not_scored_on_labels_for_features_it_does_not_answer(
        labelled, data_repository, tmp_path, deepeval):
    write_json(data_repository / "extraction-labels.json", {
        "schema_version": "1",
        "labels": {"p1": {"seniority": "senior", "role_type": "backend"},
                   "p2": {"role_type": "data"}}})
    record, _, _ = decision_run(load(data_repository), tmp_path, deepeval)
    assert record["metrics"] == [{"name": "extraction accuracy", "value": 1.0, "cases": 1,
                                  "per_feature": {"seniority": {"value": 1.0, "cases": 1}}}]


def test_a_decision_run_and_an_extractor_run_compare_on_the_common_features(labelled, tmp_path,
                                                                           deepeval):
    extractor_record, _ = run_benchmark(labelled, tmp_path, deepeval)
    decision_record, _, _ = decision_run(labelled, tmp_path, deepeval)
    state = extractor_benchmark.state_path(settings(tmp_path), labelled.root)
    result = extractor_benchmark.compare(state, [extractor_record["run_id"],
                                                 decision_record["run_id"]], {})
    assert set(result["agreement"]) == {"seniority", "remote_option", "company_stage"}


def test_a_decision_run_names_its_own_instructions(labelled, tmp_path, deepeval):
    extractor_record, _ = run_benchmark(labelled, tmp_path, deepeval)
    decision_record, _, _ = decision_run(labelled, tmp_path, deepeval)
    assert decision_record["instructions_hash"] != extractor_record["instructions_hash"]
    assert decision_record["feature_set_hash"] == extractor_record["feature_set_hash"]


def test_the_table_of_a_decision_run_says_so(labelled, tmp_path, deepeval):
    table = extractor_benchmark.format_table(*decision_run(labelled, tmp_path, deepeval)[:2])
    assert "decision model" in table and "typesafe/jev" in table


def test_the_table_names_the_metric_with_case_counts_and_lists_the_errors(labelled, tmp_path,
                                                                          deepeval):
    table = extractor_benchmark.format_table(*run_benchmark(labelled, tmp_path, deepeval))
    assert "vendor/model-a" in table
    assert "extraction accuracy" in table
    assert re.search(r"seniority\s+1\.00\s+\(2 cases\)", table)
    assert re.search(r"cost per posting\s+\$0\.2500", table)
    assert re.search(r"mean latency\s+\d+\.\d+ s", table)
    assert re.search(r"postings\s+3", table)
    assert f"p3: cannot parse {SENTINEL_TEXT}" in table


def test_the_table_says_when_no_accuracy_was_computed(repository, tmp_path, deepeval):
    table = extractor_benchmark.format_table(*run_benchmark(repository, tmp_path, deepeval))
    assert "no accuracy computed: the data repository holds no extraction labels" in table


class StubLangfuse:
    """Stands in for the Langfuse client: records each `run_experiment` call with what its task
    returns per item and what its run-level evaluators score, or raises `failure`."""

    created: list = []

    def __init__(self, failure=None, **connection):
        self.failure, self.connection = failure, connection
        self.experiments, self.flushed = [], 0
        StubLangfuse.created.append(self)

    def run_experiment(self, **call):
        if self.failure:
            raise self.failure
        outputs = {item["input"]: call["task"](item=item) for item in call["data"]}
        scores = [score for evaluator in call["run_evaluators"]
                  for score in evaluator(item_results=[])]
        self.experiments.append({**call, "outputs": outputs, "scores": scores})

    def flush(self):
        self.flushed += 1


def test_a_run_is_mirrored_to_langfuse_after_the_record_is_written(labelled, tmp_path, deepeval):
    client = StubLangfuse()
    record, _ = run_benchmark(labelled, tmp_path, deepeval, langfuse=client)
    [experiment] = client.experiments
    assert (experiment["name"], experiment["run_name"]) == ("extractor-benchmark",
                                                           record["run_id"])
    assert [(item["input"], item["expected_output"]) for item in experiment["data"]] == [
        ("p1", {"seniority": "senior"}), ("p2", {"seniority": "junior"}), ("p3", None)]
    assert experiment["outputs"]["p1"]["seniority"] == "senior"
    assert "cannot parse" in experiment["outputs"]["p3"]["error"]
    scores = {score.name: score for score in experiment["scores"]}
    assert (scores["accuracy/seniority"].value, scores["accuracy/seniority"].comment) == (
        1.0, "extraction accuracy, 2 cases")
    assert scores["cost_per_posting_usd"].value == 0.25
    assert scores["latency_mean_s"].value == record["mean_latency_s"]
    assert experiment["metadata"]["model"] == "vendor/model-a"
    assert client.flushed == 1
    state = extractor_benchmark.state_path(settings(tmp_path), labelled.root)
    assert (state / "benchmark" / "records.jsonl").exists()


def test_an_empty_answer_is_replayed_as_empty_not_as_an_error():
    client = StubLangfuse()
    record = {"metrics": [], "cost_per_posting_usd": None, "mean_latency_s": None, "run_id": "r",
              "role": "extractor", "model": "m", "base_url": None, "instructions_hash": "h",
              "feature_set_hash": "f", "commit": None}
    extractor_benchmark._mirror(client, record, {"p1": {}}, {}, {})
    assert client.experiments[0]["outputs"] == {"p1": {}}


def test_no_langfuse_client_means_no_mirror_and_no_error(labelled, tmp_path, deepeval):
    record, _ = run_benchmark(labelled, tmp_path, deepeval, langfuse=None)
    assert record["postings"] == 3
    assert extractor_benchmark.langfuse_client(Settings(_env_file=None)) is None
    only_public = Settings(_env_file=None, langfuse_public_key="pk")
    assert extractor_benchmark.langfuse_client(only_public) is None


def test_an_unreachable_langfuse_only_warns(labelled, tmp_path, deepeval, capsys):
    client = StubLangfuse(failure=ConnectionError("langfuse is down"))
    record, errors = run_benchmark(labelled, tmp_path, deepeval, langfuse=client)
    captured = capsys.readouterr()
    assert "warning: Langfuse mirror failed: langfuse is down" in captured.err
    state = extractor_benchmark.state_path(settings(tmp_path), labelled.root)
    assert json.loads((state / "benchmark" / "records.jsonl").read_text()) == record
    assert extractor_benchmark.format_table(record, errors)


@pytest.fixture
def cli(monkeypatch, tmp_path_factory, labelled, deepeval):
    """`main` against the `labelled` repository with settings for EXTRACTOR_MODEL
    `vendor/configured` at `https://router.example/v1` and a state directory outside the data
    repository (`cli.state`), the stub extractor and the loaded DeepEval; `cli.built` records each
    (model, base URL) a client was built for, `cli.loaded` each state directory DeepEval was
    loaded for."""
    built, loaded, decided = [], [], []
    state = tmp_path_factory.mktemp("cli-state")
    config = {"state_directory": state, "extractor_model": "vendor/configured",
              "extractor_base_url": "https://router.example/v1",
              "decider_model": "vendor/jev", "llm_base_url": "https://router.example/v1"}

    def run_main(*arguments, **changes):
        monkeypatch.setattr(extractor_benchmark, "Settings",
                            lambda: Settings(_env_file=None, **config | changes))
        extractor_benchmark.main(["--data", str(labelled.root), *arguments])

    monkeypatch.setattr(extractor_benchmark, "model_client",
                        lambda model, base_url, settings: built.append((model, base_url))
                        or extractor("other role" if model == "vendor/y" else SENTINEL_VALUE))
    monkeypatch.setattr(extractor_benchmark, "load_deepeval",
                        lambda state: loaded.append(state) or deepeval)
    monkeypatch.setattr(extractor_benchmark, "decider_client",
                        lambda model, base_url, settings: decided.append((model, base_url))
                        or Decider(FakeDecider(unknown_choices), model))
    run_main.built, run_main.loaded, run_main.state = built, loaded, state
    run_main.decided = decided
    return run_main


def test_main_runs_the_decision_model_for_the_decider_role(cli, capsys):
    cli("--role", "decider", "--limit", "2")
    assert cli.decided == [("vendor/jev", "https://router.example/v1")] and cli.built == []
    output = capsys.readouterr().out
    assert "vendor/jev" in output and "decision model" in output
    assert re.search(r"postings\s+2\b", output)


def test_main_runs_another_decision_model_for_one_run(cli):
    cli("--role", "decider", "--model", "typesafe/jev-1.14.0")
    assert cli.decided == [("typesafe/jev-1.14.0", "https://router.example/v1")]


def test_main_runs_the_configured_extractor_and_prints_the_table(cli, capsys):
    cli()
    assert cli.built == [("vendor/configured", "https://router.example/v1")]
    assert len(cli.loaded) == 1 and cli.loaded[0].parent == cli.state
    output = capsys.readouterr().out
    assert "vendor/configured" in output and "extraction accuracy" in output


def test_main_mirrors_to_langfuse_when_both_keys_are_set(cli, monkeypatch):
    StubLangfuse.created = []
    monkeypatch.setattr(extractor_benchmark, "Langfuse", StubLangfuse)
    cli(langfuse_public_key="pk", langfuse_secret_key="sk", langfuse_base_url="https://lf.example")
    [client] = StubLangfuse.created
    assert client.connection == {"public_key": "pk", "secret_key": "sk",
                                 "base_url": "https://lf.example"}
    assert len(client.experiments) == 1


def test_main_makes_no_langfuse_client_without_keys(cli, monkeypatch):
    StubLangfuse.created = []
    monkeypatch.setattr(extractor_benchmark, "Langfuse", StubLangfuse)
    cli()
    assert StubLangfuse.created == []


def test_main_runs_another_model_for_one_run(cli, capsys):
    cli("--model", "vendor/other", "--base-url", "https://other.example/v1", "--limit", "2")
    assert cli.built == [("vendor/other", "https://other.example/v1")]
    output = capsys.readouterr().out
    assert "vendor/other" in output and re.search(r"postings\s+2\b", output)


def test_main_keeps_the_configured_base_url_for_a_named_model(cli):
    cli("--model", "vendor/other")
    assert cli.built == [("vendor/other", "https://router.example/v1")]


def test_main_without_any_model_names_the_settings(cli, capsys):
    with pytest.raises(SystemExit):
        cli(extractor_model=None)
    assert "EXTRACTOR_MODEL or LLM_MODEL is not set" in capsys.readouterr().err
    assert cli.built == []


@pytest.mark.parametrize("modes", [(), ("--history",), ("--compare", "a", "b"),
                                   ("--settle", "missing.json")])
@pytest.mark.parametrize("where", ["this repository", "the data repository"])
def test_main_refuses_a_state_directory_inside_a_repository_before_any_work(
        cli, labelled, capsys, where, modes):
    inside = (REPOSITORY_ROOT if where == "this repository" else labelled.root) / "state-x"
    with pytest.raises(SystemExit):
        cli(*modes, state_directory=inside)
    assert "STATE_DIRECTORY" in capsys.readouterr().err
    assert (cli.built, cli.loaded) == ([], [])
    assert not inside.exists()


def stored_run_ids(cli, labelled):
    state = extractor_benchmark.state_path(Settings(_env_file=None, state_directory=cli.state),
                                 labelled.root)
    return [record["run_id"] for record in extractor_benchmark.read_records(state)]


def test_main_lists_the_stored_runs_without_building_a_model(cli, capsys):
    cli("--model", "vendor/x")
    cli("--model", "vendor/y")
    capsys.readouterr()
    built = len(cli.built)
    cli("--history")
    output = capsys.readouterr().out
    assert "vendor/x" in output and "vendor/y" in output and len(cli.built) == built


def test_main_compares_two_stored_runs_and_writes_the_disagreements(cli, labelled, capsys):
    cli("--model", "vendor/x")
    cli("--model", "vendor/y")
    capsys.readouterr()
    cli("--compare", *stored_run_ids(cli, labelled))
    output = capsys.readouterr().out
    assert re.search(r"role_type\s+0\.00\s+\(2 postings\)", output)
    [path] = re.findall(r"disagreements file: (\S+)", output)
    listed = json.loads(Path(path).read_text())
    assert {(item["posting"], item["feature"]) for item in listed} == {
        ("p1", "role_type"), ("p2", "role_type")}


def test_main_stops_a_comparison_of_fewer_than_two_runs(cli, labelled, capsys):
    cli("--model", "vendor/x")
    capsys.readouterr()
    with pytest.raises(SystemExit):
        cli("--compare", *stored_run_ids(cli, labelled))
    assert "needs at least two runs" in capsys.readouterr().err


def test_main_settles_a_filled_disagreements_file(cli, labelled, capsys, tmp_path):
    file = tmp_path / "filled.json"
    file.write_text(json.dumps([
        {"posting": "p1", "feature": "role_type", "runs": {}, "label": "backend"},
        {"posting": "p2", "feature": "role_type", "runs": {}, "label": None}]))
    cli("--settle", str(file))
    assert "merged 1 label" in capsys.readouterr().out
    assert load(labelled.root).extraction_labels.labels["p1"]["role_type"] == "backend"


SCORE = {"run_id": "run-1", "hyperparameters": {"model": "m"}}


def test_no_labels_give_no_accuracy(deepeval):
    extracted = {"p1": {"seniority": "senior"}}
    assert accuracy.score_accuracy(deepeval, extracted, {}, **SCORE) == {}
    assert accuracy.score_accuracy(deepeval, extracted, {"p2": {"seniority": "senior"}},
                                   **SCORE) == {}


def test_labels_give_accuracy_per_feature_with_case_counts(deepeval):
    extracted = {"p1": {"seniority": "senior", "tech_stack": ["go", "Python"], "role": "Backend"},
                 "p2": {"seniority": "junior", "tech_stack": ["go"], "role": "Data"},
                 "p3": None, "p4": {"seniority": "senior"}}
    labels = {"p1": {"seniority": "senior", "tech_stack": ["python", "go"], "role": "backend"},
              "p2": {"seniority": "senior", "tech_stack": ["go"]},
              "p3": {"seniority": "lead"}}
    assert accuracy.score_accuracy(deepeval, extracted, labels, **SCORE) == {
        "seniority": {"accuracy": 1 / 3, "cases": 3},
        "tech_stack": {"accuracy": 1.0, "cases": 2},
        "role": {"accuracy": 1.0, "cases": 1}}


def test_scoring_prints_nothing_of_deepevals_own_report(deepeval, capfd):
    """DeepEval's report would put the extracted and expected values on the terminal."""
    accuracy.score_accuracy(deepeval, {"p1": {"seniority": "SENTINEL-WRONG"}},
                            {"p1": {"seniority": "senior"}}, **SCORE)
    captured = capfd.readouterr()
    assert (captured.out, captured.err) == ("", "")


def test_a_missing_feature_in_an_answer_is_wrong(deepeval):
    assert accuracy.score_accuracy(deepeval, {"p1": {"seniority": "senior"}},
                                   {"p1": {"remote": True}}, **SCORE) == {
        "remote": {"accuracy": 0.0, "cases": 1}}
