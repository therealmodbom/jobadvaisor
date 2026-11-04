from conftest import AT, LABEL, PROFILE, write_json
from test_triage_graph import POLICY_PACK, Harness, add_posting

from jobadvaisor.data.loader import load
from jobadvaisor.triage.graph import run_config

NOT_PREFERENCE = {"schema_version": "1", "kind": "imported_not_preference", "rated_at": AT}


def batch(harness: Harness, run_id: str) -> set[str]:
    return set(harness.graph.get_state(run_config(run_id)).values["batch"])


def test_not_preference_record_is_never_an_example(tmp_path):
    root = tmp_path / "data"
    write_json(root / "profile.json", PROFILE)
    write_json(root / "policy-pack.json", POLICY_PACK)
    add_posting(root, "imported", "Backend Engineer")
    write_json(root / "labels/imported.json", NOT_PREFERENCE)
    add_posting(root, "rated", "Frontend Engineer")
    write_json(root / "labels/rated.json", LABEL)
    add_posting(root, "new", "Backend Engineer 6")
    harness = Harness(tmp_path, root)
    results = harness.start("run-1")["results"]
    assert set(results) == {"imported", "new"}  # no verdict = no rating, so it is scored
    assert results["new"]["example_ids"] == ["rated"]
    assert harness.index.posting_ids() == ["rated"]


def test_demo_run_uses_no_not_preference_record_as_an_example(tmp_path, demo_copy):
    repository = load(demo_copy)
    harness = Harness(tmp_path, demo_copy)
    results = harness.start("run-1")["results"]
    used = {example for result in results.values() for example in result.get("example_ids", [])}
    assert used and all(repository.labels[example].kind != "imported_not_preference"
                        for example in used)


def test_first_pass_takes_every_unrated_posting_and_the_next_only_the_unscored(tmp_path,
                                                                              demo_copy):
    repository = load(demo_copy)
    unlabeled = {posting_id for posting_id in repository.postings
                 if not (posting_id in repository.labels and repository.labels[posting_id].verdict)}
    harness = Harness(tmp_path, demo_copy)
    results = harness.start("run-1")["results"]
    assert batch(harness, "run-1") == unlabeled and len(unlabeled) == 24
    scored = {posting_id for posting_id, result in results.items()
              if result["status"] == "scored"}
    harness.start("run-2")
    assert scored and batch(harness, "run-2") == unlabeled - scored
    harness.start("run-3", rescore_unrated=True)
    assert batch(harness, "run-3") == unlabeled
