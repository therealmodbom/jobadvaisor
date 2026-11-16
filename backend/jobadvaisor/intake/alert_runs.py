"""The background run of the entries chosen from an alert mail
(`openspec/changes/alert-mail-intake/design.md` → Run): one entry after the other through the
normal intake of a link, one run at a time, state in memory only (a restart forgets it)."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from pydantic import ValidationError

from jobadvaisor.intake.fetch import guarded_link
from jobadvaisor.intake.postings import Intake, PostingNotFoundError, add_from_url


class AlertRunBusyError(Exception):
    """Another alert run is computing; `run_id` names it."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(f"alert run {run_id} is still computing")


@dataclass(frozen=True)
class RunEntry:
    """A chosen entry: its cleaned link, its title from the mail, and `force` when the user
    asked to store a text duplicate anyway."""

    url: str
    title: str
    force: bool = False


def add_entry(intake: Intake, entry: RunEntry) -> dict:
    """Put one entry through `add_from_url` with `guarded_link` set to its link, and return
    its outcome: `{state: "stored", posting_id}`, `{state: "duplicate", posting_id,
    duplicate_by}`, or `{state: "failed"}` with the ladder's `attempts` or a `reason` (a
    `ValueError`'s text, else the exception's type name). Never raises."""
    token = guarded_link.set(entry.url)
    try:
        posting_id, _, duplicate_by, _ = add_from_url(intake, entry.url,
                                                     allow_text_duplicate=entry.force)
    except PostingNotFoundError as error:
        return {"state": "failed", "attempts": error.attempts}
    except ValidationError as error:  # a ValueError, but its text is multi-line
        return {"state": "failed", "reason": type(error).__name__}
    except ValueError as error:  # includes NoPostingTextError
        return {"state": "failed", "reason": str(error)}
    except Exception as error:  # one entry never stops the run
        return {"state": "failed", "reason": type(error).__name__}
    finally:
        guarded_link.reset(token)
    if duplicate_by is None:
        return {"state": "stored", "posting_id": posting_id}
    return {"state": "duplicate", "posting_id": posting_id, "duplicate_by": duplicate_by}


class AlertRuns:
    """Starts and reads alert runs into `intake`, one at a time, state in memory only."""

    def __init__(self, intake: Intake):
        self._intake = intake
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._lock = threading.Lock()
        self._state: dict[str, dict] = {}
        self._computing: str | None = None

    def start(self, entries: list[RunEntry]) -> str:
        """Add `entries` in the background and return the run's ID at once. Raises
        `AlertRunBusyError` while another run computes."""
        run_id = uuid.uuid4().hex
        with self._lock:
            if self._computing:
                raise AlertRunBusyError(self._computing)
            self._computing = run_id
            self._state[run_id] = {
                "run_id": run_id, "status": "running", "error": None, "total": len(entries),
                "entries": [{"url": e.url, "title": e.title, "state": "waiting"} for e in entries]}
        self._executor.submit(self._run, run_id, entries)
        return run_id

    def read(self, run_id: str) -> dict | None:
        """A copy of the run's state, or `None` for an unknown ID: `run_id`, `status`
        (`running`, `done`, `failed`), `error` (the exception's type name when the run
        crashed), `total`, `done` (entries ended), and `entries` in order, each `{url, title,
        state}` with `state` one of `waiting`, `running`, `stored`, `duplicate`, `failed`, plus
        the outcome's fields (`add_entry`)."""
        with self._lock:
            state = self._state.get(run_id)
            if state is None:
                return None
            entries = [dict(entry) for entry in state["entries"]]
            done = sum(entry["state"] in ("stored", "duplicate", "failed") for entry in entries)
            return state | {"entries": entries, "done": done}

    def _run(self, run_id: str, entries: list[RunEntry]) -> None:
        status, error = "done", None
        try:
            for index, entry in enumerate(entries):
                with self._lock:
                    self._state[run_id]["entries"][index]["state"] = "running"
                outcome = add_entry(self._intake, entry)
                with self._lock:
                    self._state[run_id]["entries"][index] |= outcome
        except Exception as crash:  # the thread must not die silently
            status, error = "failed", type(crash).__name__
        finally:
            with self._lock:
                self._state[run_id] |= {"status": status, "error": error}
                self._computing = None
