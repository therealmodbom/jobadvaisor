"""The scoring eval's harness, with fake models. The eval itself makes real calls and runs only
through `python -m jobadvaisor.evals`."""

from conftest import FakeStructuredModel
from langchain_core.embeddings import DeterministicFakeEmbedding
from test_eval_agent import PricedModel

from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import load
from jobadvaisor.evals.scoring import mixed_chip_citations, precision_at_k, run, time_split
from jobadvaisor.index import LabelIndex
from jobadvaisor.tools.guard import ContentGuard


class PricedJudge(FakeStructuredModel):
    """A judge whose every answer costs one `PricedModel` call (0.25)."""

    def _answer(self, schema, messages):
        PricedModel().invoke(messages)
        return super()._answer(schema, messages)


DEMO = load(FIXTURE_DIRECTORY)
GUARD = ContentGuard(None, {})  # every demo posting carries a clean stored guard


def test_time_split_holds_out_the_latest_usable_labels():
    split = time_split(DEMO, held_out=15)
    assert (len(split.held_out), len(split.training)) == (15, 111)
    rated = {posting_id: DEMO.labels[posting_id].rated_at
             for posting_id in split.held_out + split.training}
    assert all(rated[posting_id] < split.cut_off for posting_id in split.training)
    assert all(rated[posting_id] >= split.cut_off for posting_id in split.held_out)
    assert all(DEMO.labels[posting_id].kind != "imported_not_preference" for posting_id in rated)


def test_precision_at_k_counts_positives_among_the_top_k():
    assert precision_at_k(["positive", "negative", "positive", "positive"], k=2) == 0.5
    assert precision_at_k(["positive"], k=5) == 1.0


def test_report_and_no_example_from_after_the_cut_off(tmp_path):
    index = LabelIndex(tmp_path / "chroma", DeterministicFakeEmbedding(size=16), "fake-16")
    index.sync(DEMO)
    judge = FakeStructuredModel(*[{"score": score % 11, "reasoning": "r"}
                                  for score in range(15)])
    report = run(DEMO, index, GUARD, judge, "fake", k=5, held_out=15)
    split = time_split(DEMO, held_out=15)
    assert (report["k"], report["held_out"], report["cut_off"]) == (5, 15,
                                                                    split.cut_off.isoformat())
    assert 0 <= report["precision_at_k"] <= 1 and report["model"] == "fake"
    assert isinstance(report["mixed_chip_citations"], list)
    used = [example_id for row in report["scores"] for example_id in row["example_ids"]]
    assert used and all(DEMO.labels[example_id].rated_at < split.cut_off for example_id in used)
    assert set(used).isdisjoint(split.held_out)


def test_report_groups_the_held_out_scores_by_rating_level(tmp_path):
    index = LabelIndex(tmp_path / "chroma", DeterministicFakeEmbedding(size=16), "fake-16")
    index.sync(DEMO)
    judge = FakeStructuredModel(*[{"score": 4 + score % 3, "reasoning": "r"}
                                  for score in range(15)])
    report = run(DEMO, index, GUARD, judge, "fake", k=5, held_out=15)
    levels = report["by_level"]
    assert sum(entry["count"] for entry in levels.values()) == 15
    assert set(levels) <= {f"{verdict}/{strength}" for verdict in ("positive", "negative")
                           for strength in ("weak", "strong", "plain")}
    assert {"positive/strong", "negative/weak"} <= set(levels)
    for key, entry in levels.items():
        held = [row["score"] for row in report["scores"] if
                (f"{DEMO.labels[row['posting']].verdict}/"
                 f"{DEMO.labels[row['posting']].strength or 'plain'}") == key]
        assert entry["count"] == len(held)
        assert entry["mean_score"] == sum(held) / len(held)


def test_ranking_puts_the_highest_scores_first(tmp_path):
    index = LabelIndex(tmp_path / "chroma", DeterministicFakeEmbedding(size=16), "fake-16")
    index.sync(DEMO)
    judge = FakeStructuredModel(*[{"score": score // 2, "reasoning": "r"}
                                  for score in range(15)])
    report = run(DEMO, index, GUARD, judge, "fake", k=5, held_out=15)
    scores = [row["score"] for row in report["scores"]]
    assert scores == sorted(scores, reverse=True) and len(scores) == 15 and scores[0] == 7


def test_mixed_chip_citations_check_both_polarities_in_the_reasoning():
    labels = {chip.id: chip.label for chip in DEMO.policy_pack.reason_chips}
    polarity = {chip.id: chip.polarity for chip in DEMO.policy_pack.reason_chips}
    [mixed] = [pid for pid, label in DEMO.labels.items()
               if {polarity[chip] for chip in label.chips} == {"positive", "negative"}]
    chips = DEMO.labels[mixed].chips
    both = " und ".join(labels[chip] for chip in chips)
    rows = [{"posting": "a", "example_ids": [mixed], "reasoning": f"Wegen {both}."},
            {"posting": "b", "example_ids": [mixed], "reasoning": f"Nur {labels[chips[0]]}."},
            {"posting": "c", "example_ids": [], "reasoning": both}]
    found = mixed_chip_citations(DEMO, rows)
    assert [(item["posting"], item["cites_both"]) for item in found] == [("a", True),
                                                                          ("b", False)]
    assert found[1]["cited"] == [labels[chips[0]]]


def test_mixed_chip_citations_match_inflected_and_ignore_generic_words():
    [mixed] = [pid for pid, label in DEMO.labels.items() if label.chips == ["remote-possible",
                                                                            "wrong-stack"]]
    rows = [{"posting": "inflected", "example_ids": [mixed],
             "reasoning": "trotz falschem Tech-Stack wegen Remote positiv bewertet"},
            {"posting": "generic", "example_ids": [mixed],
             "reasoning": "dort war Hybridarbeit möglich, der Stack passt nicht"},
            {"posting": "negative only", "example_ids": [mixed],
             "reasoning": "falscher Stack, wie auch bei demo-036"}]
    found = mixed_chip_citations(DEMO, rows)
    assert [(item["posting"], item["cites_both"]) for item in found] == [
        ("inflected", True), ("generic", False), ("negative only", False)]
    assert found[2]["cited"] == ["falscher Tech-Stack"]


def test_report_carries_the_cost_per_posting(tmp_path):
    index = LabelIndex(tmp_path / "chroma", DeterministicFakeEmbedding(size=16), "fake-16")
    index.sync(DEMO)
    judge = PricedJudge(*[{"score": 5, "reasoning": "r"} for _ in range(15)])
    report = run(DEMO, index, GUARD, judge, "fake", k=5, held_out=15)
    assert report["cost_per_posting_usd"] == 0.25 and report["uncosted_calls"] == 0


def test_too_few_labels_are_skipped_with_the_reason(tmp_path, data_repository):
    repository = load(data_repository)
    index = LabelIndex(tmp_path / "chroma", DeterministicFakeEmbedding(size=16), "fake-16")
    report = run(repository, index, GUARD, FakeStructuredModel(), "fake", k=5, held_out=15)
    assert report["skipped"] == "1 usable labels, need more than the 15 held out"
