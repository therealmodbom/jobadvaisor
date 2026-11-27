"""The background run of the entries chosen from an alert mail
(`openspec/changes/archive/2026-11-16-alert-mail-intake/design.md` → Run): one entry after the
other through the normal intake of a link, one run at a time, run state in memory only (a
restart forgets it). Every run keeps the list of unsettled links in the data repository
(`openspec/changes/182-unsettled-links-list/design.md` D3): its links wait from the start, each
ended entry settles or keeps its row, and the end turns the links it did not reach
`not_reached`. The lock guards the run state only and is never held while `write_gate` is
taken; the intake, every list write and the end hook run outside it."""

import logging
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from typing import Literal

from pydantic import ValidationError

from jobadvaisor.data.models import (
    MAX_UNSETTLED_REASON,
    MAX_UNSETTLED_TITLE,
    UnsettledAttempt,
    UnsettledLink,
    UnsettledLinks,
)
from jobadvaisor.data.writer import read_unsettled_links, update_unsettled_links
from jobadvaisor.intake.company_facts import HOST_SPACING_SECONDS, Throttle
from jobadvaisor.intake.duplicates import normalize_url
from jobadvaisor.intake.fetch import guarded_link, host_throttle
from jobadvaisor.intake.ladder import gone_disputed
from jobadvaisor.intake.postings import Intake, PostingNotFoundError, add_from_url

log = logging.getLogger(__name__)
Source = Literal["mailbox", "paste"]


class AlertRunBusyError(Exception):
    """Another alert run is computing; `run_id` names it."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(f"alert run {run_id} is still computing")


class RunNotRunningError(Exception):
    """The run is `done`, `failed` or `cancelled`, so it takes no cancel."""


class LinkInRunError(Exception):
    """The link is `waiting` in the list while a run computes, so it cannot be removed."""


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


def _rows(links: UnsettledLinks) -> dict[str, UnsettledLink]:
    """The rows of `links` by their link's key (`normalize_url`); of a key repeated by a hand
    edit, the first row."""
    rows: dict[str, UnsettledLink] = {}
    for row in links.links:
        rows.setdefault(normalize_url(row.url), row)
    return rows


def _taken(current: UnsettledLinks, entries: list[RunEntry], source: Source,
           now: datetime) -> UnsettledLinks:
    """`current` as a run of `entries` starts: every row still `waiting` (a run lost in a
    restart) turns `not_reached`, then each distinct link of `entries` waits, a new row with
    `tries: 0` and `added_at: now`, an existing one with the entry's title and all else kept."""
    rows = {key: row.model_copy(update={"state": "not_reached"}) if row.state == "waiting"
            else row for key, row in _rows(current).items()}
    seen = set()
    for entry in entries:
        key = normalize_url(entry.url)
        if key in seen:
            continue
        seen.add(key)
        title = entry.title[:MAX_UNSETTLED_TITLE]
        rows[key] = rows[key].model_copy(update={"state": "waiting", "title": title}) \
            if key in rows else UnsettledLink(url=entry.url, title=title, source=source,
                                              state="waiting", tries=0, added_at=now)
    return current.model_copy(update={"links": list(rows.values())})


TAILED = ("connection failed", "browser failed", "fetch failed")  # outcomes stored as prefix


def _bare(outcome: str) -> str:
    """`outcome` without the variable tail of the `TAILED` outcomes, whose text can name the
    address a step fetched (the browser's message names the redirect it navigated)."""
    return next((prefix for prefix in TAILED if outcome.startswith(prefix)), outcome)


def _settled(current: UnsettledLinks, *, entry: RunEntry, outcome: dict, source: Source,
             now: datetime) -> UnsettledLinks:
    """`current` once `entry` ended with `outcome` (`add_entry`) at `now`: `stored`,
    `duplicate` and `closed` drop the link's row; `failed` makes it `unclear` (with
    `unclear: true`) or `unread`, counts one try, and keeps the attempts as `{step, outcome}`
    (`_bare`) and the reason cut to `MAX_UNSETTLED_REASON`. A row missing for a failed link (a
    hand edit removed it) is created with `source`."""
    rows = _rows(current)
    key = normalize_url(entry.url)
    if outcome["state"] != "failed":
        rows.pop(key, None)
    else:
        row = rows.get(key) or UnsettledLink(
            url=entry.url, title=entry.title[:MAX_UNSETTLED_TITLE], source=source,
            state="waiting", tries=0, added_at=now)
        rows[key] = row.model_copy(update={
            "state": "unclear" if outcome.get("unclear") else "unread",
            "tries": row.tries + 1, "last_tried_at": now,
            "attempts": [UnsettledAttempt(step=attempt["step"], outcome=_bare(attempt["outcome"]))
                         for attempt in outcome.get("attempts", [])],
            "reason": (outcome.get("reason") or "")[:MAX_UNSETTLED_REASON] or None})
    return current.model_copy(update={"links": list(rows.values())})


