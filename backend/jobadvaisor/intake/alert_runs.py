"""The background run of the entries chosen from an alert mail
(`openspec/changes/archive/2026-11-16-alert-mail-intake/design.md` → Run): one entry after the
other through the normal intake of a link, one run at a time, state in memory only (a restart
forgets it)."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from pydantic import ValidationError

from jobadvaisor.intake.company_facts import HOST_SPACING_SECONDS, Throttle
from jobadvaisor.intake.duplicates import normalize_url
from jobadvaisor.intake.fetch import guarded_link, host_throttle
from jobadvaisor.intake.ladder import gone_disputed
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
    duplicate_by}`, `{state: "closed", attempts}` when the link is gone and no other source
    holds the posting, or `{state: "failed"}` with the ladder's `attempts` (and `unclear: true`
    when the link answered 404 or 410 but another answer disputes it, `gone_disputed`) or a
    `reason` (a `ValueError`'s text, else the exception's type name). Never raises."""
    token = guarded_link.set(entry.url)
    try:
        posting_id, _, duplicate_by, _ = add_from_url(intake, entry.url,
                                                     allow_text_duplicate=entry.force)
    except PostingNotFoundError as error:
        outcome = {"state": "closed" if error.closed else "failed", "attempts": error.attempts}
        if gone_disputed(error.attempts, entry.url):
            outcome["unclear"] = True
        return outcome
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
    """Starts and reads alert runs into `intake`, one at a time, state in memory only. Every
    request of a run's intake waits on `throttle` (default: one request per host per
    `HOST_SPACING_SECONDS`) through `fetch.host_throttle`; tests pass one on a fake clock."""

    def __init__(self, intake: Intake, throttle: Throttle | None = None):
        self._intake = intake
        self._throttle = throttle or Throttle(HOST_SPACING_SECONDS)
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
        try:
            self._executor.submit(self._run, run_id, entries)
        except Exception:
            with self._lock:
                self._computing = None
                del self._state[run_id]
            raise
        return run_id

    def read(self, run_id: str) -> dict | None:
        """A copy of the run's state, or `None` for an unknown ID: `run_id`, `status`
        (`running`, `done`, `failed`), `error` (the exception's type name when the run
        crashed), `total`, `done` (entries ended, closed ones included), and `entries` in
        order, each `{url, title, state}` with `state` one of `waiting`, `running`, `stored`,
        `duplicate`, `closed`, `failed`, plus the outcome's fields (`add_entry`). An entry whose
        link (`normalize_url`) an earlier entry already put through intake is not fetched: it
        carries that entry's outcome fields and `same_as`, the earlier entry's index."""
        with self._lock:
            state = self._state.get(run_id)
            if state is None:
                return None
            entries = [dict(entry) for entry in state["entries"]]
            done = sum(entry["state"] in ("stored", "duplicate", "closed", "failed")
                       for entry in entries)
            return state | {"entries": entries, "done": done}

    def _run(self, run_id: str, entries: list[RunEntry]) -> None:
        status, error = "done", None
        seen: dict[str, int] = {}  # link key → index of the entry that was fetched for it
        try:
            for index, entry in enumerate(entries):
                key = normalize_url(entry.url)
                if key in seen:
                    with self._lock:
                        shown = self._state[run_id]["entries"]
                        shown[index] |= {name: value for name, value in shown[seen[key]].items()
                                         if name not in ("url", "title")} | {"same_as": seen[key]}
                    continue
                seen[key] = index
                with self._lock:
                    self._state[run_id]["entries"][index]["state"] = "running"
                token = host_throttle.set(self._throttle)
                try:
                    outcome = add_entry(self._intake, entry)
                finally:
                    host_throttle.reset(token)
                with self._lock:
                    self._state[run_id]["entries"][index] |= outcome
        except Exception as crash:  # the thread must not die silently
            status, error = "failed", type(crash).__name__
        finally:
            with self._lock:
                self._state[run_id] |= {"status": status, "error": error}
                self._computing = None
