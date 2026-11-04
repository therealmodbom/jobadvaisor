"""The list import (`design.md` → The list import): the entries of an uploaded list go through
the normal intake one after the other in a background thread, one import at a time. State
lives in memory only: counts, the entries that were not imported (row text, link, reason) and
the IDs of postings whose status differs from the list's."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from pydantic import ValidationError

from jobadvaisor.data.models import ImportMapping
from jobadvaisor.data.writer import read_posting, update_posting, write_import_mapping
from jobadvaisor.intake.duplicates import normalize_url
from jobadvaisor.intake.entries import Entry, mapped_status
from jobadvaisor.intake.ladder import GONE_OUTCOMES, is_gone
from jobadvaisor.intake.postings import Intake, PostingNotFoundError, add_from_url

OUTCOMES = ("imported", "duplicate", "skipped_status", "skipped_gone", "failed")
NOT_IMPORTED = ("skipped_status", "skipped_gone", "failed")


class ImportBusyError(Exception):
    """Another import is computing; `import_id` names it."""

    def __init__(self, import_id: str):
        self.import_id = import_id
        super().__init__(f"import {import_id} is still computing")


def import_entry(intake: Intake, entry: Entry,
                 mapping: ImportMapping) -> tuple[str, tuple[str, str] | None, str | None]:
    """Put one list entry through the intake and return `(outcome, discrepancy, reason)`: the
    outcome is one of `OUTCOMES`; the discrepancy `(posting_id, list_status)` for a duplicate
    by exact text, or by URL through the listed link itself (not a merely similar text, nor a
    URL the intake found elsewhere), whose stored status differs from the (non-empty) list
    status mapped by `mapping`, else `None`; the reason says why an entry was not imported
    (`None` for imported and duplicate).

    An entry whose status maps to skip is skipped without a fetch (reason: the status value),
    one answering 404/410 on the listed link is skipped as gone without looking for it
    elsewhere (reason: the HTTP outcome), any other failure is `failed` (reason: "kein Link",
    the last fetch outcome on the listed link, the error text of a `ValueError`, else the
    exception's type name, also for pydantic's `ValidationError`, whose text is multi-line).
    A new posting gets the origin mark and the mapped application status; a duplicate keeps
    the user's status and gets the origin mark only when the listed link is one of its URLs or
    it has no mark yet, so an entry never overwrites the mark of a posting found through
    another link. If that write fails after `add_from_url` stored the posting, it stays stored
    without its origin and counts as `failed`; a re-upload finds it as a duplicate and adds the
    origin. Never raises.
    """
    status = mapped_status(mapping, entry.status)
    if status == "skip":
        return "skipped_status", None, entry.status
    if entry.url is None:
        return "failed", None, "kein Link"
    try:
        posting_id, posting, duplicate_by, _ = add_from_url(intake, entry.url,
                                                            search_if_gone=False)
        listed = normalize_url(entry.url) in {normalize_url(url) for url in posting.urls}
        updates: dict[str, object] = {}
        if duplicate_by is None or listed or posting.origin is None:
            origin = {"table": entry.table, "fit": entry.assessment, "status": entry.status}
            updates["origin"] = {key: value for key, value in origin.items() if value is not None}
        if duplicate_by is None:
            updates["status"] = status
        if updates:
            update_posting(intake.root, posting_id, updates)
    except PostingNotFoundError as error:
        on_url = [a["outcome"] for a in error.attempts if a["url"] == entry.url]
        if is_gone(error.attempts, entry.url):
            return "skipped_gone", None, next(o for o in on_url if o in GONE_OUTCOMES)
        return "failed", None, (on_url or [str(error)])[-1]
    except ValidationError as error:  # a ValueError, but its text is multi-line
        return "failed", None, type(error).__name__
    except ValueError as error:  # includes NoPostingTextError
        return "failed", None, str(error)
    except Exception as error:  # one entry never stops the import
        return "failed", None, type(error).__name__
    if duplicate_by is None:
        return "imported", None, None
    # a merely similar text, or a URL found elsewhere, may be another posting
    same_posting = duplicate_by == "text" or (duplicate_by == "url" and listed)
    differs = same_posting and entry.status is not None and status != posting.status
    return "duplicate", (posting_id, status) if differs else None, None


class Imports:
    """Starts and reads list imports into `intake`, one at a time, state in memory only."""

    def __init__(self, intake: Intake):
        self._intake = intake
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._lock = threading.Lock()
        self._state: dict[str, dict] = {}
        self._computing: str | None = None

    def start(self, entries: list[Entry], mapping: ImportMapping, left_out: list[dict]) -> str:
        """Store `mapping` in the policy pack, import `entries` with it in the background and
        return the import's ID at once; `left_out` (`tables_left_out`) is kept for the report.
        Raises `ImportBusyError` while another import computes; the stored mapping is then
        left as it was."""
        import_id = uuid.uuid4().hex
        with self._lock:
            if self._computing:
                raise ImportBusyError(self._computing)
            write_import_mapping(self._intake.root, mapping)
            self._computing = import_id
            self._state[import_id] = {"import_id": import_id, "status": "running",
                                      "error": None, "total": len(entries),
                                      "counts": dict.fromkeys(OUTCOMES, 0), "not_imported": [],
                                      "discrepancies": {}, "tables_left_out": left_out}
        self._executor.submit(self._run, import_id, entries, mapping)
        return import_id

    def read(self, import_id: str) -> dict | None:
        """A copy of the import's state — `import_id`, `status` (`running`, `done`, `failed`),
        `error` (the exception's type name when the import crashed), `total`, `done` (entries
        processed), `counts` per outcome, `not_imported`, `conflicts` and `tables_left_out`
        (`[{name, entries}]`, fixed at start) — or `None` for an unknown ID.

        `not_imported` lists in list order every entry that was skipped or failed: `{row, url,
        outcome, reason}` (`url` is `null` for an entry without a link). `conflicts` lists the
        stored postings whose app status differs from the list's: `{posting_id, title, company,
        status, list_status}`, read from disk now. One whose status now equals the list's, or
        that no longer loads, is left out."""
        with self._lock:
            state = self._state.get(import_id)
            if state is None:
                return None
            counts = dict(state["counts"])
            not_imported = list(state["not_imported"])
            discrepancies = list(state["discrepancies"].items())
            state = {key: value for key, value in state.items()
                     if key not in ("discrepancies", "not_imported")}
        conflicts = []
        for posting_id, list_status in discrepancies:
            try:
                posting = read_posting(self._intake.root, posting_id)
            except (ValueError, OSError):
                continue
            if posting.status != list_status:
                conflicts.append({"posting_id": posting_id, "title": posting.title,
                                  "company": posting.company, "status": posting.status,
                                  "list_status": list_status})
        return state | {"counts": counts, "done": sum(counts.values()),
                        "not_imported": not_imported, "conflicts": conflicts}

    def _run(self, import_id: str, entries: list[Entry], mapping: ImportMapping) -> None:
        status, error = "done", None
        try:
            for entry in entries:
                outcome, discrepancy, reason = import_entry(self._intake, entry, mapping)
                with self._lock:
                    state = self._state[import_id]
                    state["counts"][outcome] += 1
                    if outcome in NOT_IMPORTED:
                        state["not_imported"].append({"row": entry.row, "url": entry.url,
                                                      "outcome": outcome, "reason": reason})
                    if discrepancy:  # a posting listed twice keeps the later status
                        state["discrepancies"][discrepancy[0]] = discrepancy[1]
        except Exception as crash:  # the thread must not die silently
            status, error = "failed", type(crash).__name__
        finally:
            with self._lock:
                self._state[import_id] |= {"status": status, "error": error}
                self._computing = None