def _ended(current: UnsettledLinks, *, keys: set[str],
           unwritten: dict[str, tuple[RunEntry, dict, datetime]],
           source: Source) -> UnsettledLinks:
    """`current` once a run over the links `keys` has ended: the outcomes whose own write
    failed (`unwritten`: link key → entry, outcome, end time) are applied now (`_settled`), and
    every row of `keys` still `waiting` turns `not_reached`. Rows of other links stay as they
    are."""
    for entry, outcome, at in unwritten.values():
        current = _settled(current, entry=entry, outcome=outcome, source=source, now=at)
    rows = _rows(current)
    for key in keys & rows.keys():
        if rows[key].state == "waiting":
            rows[key] = rows[key].model_copy(update={"state": "not_reached"})
    return current.model_copy(update={"links": list(rows.values())})


class AlertRuns:
    """Starts and reads alert runs into `intake`, one at a time, run state in memory only, and
    keeps the list of unsettled links of `intake.root` (`start`). Every
    request of a run's intake waits on `throttle` (default: one request per host per
    `HOST_SPACING_SECONDS`) through `fetch.host_throttle`; tests pass one on a fake clock."""

    def __init__(self, intake: Intake, throttle: Throttle | None = None):
        self._intake, self._root = intake, intake.root
        self._throttle = throttle or Throttle(HOST_SPACING_SECONDS)
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._lock = threading.Lock()
        self._state: dict[str, dict] = {}
        self._computing: str | None = None

    def start(self, entries: list[RunEntry],
              on_end: Callable[[list[dict]], None] | None = None, *, source: Source) -> str:
        """Add `entries` in the background and return the run's ID at once. Raises
        `AlertRunBusyError` while another run computes. Once the slot is claimed, and outside
        this object's lock, the list of unsettled links is written in one change (`_taken`):
        leftover `waiting` rows turn `not_reached`, and each link of `entries` waits, a new one
        listed with `source`. When that write raises (`DataRepositoryError` for an unreadable or
        invalid file), the slot is freed, nothing starts and the error propagates. The lock is
        released first because a backup can hold `write_gate` for seconds and `read` must not
        wait for it. Each fetched entry then settles or keeps its row (`_settled`; a failed
        write is logged and retried at the end), and the end of the run (after the last entry,
        a cancel or a crash, before the slot is freed) applies those retries and turns this
        run's rows still `waiting` `not_reached` (`_ended`). `on_end(entries)` gets the final
        entry states (`read`'s `entries`) on the worker thread, outside this object's lock,
        after the last entry, after a crash, after a cancel, after the end's write, and before
        the run's status leaves `running` and the slot is freed. A hook that takes a lock must
        never take one a caller of `start` holds. An exception in it is logged by its type and
        never keeps the slot."""
        run_id = uuid.uuid4().hex
        with self._lock:
            if self._computing:
                raise AlertRunBusyError(self._computing)
            self._computing = run_id
            self._state[run_id] = {
                "run_id": run_id, "status": "running", "error": None,
                "cancel_requested": False, "total": len(entries),
                "entries": [{"url": e.url, "title": e.title, "state": "waiting"} for e in entries]}
        try:
            now = datetime.now(UTC)
            update_unsettled_links(self._root,
                                   lambda current: _taken(current, entries, source, now))
            self._executor.submit(self._run, run_id, entries, on_end, source)
        except Exception:
            with self._lock:
                self._computing = None
                del self._state[run_id]
            raise
        return run_id

    def current(self) -> str | None:
        """The ID of the computing run, or `None`."""
        with self._lock:
            return self._computing

    def unsettled(self) -> dict:
        """The list of unsettled links as the API serves it: `{links, run_id}`, `run_id` the
        computing run or `None`, `links` newest activity first (`last_tried_at`, else
        `added_at`), each `{url, title, source, state, tries, added_at, last_tried_at,
        attempts, reason, in_run}`. A `waiting` row reads `in_run: true` while a run computes
        and `not_reached` while none does (a process that died mid-run). Raises
        `DataRepositoryError` for an unreadable or invalid file."""
        links = read_unsettled_links(self._root)  # first: a run ending meanwhile reads as ended
        run_id = self.current()
        rows = sorted(_rows(links).values(), key=lambda row: row.last_tried_at or row.added_at,
                      reverse=True)
        answer = []
        for row in rows:
            shown = row.model_dump(mode="json") | {"in_run": False}
            if row.state == "waiting":
                shown |= {"in_run": True} if run_id else {"state": "not_reached"}
            answer.append(shown)
        return {"links": answer, "run_id": run_id}

    def remove(self, url: str) -> None:
        """Drop the row of `url` (compared by `normalize_url`) from the list in one change.
        Raises `KeyError` without a row and `LinkInRunError` for a `waiting` row while a run
        computes, decided inside that change (under `write_gate`, before this object's lock),
        so a run starting meanwhile cannot interleave; `DataRepositoryError` for an unreadable
        or invalid file. Changes no posting and no mail mark."""
        key = normalize_url(url)

        def change(current: UnsettledLinks) -> UnsettledLinks:
            rows = _rows(current)
            if key not in rows:
                raise KeyError(url)
            if rows[key].state == "waiting" and (run_id := self.current()):
                raise LinkInRunError(f"{url} is still in alert run {run_id}")
            del rows[key]
            return current.model_copy(update={"links": list(rows.values())})
        update_unsettled_links(self._root, change)

    def cancel(self, run_id: str) -> str | None:
        """Ask the running run to stop; returns its ID at once. The worker looks for the request
        before each entry, so the entry it works on is finished, then the run ends `cancelled`
        and the entries it did not reach stay `waiting`. Answers `None` for an unknown ID and
        raises `RunNotRunningError` for a run that has ended."""
        with self._lock:
            state = self._state.get(run_id)
            if state is None:
                return None
            if state["status"] != "running":
                raise RunNotRunningError(f"alert run {run_id} is {state['status']}")
            state["cancel_requested"] = True
            return run_id

    def read(self, run_id: str) -> dict | None:
        """A copy of the run's state, or `None` for an unknown ID: `run_id`, `status`
        (`running`, `done`, `failed`, `cancelled`), `error` (the exception's type name when the
        run crashed), `cancel_requested`, `total`, `done` (entries ended, closed ones included),
        and `entries` in order, each `{url, title, state}` with `state` one of `waiting`,
        `running`, `stored`, `duplicate`, `closed`, `failed`, plus the outcome's fields
        (`add_entry`). An entry whose link (`normalize_url`) an earlier entry already put
        through intake is not fetched: it carries that entry's outcome fields and `same_as`, the
        earlier entry's index. After a cancel, the entries not reached are `waiting`."""
        with self._lock:
            state = self._state.get(run_id)
            if state is None:
                return None
            entries = [dict(entry) for entry in state["entries"]]
            done = sum(entry["state"] in ("stored", "duplicate", "closed", "failed")
                       for entry in entries)
            return state | {"entries": entries, "done": done}

    def _run(self, run_id: str, entries: list[RunEntry],
             on_end: Callable[[list[dict]], None] | None, source: Source) -> None:
        status, error = "done", None
        seen: dict[str, int] = {}  # link key → index of the entry that was fetched for it
        # link key → (entry, outcome, end time) of an entry whose row could not be written
        unwritten: dict[str, tuple[RunEntry, dict, datetime]] = {}
        try:
            for index, entry in enumerate(entries):
                with self._lock:
                    if self._state[run_id]["cancel_requested"]:
                        status = "cancelled"
                        break
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
                now = datetime.now(UTC)
                try:  # before the entry shows as ended, so a reader of `done` sees its row
                    update_unsettled_links(self._root, partial(
                        _settled, entry=entry, outcome=outcome, source=source, now=now))
                except Exception as failure:  # the run goes on; the end retries the write
                    log.warning("alert run %s: an ended entry was not written to the list of "
                                "unsettled links (%s)", run_id, type(failure).__name__)
                    unwritten[key] = (entry, outcome, now)
                with self._lock:
                    self._state[run_id]["entries"][index] |= outcome
        except Exception as crash:  # the thread must not die silently
            status, error = "failed", type(crash).__name__
        finally:
            # Before the slot is freed, so no later run's rows are waiting yet.
            try:
                update_unsettled_links(self._root, partial(
                    _ended, keys={normalize_url(entry.url) for entry in entries},
                    unwritten=unwritten, source=source))
            except Exception as failure:  # the slot must be freed whatever the write did
                log.warning("alert run %s: the end of the run was not written to the list of "
                            "unsettled links (%s)", run_id, type(failure).__name__)
            if on_end is not None:
                try:
                    on_end(self.read(run_id)["entries"])
                except Exception as hook:  # the slot must be freed whatever the hook did
                    log.warning("alert run %s: the end hook failed (%s)", run_id,
                                type(hook).__name__)
            with self._lock:
                self._state[run_id] |= {"status": status, "error": error}
                self._computing = None
