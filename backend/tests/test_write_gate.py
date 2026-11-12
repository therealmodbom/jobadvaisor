"""The write gate: every public writer function waits while the gate is held (`data-repository` →
Writes and backups never interleave)."""

import threading
from datetime import UTC, datetime

from conftest import POSTING

from jobadvaisor.data import writer
from jobadvaisor.data.models import (
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


def _writes(root):
    """Every public write function of the writer, as a no-argument call on `root`."""
    return {
        "write_label": lambda: writer.write_label(root, "p2", LABEL),
        "write_score": lambda: writer.write_score(root, "p2", SCORE),
        "write_company": lambda: writer.write_company(root, "acme", COMPANY),
        "write_pool": lambda: writer.write_pool(root, Pool(schema_version="1")),
        "write_guard": lambda: writer.write_guard(root, "p1", GUARD),
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


def test_the_gate_is_reentrant():
    with writer.write_gate, writer.write_gate:
        pass


def test_the_old_locks_are_gone():
    assert not hasattr(writer, "_pool_lock")
    assert not hasattr(writer, "_update_lock")
