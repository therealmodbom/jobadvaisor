"""The availability check (`design.md` → D5): the user starts it, it fetches each covered
posting's links once with plain HTTP (no model call), decides closed, available or unknown, and
stores the result as the posting's `availability`. One check at a time, state in memory only (a
restart forgets it), like the alert-mail runs."""

import threading
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx

from jobadvaisor.data.loader import DataRepository, load
from jobadvaisor.data.models import Availability, PolicyPack, Posting
from jobadvaisor.data.writer import write_availability
from jobadvaisor.intake.company_facts import Throttle
from jobadvaisor.intake.fetch import (
    TIMEOUT_SECONDS,
    USER_AGENT,
    FetchError,
    closed_by_text,
    download_plain,
    guarded_link,
    url_host,
)
from jobadvaisor.intake.ladder import (
    GONE_OUTCOMES,
    closed_rules_of,
    is_login_walled,
    login_wall_hosts,
)
from jobadvaisor.intake.links import public_link

HOST_SPACING_SECONDS = 3  # between two requests to one host; the spike still met 429s at 3 s


class CheckBusyError(Exception):
    """Another availability check is computing; `check_id` names it."""

    def __init__(self, check_id: str):
        self.check_id = check_id
        super().__init__(f"availability check {check_id} is still computing")


class CheckStateError(Exception):
    """The check is not running, so it takes no cancel; the message says why."""


def _links(posting: Posting, walled: list[str]) -> list[str]:
    """The posting's stored links that are not on a login-walled host: the ones a check fetches."""
    return [url for url in posting.urls if not is_login_walled(url, walled)]


def check_batch(repository: DataRepository) -> list[str]:
    """The IDs, in ID order, of the postings a check covers: application status open,
    availability neither closed nor set by the user, and at least one stored link on a host that
    is not login-walled (so a pasted or uploaded posting, with no link, is never covered). The
    API announces this count and a check starts with exactly this batch."""
    walled = login_wall_hosts(repository.policy_pack)
    return sorted(
        posting_id for posting_id, posting in repository.postings.items()
        if posting.status == "open" and _links(posting, walled)
        and not (posting.availability
                 and (posting.availability.state == "closed"
                      or posting.availability.set_by == "user")))


def check_posting(posting: Posting, walled: list[str], *, http: httpx.Client | None = None,
                  throttle: Throttle | None = None) -> str:
    """What the links of `posting` say: `"available"`, `"closed"` or `"unknown"`.

    Each link not on a `walled` host is fetched in order, once (`download_plain` without
    retry), with `guarded_link` set to it, after `throttle` allowed a request to its host. The
    first link that answers 200 with no closed rule's text marker on its final page makes the
    posting available, whatever the page holds. It is closed when every fetched link answered
    404 or 410, redirected to a closed rule's redirect marker or showed a text marker. Anything
    else, a 429, another HTTP error, a timeout, a failed connection or a refused redirect,
    leaves it unknown, and so does a posting with no link to fetch. A link that is not on a
    public host (`public_link`: localhost, a private or loopback address, a non-http scheme)
    is never requested and counts like an unreachable one. Never raises. The caller
    sets the closed rules (`closed_rules_of`); `http` replaces the client in tests."""
    links, gone = _links(posting, walled), 0
    for url in links:
        if not public_link(url):  # stored links are not validated: never reach a local service
            continue
        if throttle:
            throttle.wait(url_host(url))
        token = guarded_link.set(url)
        try:
            final_url, html = download_plain(url, http, retry=False)
            if not closed_by_text(final_url, html):
                return "available"
            gone += 1
        except FetchError as error:
            gone += str(error) in GONE_OUTCOMES
        except Exception:  # a malformed link leaves the posting unknown, never ends the check
            pass
        finally:
            guarded_link.reset(token)
    return "closed" if links and gone == len(links) else "unknown"


def _round_robin(postings: list[tuple[str, Posting]], walled: list[str]
                 ) -> list[tuple[str, Posting]]:
    """`postings` interleaved by the host of their first link, hosts in order of first
    appearance, so other hosts go on while one host's spacing runs."""
    queues: dict[str, deque] = {}
    for item in postings:
        host = url_host(_links(item[1], walled)[0])
        queues.setdefault(host, deque()).append(item)
    order = []
    while queues:
        for host in list(queues):
            order.append(queues[host].popleft())
            if not queues[host]:
                del queues[host]
    return order


