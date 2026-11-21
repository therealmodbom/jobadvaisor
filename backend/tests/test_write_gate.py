"""The write gate: every public writer function waits while the gate is held (`data-repository` →
Writes and backups never interleave)."""

import threading
from datetime import UTC, datetime

from conftest import POSTING

from jobadvaisor.api import app as app_module
from jobadvaisor.data import loader, writer
from jobadvaisor.data.models import (
    Availability,
    Company,
    Guard,
    ImportMapping,
    Label,
    Pool,
    PoolPass,
    PoolSettings,
    Posting,
    Score,
)

NOW = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
LABEL = Label(schema_version="1", kind="rating", verdict="negative", rated_at=NOW)
SCORE = Score(schema_version="1", score=7, reasoning="Fits.", scored_at=NOW)
COMPANY = Company(schema_version="1", name="Acme GmbH", size_class="51-200", source="linkedin",
                  source_url="https://www.linkedin.com/company/acme", fetched_at=NOW)
GUARD = Guard(flagged=False, checked_by="t", checked_at=NOW)
AVAILABILITY = Availability(state="closed", set_at=NOW, set_by="check")


def _writes(root):
    """Every public write function of the writer, as a no-argument call on `root`."""
    return {
        "write_label": lambda: writer.write_label(root, "p2", LABEL),
        "write_score": lambda: writer.write_score(root, "p2", SCORE),
        "write_company": lambda: writer.write_company(root, "acme", COMPANY),
        "write_pool": lambda: writer.write_pool(root, Pool(schema_version="1")),
        "write_guard": lambda: writer.write_guard(root, "p1", GUARD),
        "write_availability": lambda: writer.write_availability(root, "p1", AVAILABILITY, None),
        "create_posting": lambda: writer.create_posting(
            root, "new", Posting.model_validate(POSTING)),
        "update_posting": lambda: writer.update_posting(root, "p1", {"title": "Changed"}),
        "append_pass": lambda: writer.append_pass(
            root, PoolPass(finished_at=NOW, scored=1, corrections=0, rated=1)),
        "update_pool_settings": lambda: writer.update_pool_settings(root, PoolSettings()),
        "merge_extraction_labels": lambda: writer.merge_extraction_labels(root, {}),
        "write_login_wall_hosts": lambda: writer.write_login_wall_hosts(root, ["example.com"]),
        "write_import_mapping": lambda: writer.write_import_mapping(root, ImportMapping()),
    }


def test_every_public_write_function_waits_for_the_gate(data_repository):
    writes = _writes(data_repository)
    finished: dict[str, threading.Event] = {name: threading.Event() for name in writes}

    failures: dict[str, BaseException] = {}

    def run(name, call):
        try:
            call()
        except BaseException as error:  # noqa: BLE001 - reported by the assertion below
            failures[name] = error
        finally:
            finished[name].set()

    threads = [threading.Thread(target=run, args=item) for item in writes.items()]
    with writer.write_gate:
        for thread in threads:
            thread.start()
        for name, event in finished.items():
            assert not event.wait(0.2), f"{name} did not wait for the write gate"
    for thread in threads:
        thread.join(timeout=10)
    assert all(event.is_set() for event in finished.values())
    assert not failures, f"writes that failed once the gate was released: {failures}"


def _blocked_while_gated(call) -> object:
    """Run `call` in a thread while this one holds the gate; assert it waits, then returns its
    result once the gate is released."""
    done, result = threading.Event(), []

    def run():
        result.append(call())
        done.set()

    thread = threading.Thread(target=run)
    with writer.write_gate:
        thread.start()
        assert not done.wait(0.2), "the read did not wait for the write gate"
    assert done.wait(10)
    thread.join(10)
    return result[0]


def test_the_gate_lives_in_the_loader_and_the_writer_shares_it():
    assert writer.write_gate is loader.write_gate


def test_load_and_read_scores_wait_for_the_gate(data_repository):
    assert set(_blocked_while_gated(lambda: loader.load(data_repository)).postings) == {
        "p1", "p2"}
    assert _blocked_while_gated(lambda: writer.read_scores(data_repository)) == ({}, {})


def test_pool_state_holds_the_gate_across_its_three_reads(data_repository, monkeypatch):
    """A delete started while `pool_state` reads waits until all three reads are done, so the
    state shows the posting with its score or neither."""
    writer.write_score(data_repository, "p2", SCORE)
    deleted, seen = threading.Event(), []
    original = app_module.read_pool

    def read_pool_while_a_delete_waits(root):
        thread = threading.Thread(
            target=lambda: (writer.delete_posting(root, "p2"), deleted.set()))
        thread.start()
        seen.append(deleted.wait(0.2))  # the first two reads are done, the third is not
        return original(root)

    monkeypatch.setattr(app_module, "read_pool", read_pool_while_a_delete_waits)
    repository, scores, _, _ = app_module.pool_state(data_repository)
    assert seen == [False] and deleted.wait(10)
    assert "p2" in repository.postings and "p2" in scores


def test_merge_extraction_labels_still_loads_inside_the_gate(data_repository):
    merged = writer.merge_extraction_labels(data_repository, {"p1": {"role_type": "backend"}})
    assert merged.labels == {"p1": {"role_type": "backend"}}


def test_the_gate_is_reentrant():
    with writer.write_gate, writer.write_gate:
        pass


def test_the_old_locks_are_gone():
    assert not hasattr(writer, "_pool_lock")
    assert not hasattr(writer, "_update_lock")
