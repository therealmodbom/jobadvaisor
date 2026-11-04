"""The logistic-regression competitor, with a fake extractor. Live runs go through
`python -m jobadvaisor.evals`."""

from conftest import ScriptedModel

from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import load
from jobadvaisor.data.models import Feature
from jobadvaisor.evals import __main__ as cli
from jobadvaisor.evals import logistic
from jobadvaisor.evals.logistic import encoder, fit, predict, run
from jobadvaisor.evals.scoring import time_split
from jobadvaisor.settings import Settings
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.tools.prompts import posting_block

DEMO = load(FIXTURE_DIRECTORY)
GUARD = ContentGuard(None, {})  # every demo posting carries a clean stored guard


def extractor_knowing_verdicts(repository):
    """Answers remote_option "remote" for postings rated positive, "onsite" otherwise, and
    "unknown" for every other feature."""
    verdicts = {posting_block(posting): repository.labels[posting_id].verdict
                for posting_id, posting in repository.postings.items()
                if posting_id in repository.labels}

    def answer(schema, prompt):
        verdict = verdicts[prompt.split("\n\n<company_facts>")[0]]  # the facts follow the posting
        return {field.alias: ("remote" if verdict == "positive" else "onsite")
                if field.alias == "remote_option" else "unknown"
                for field in schema.model_fields.values()}
    return ScriptedModel(answer)


def test_encoder_one_hot_encodes_categories_and_lists_and_ignores_unknown():
    features = [Feature(id="mode", description="d", type="categorical", options=["a", "b"]),
                Feature(id="stack", description="d", type="list", options=["x", "y"]),
                Feature(id="paid", description="d", type="boolean")]
    encode = encoder(features, [{"mode": "a", "stack": ["x", "y"], "paid": True}])
    assert encode({"mode": "b", "stack": ["y"], "paid": False}) == [0, 1, 0, 1, 0, 1]
    assert encode({"mode": "unknown", "stack": "unknown", "paid": "unknown"}) == [0] * 6


def test_encoder_keeps_text_tokens_seen_in_at_least_three_training_rows():
    feature = Feature(id="role", description="d", type="text")
    rows = [{"role": "Backend engineering"}] * 3 + [{"role": "QA"}]
    encode = encoder([feature], rows)
    assert encode({"role": "backend, data"}) == [1, 0]
    assert encode({"role": "qa"}) == [0, 0]


def test_fit_separates_separable_data():
    weights = fit([[1, 0], [1, 0], [0, 1], [0, 1]], [1, 1, 0, 0])
    assert predict(weights, [1, 0]) > 0.8 > 0.2 > predict(weights, [0, 1])


def test_report_on_the_demo_persona_ranks_by_the_learned_feature():
    report = run(DEMO, GUARD, extractor_knowing_verdicts(DEMO), "fake", k=5, held_out=15)
    split = time_split(DEMO, 15)
    assert report["training_labels"] == len(split.training) == 111
    assert (report["k"], report["held_out"], report["cut_off"]) == (5, 15,
                                                                    split.cut_off.isoformat())
    assert report["precision_at_k"] == 1.0 and report["errors"] == []
    assert report["minimum_labels"] == 100


def test_too_few_training_labels_are_skipped_with_the_reason():
    report = run(DEMO, GUARD, extractor_knowing_verdicts(DEMO), "fake", held_out=15,
                 minimum_labels=200)
    assert report["skipped"] == "111 training labels, need at least 200"


def test_cli_passes_the_configured_minimum(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(cli, "Settings", lambda: Settings(_env_file=None, llm_model="fake",
                                                          competitor_min_labels=40))
    monkeypatch.setattr(cli, "chat_model", lambda role, settings: None)
    monkeypatch.setattr(logistic, "run", lambda *args, **options: seen.append(options) or {})
    cli.main(["--only", "logistic_regression"])
    assert seen == [{"minimum_labels": 40}]
    assert Settings(_env_file=None).competitor_min_labels == 100


def test_no_extraction_runs_below_the_minimum(data_repository):
    extractor = ScriptedModel(lambda schema, prompt: {})
    report = run(load(data_repository), GUARD, extractor, "fake", held_out=15)
    assert "skipped" in report and extractor.calls == []