class AvailabilityChecks:
    """Starts and reads availability checks over the data repository at `root`, one at a time,
    state in memory only. `http` and `throttle` replace the HTTP client and the per-host
    spacing (`HOST_SPACING_SECONDS`) in tests."""

    def __init__(self, root: Path, *, http: httpx.Client | None = None,
                 throttle: Throttle | None = None):
        self._root, self._http = root, http
        self._throttle = throttle or Throttle(HOST_SPACING_SECONDS)
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._lock = threading.Lock()
        self._state: dict[str, dict] = {}
        self._computing: str | None = None

    def start(self) -> str:
        """Check the postings `check_batch` names in the background and return the check's ID at
        once; `read` reports its `total`. Raises `CheckBusyError` while another check computes,
        `DataRepositoryError` when the data repository does not load."""
        repository = load(self._root)
        walled = login_wall_hosts(repository.policy_pack)
        batch = _round_robin([(i, repository.postings[i]) for i in check_batch(repository)],
                             walled)
        check_id = uuid.uuid4().hex
        with self._lock:
            if self._computing:
                raise CheckBusyError(self._computing)
            self._computing = check_id
            self._state[check_id] = {
                "check_id": check_id, "status": "running", "error": None, "total": len(batch),
                "done": 0, "cancel_requested": False,
                "counts": {"available": 0, "closed": 0, "unknown": 0}, "closed": []}
        try:
            self._executor.submit(self._run, check_id, batch, repository.policy_pack)
        except Exception:
            with self._lock:
                self._computing = None
                del self._state[check_id]
            raise
        return check_id

    def cancel(self, check_id: str) -> None:
        """Ask the running check to stop; returns at once. The worker reads the request before
        each posting, so the posting it works on is finished and stored, then the check ends
        `cancelled` with the counts so far. A cancel arriving after the last posting is read
        ends a `done` check. Raises `KeyError` for an unknown ID and `CheckStateError` for a
        check that has ended."""
        with self._lock:
            state = self._state[check_id]
            if state["status"] != "running":
                raise CheckStateError(f"check {check_id} is {state['status']}, not running")
            state["cancel_requested"] = True

    def read(self, check_id: str) -> dict | None:
        """A copy of the check's state, or `None` for an unknown ID: `check_id`, `status`
        (`running`, `done`, `cancelled`, `failed`), `error` (the exception's type name when the
        check crashed), `total`, `done` (postings checked), `cancel_requested` (true once a
        cancel arrived, while the check runs on to the end of its posting), `counts`
        (`available`, `closed`, `unknown`) and `closed`, the postings found closed as
        `{posting_id, title, company}`. A posting whose availability the user set meanwhile
        counts as done and in no count."""
        with self._lock:
            state = self._state.get(check_id)
            if state is None:
                return None
            return state | {"counts": dict(state["counts"]),
                            "closed": [dict(entry) for entry in state["closed"]]}

    def _run(self, check_id: str, batch: list[tuple[str, Posting]], policy_pack: PolicyPack
             ) -> None:
        status, error = "done", None
        http = self._http or httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True,
                                          headers={"User-Agent": USER_AGENT})
        try:
            walled = login_wall_hosts(policy_pack)
            with closed_rules_of(policy_pack):  # set here: a context variable stays in its thread
                for posting_id, posting in batch:
                    with self._lock:
                        if self._state[check_id]["cancel_requested"]:
                            status = "cancelled"
                            break
                    found = check_posting(posting, walled, http=http, throttle=self._throttle)
                    stored = write_availability(self._root, posting_id, Availability(
                        state=found, set_at=datetime.now(UTC), set_by="check"))
                    with self._lock:
                        state = self._state[check_id]
                        state["done"] += 1
                        if stored:  # False: the user set it meanwhile, or deleted the posting
                            state["counts"][found] += 1
                            if found == "closed":
                                state["closed"].append({"posting_id": posting_id,
                                                        "title": posting.title,
                                                        "company": posting.company})
        except Exception as crash:  # the thread must not die silently
            status, error = "failed", type(crash).__name__
        finally:
            if self._http is None:
                http.close()
            with self._lock:
                self._state[check_id] |= {"status": status, "error": error}
                self._computing = None
