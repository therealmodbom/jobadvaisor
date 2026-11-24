"""The localhost API (`design.md` → API and frontend). Serve it with
`uvicorn --factory jobadvaisor.api.app:create_app`. Every error answers `{error, detail}`."""

import re
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path
from typing import Annotated, Literal, Self

from fastapi import FastAPI, File, Form, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    StringConstraints,
    ValidationError,
    model_validator,
)
from starlette.exceptions import HTTPException

from jobadvaisor import mailbox_secret
from jobadvaisor.agent import AgentContext, Reply, answer
from jobadvaisor.availability import (
    AvailabilityChecks,
    CheckBusyError,
    CheckStateError,
    check_batch,
    checkable,
)
from jobadvaisor.data.backup import (
    Backup,
    BackupRefused,
    BackupRunning,
    BackupUnavailable,
)
from jobadvaisor.data.loader import DataRepository, DataRepositoryError, load, write_gate
from jobadvaisor.data.models import (
    HOST_PATTERN,
    Folders,
    ImportMapping,
    Label,
    Pool,
    PoolSettings,
    Posting,
    Score,
)
from jobadvaisor.data.writer import (
    delete_posting,
    read_mailbox,
    read_pool,
    read_posting,
    read_scores,
    update_mailbox_account,
    update_pool_settings,
    write_label,
    write_login_wall_hosts,
)
from jobadvaisor.index import LabelIndex, PostingIndex, state_path
from jobadvaisor.intake import alert_mail, mailbox_checks
from jobadvaisor.intake.alert_runs import AlertRunBusyError, AlertRuns, RunEntry
from jobadvaisor.intake.entries import parse_entries, preview, tables_left_out
from jobadvaisor.intake.imports import ImportBusyError, Imports
from jobadvaisor.intake.ladder import login_wall_hosts
from jobadvaisor.intake.mailbox import MailboxError
from jobadvaisor.intake.mailbox import connect as connect_to_mailbox
from jobadvaisor.intake.postings import (
    Intake,
    NoPostingTextError,
    NotFlaggedError,
    PostingNotFoundError,
    Submission,
    add_from_url,
    add_submission,
    amend_posting,
    pdf_text,
    read_policy_pack,
)
from jobadvaisor.llm import chat_model, embeddings
from jobadvaisor.pool import counter, next_pass, rank, resolve_verdict
from jobadvaisor.settings import REPOSITORY_ROOT, Settings
from jobadvaisor.tools.guard import content_guard
from jobadvaisor.triage.graph import (
    ScoreRefused,
    ScoringFailed,
    TriageContext,
    build_graph,
    checkpoint_path,
    checkpointer,
)
from jobadvaisor.triage.runs import RunBusyError, Runs, RunStateError

HTTP_URL = re.compile(r"https?://[^\s/]+\S*")
NOT_FOUND_DETAIL = "no attempt yielded the posting; paste its text or upload a PDF instead"


class BatchBody(BaseModel):
    """`POST /postings/batch` body: `{"urls": [...]}`, at least one string."""

    model_config = ConfigDict(extra="forbid")

    urls: list[StrictStr] = Field(min_length=1)


class AlertMailBody(BaseModel):
    """`POST /alert-mails/preview` body: the pasted mail's `html` part (null when the clipboard
    had none) and its plain `text`; not both empty."""

    model_config = ConfigDict(extra="forbid")

    html: StrictStr | None = Field(None, max_length=alert_mail.MAX_MAIL)
    text: StrictStr = Field("", max_length=alert_mail.MAX_MAIL)

    @model_validator(mode="after")
    def not_empty(self) -> Self:
        """Reject a paste that holds nothing."""
        if not (self.html or "").strip() and not self.text.strip():
            raise ValueError("paste a mail")
        return self


class AlertRunEntryBody(BaseModel):
    """One chosen entry: an http(s) `url`, its `title`, and `force` to store a text duplicate
    anyway (default false)."""

    model_config = ConfigDict(extra="forbid")

    url: StrictStr
    title: StrictStr = ""
    force: StrictBool = False

    @model_validator(mode="after")
    def http_url(self) -> Self:
        """Reject a link that is no http(s) address on a public host."""
        if not HTTP_URL.fullmatch(self.url.strip()) or not alert_mail.public_link(self.url.strip()):
            raise ValueError("url must be an http or https address on a public host")
        return self


class AlertRunBody(BaseModel):
    """`POST /alert-mails/runs` body: 1 to 100 entries."""

    model_config = ConfigDict(extra="forbid")

    entries: list[AlertRunEntryBody] = Field(min_length=1, max_length=alert_mail.MAX_ENTRIES)


class MailboxBody(BaseModel):
    """`PUT /mailbox` body: `host` and `user` (trimmed, not empty), `port` (default 993), an
    optional `password` (empty or absent keeps the stored one), an optional `folders` choice
    (`{"all": true}` or `{"names": [...]}`) and an optional `max_mails` (1 to 1000); an absent
    `folders` or `max_mails` keeps the stored value."""

    model_config = ConfigDict(extra="forbid")

    host: Annotated[StrictStr, StringConstraints(strip_whitespace=True, min_length=1)]
    port: int = Field(993, ge=1, le=65535)
    user: Annotated[StrictStr, StringConstraints(strip_whitespace=True, min_length=1)]
    password: StrictStr | None = None
    folders: Folders | None = None
    max_mails: int | None = Field(None, ge=1, le=1000)


class MailboxCheckBody(BaseModel):
    """`POST /mailbox/checks` body (optional): `{"since": "YYYY-MM-DD"}`, the start date of the
    first check."""

    model_config = ConfigDict(extra="forbid")

    since: date | None = None


class MailboxFinishBody(BaseModel):
    """`POST /mailbox/checks/{id}/finish` body: the chosen entries, none up to all the check
    offered (there is no upper limit of 100 as for a pasted mail)."""

    model_config = ConfigDict(extra="forbid")

    entries: list[AlertRunEntryBody]


class UnscreenedAnswer(BaseModel):
    """`POST /pool/passes/{id}/unscreened` body: `{"continue": true}` continues with the
    unscreened postings, `{"continue": false}` aborts the pass."""

    model_config = ConfigDict(extra="forbid")

    proceed: bool = Field(alias="continue")


class PassBody(BaseModel):
    """`POST /pool/passes` body: `{"variant": "unscored" | "all"}`, required."""

    model_config = ConfigDict(extra="forbid")

    variant: Literal["unscored", "all"]


class PoolSettingsBody(BaseModel):
    """`PUT /pool/settings` body: both fields required."""

    model_config = ConfigDict(extra="forbid")

    correction_threshold: int = Field(ge=1)
    correction_rate: float = Field(ge=0, le=1)


class PostingPatch(BaseModel):
    """`PATCH /postings/{id}` body: corrected fields, the application `status`, the hand setting
    `availability` (`"available"` or `"closed"`; any other value, `"unknown"` and `"check"`
    included, is a 422) and/or `"release": true` for a posting the content guard flagged. At
    least one is required."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(None, min_length=1)
    company: str | None = Field(None, min_length=1)
    location_raw: str | None = Field(None, min_length=1)
    status: Literal["open", "applied", "done"] | None = None
    availability: Literal["available", "closed"] | None = None
    release: Literal[True] | None = None

    @model_validator(mode="after")
    def not_empty(self) -> Self:
        """Reject a body that changes nothing and an explicit null for a corrected field."""
        if not self.model_fields_set:
            raise ValueError("name a field to correct or release the posting")
        nulled = [name for name in self.model_fields_set - {"release"}
                  if getattr(self, name) is None]
        if nulled:
            raise ValueError("cannot set to null: " + ", ".join(sorted(nulled)))
        return self


class RatingBody(BaseModel):
    """`PUT /postings/{id}/rating` body: optional `verdict` ("positive" or "negative"), optional
    `strength` ("weak" or "strong", only with a verdict; absent is a plain yes or no), reason
    `chips` (IDs from the policy pack, default none) and optional `note`. Without a verdict the
    first chip with a polarity decides it."""

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["positive", "negative"] | None = None
    strength: Literal["weak", "strong"] | None = None
    chips: list[str] = []
    note: str | None = None


class LoginWallHosts(BaseModel):
    """`PUT /policy-pack/login-wall-hosts` body: the full list, replacing the stored one (an
    empty list walls off no host). Hosts are trimmed, lower-cased and de-duplicated."""

    model_config = ConfigDict(extra="forbid")

    hosts: list[str]


class Message(BaseModel):
    """One turn of a conversation with the agent."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class AgentMessages(BaseModel):
    """`POST /agent/messages` body: the whole conversation so far, ending with the user's
    message (the server keeps no history)."""

    model_config = ConfigDict(extra="forbid")

    messages: list[Message] = Field(min_length=1)

    @model_validator(mode="after")
    def ends_with_user(self) -> Self:
        """Reject a conversation that does not end with the user's message."""
        if self.messages[-1].role != "user":
            raise ValueError("the last message must be the user's")
        return self


Agent = Callable[[list[dict]], Reply]
ALL_STATUSES = ("open", "applied", "done")
MAILBOX_SETUP_REASONS = {
    "no key": "no mailbox key is configured (MAILBOX_KEY)",
    "no password": "no password is stored for the mailbox",
    "password unreadable": "the stored password cannot be decrypted; enter it again"}
FRONTEND_BUILD = REPOSITORY_ROOT / "frontend" / "dist"
# Written into the image at build time (Dockerfile); a file, not an environment variable, so the
# deployment's settings cannot make the backend disagree with the frontend it serves.
VERSION_FILE = REPOSITORY_ROOT / "VERSION"


def create_app(runs: Runs | None = None, intake: Intake | None = None,
               agent: Agent | None = None, frontend: Path = FRONTEND_BUILD,
               imports: Imports | None = None, backup: Backup | None = None,
               alert_runs: AlertRuns | None = None,
               checks: AvailabilityChecks | None = None,
               connect: mailbox_checks.Connect | None = None) -> FastAPI:
    """The app over `runs`, `intake`, `agent` (conversation → reply), `imports`, `backup`,
    `alert_runs` and `checks`, by default those of the configured data repository (imports and
    alert runs over `intake`, the backup of `intake.root` with that repository's state directory,
    the availability checks of `intake.root`); the default
    agent is built on its first message. `connect` opens the IMAP connection of the mailbox
    (`intake.mailbox.connect` by default; tests pass a fake). The built frontend in `frontend`
    is served at `/` after the API routes, so they take precedence; without a build (no
    `index.html`) the API runs alone."""
    settings = Settings()
    if runs is None or intake is None:
        runs, intake = runs or configured_runs(settings), intake or configured_intake(settings)
    imports = imports or Imports(intake)
    alert_runs = alert_runs or AlertRuns(intake)
    checks = checks or AvailabilityChecks(intake.root)
    mail_record = state_path(settings, intake.root) / "alert-mails.jsonl"
    password_file = state_path(settings, intake.root) / "mailbox-password"
    mailbox = mailbox_checks.MailboxChecks(
        intake, alert_runs, record=mail_record, password_file=password_file,
        key=settings.mailbox_key, connect=connect or connect_to_mailbox)
    backup = backup or Backup(intake.root, state_path(settings, intake.root))
    if agent is None:
        configured = cache(lambda: configured_agent(Settings()))
        agent = lambda messages: configured()(messages)  # noqa: E731
    app = FastAPI(title="JobAdvAIsor")

    @app.exception_handler(HTTPException)
    def http_error(request: Request, error: HTTPException) -> JSONResponse:
        return problem(error.status_code, "not found" if error.status_code == 404
                       else "request failed", str(error.detail))

    @app.exception_handler(Exception)
    def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        return problem(500, "internal error", f"{type(error).__name__}: {error}")

    @app.exception_handler(mailbox_checks.CheckBusyError)
    def mailbox_check_busy(request: Request, error: mailbox_checks.CheckBusyError
                           ) -> JSONResponse:
        return JSONResponse({"error": "check in progress", "detail": str(error),
                             "check_id": error.check_id}, status_code=409)

    @app.exception_handler(mailbox_checks.ReadInProgressError)
    def mailbox_read_in_progress(request: Request, error: mailbox_checks.ReadInProgressError
                                 ) -> JSONResponse:
        return problem(409, "read in progress", str(error))

    @app.exception_handler(mailbox_checks.NotConfiguredError)
    def mailbox_not_configured(request: Request, error: mailbox_checks.NotConfiguredError
                               ) -> JSONResponse:
        return problem(409, "not configured", str(error))

    @app.exception_handler(mailbox_checks.CheckNotDoneError)
    def mailbox_check_not_done(request: Request, error: mailbox_checks.CheckNotDoneError
                               ) -> JSONResponse:
        return problem(409, "check not done", str(error))

    @app.exception_handler(MailboxError)
    def mailbox_unreachable(request: Request, error: MailboxError) -> JSONResponse:
        """A mailbox reason as its answer: 409 for a missing key or password (the user must
        act in the settings), else 502. Never text from the server."""
        if error.reason in MAILBOX_SETUP_REASONS:
            return problem(409, error.reason, MAILBOX_SETUP_REASONS[error.reason])
        return problem(502, error.reason, "the mailbox could not be reached")

    @app.exception_handler(RequestValidationError)
    def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        detail = "; ".join(f"{'.'.join(map(str, item['loc']))}: {item['msg']}"
                           for item in error.errors())
        return problem(422, "invalid request", detail)

    @app.get("/health")
    def read_health() -> JSONResponse:
        """`{"status", "checks": {"data_repo"}, "version"}`: `status` is `ok` (200) or `fail` (503,
        same body); `data_repo` is `ok` or the error of loading the data repository and
        `pool.json`; `version` is the release tag written to the `VERSION` file at image
        build, or `dev` when the file does not exist (a checkout). The version is in both."""
        try:
            load(intake.root)
            read_pool(intake.root)
            data_repo = "ok"
        except DataRepositoryError as error:
            data_repo = str(error)
        version = VERSION_FILE.read_text().strip() if VERSION_FILE.is_file() else "dev"
        ok = data_repo == "ok"
        return JSONResponse({"status": "ok" if ok else "fail", "checks": {"data_repo": data_repo},
                             "version": version}, status_code=200 if ok else 503)

    def backup_state() -> dict:
        """The body of `GET /backup`. Raises `BackupUnavailable`."""
        status, history = backup.status(), backup.history()
        return {"pending": status.uncommitted > 0 or status.unpushed > 0,
                "uncommitted": status.uncommitted, "unpushed": status.unpushed,
                "branch": status.branch, "remote": status.remote, "operation": status.operation,
                "running": backup.running, "progress": backup.progress,
                "last_result": asdict(backup.last_result) if backup.last_result else None,
                "last_success": history.last_success, "last_failure": history.last_failure}

    @app.get("/backup")
    def read_backup() -> dict:
        """What a backup would do and how the last one went: `pending` (`uncommitted` changed
        files, also those made outside the app, or `unpushed` commits), `branch` (null on a
        detached HEAD), `remote` (the upstream, null without one), `operation` (a merge or
        rebase stopped on a conflict), `running` with its `progress` `{step, files, percent}`,
        `last_result` `{at, result, commit}` of the last finished backup (`pushed`, `committed`
        or `up_to_date`), `last_success` (time) and `last_failure` `{at, step, reason}` (step
        `commit` or `push`, reason git's message) since then. 409 `backup unavailable` when the
        data directory is no git repository of its own."""
        try:
            return backup_state()
        except BackupUnavailable as error:
            return problem(409, "backup unavailable", str(error))

    @app.post("/backup", status_code=202)
    def start_backup() -> dict:
        """Start a backup in the background (commit what is pending, then push when there is an
        upstream); takes no body and answers at once `{"status"}`, the `GET /backup` body with
        `running` true. A commit or push failure shows later in `last_failure` of `GET /backup`.
        409 `backup running` (a second press is not queued), `backup refused` (detail: the
        branch other than `main` or the operation in progress) or `backup unavailable`."""
        try:
            before = backup_state()  # taken first: a status read after the start could fail on a
            backup.start()           # backup that is already running, or race a fast one
            return {"status": before | {"running": True, "progress": backup.progress}}
        except BackupRunning as error:
            return problem(409, "backup running", str(error))
        except BackupRefused as error:
            return problem(409, "backup refused", str(error))
        except BackupUnavailable as error:
            return problem(409, "backup unavailable", str(error))

    @app.get("/pool")
    def read_pool_view() -> dict:
        """The posting pool: `rows` of every status in rank order, the correction `counter`,
        `settings`, `next_pass`, `next_check` (`{total}`: the postings a check would cover), the
        policy pack's `reason_chips` and `screening` (a content-guard
        classifier is configured). A corrupt score file shows
        as `score_problem` on its row; a data repository that does not load answers 500."""
        repository, scores, problems, pool = pool_state(intake.root)
        return {"rows": rank(repository, scores, problems, ALL_STATUSES),
                "counter": counter(repository, scores, pool),
                "settings": pool.settings.model_dump(),
                "next_pass": next_pass(repository, scores, pool),
                "next_check": {"total": len(check_batch(repository))},
                "reason_chips": reason_chips(repository),
                "screening": intake.guard.classifier is not None}

    @app.put("/pool/settings")
    def save_pool_settings(body: PoolSettingsBody) -> dict:
        """Store the correction threshold and rate in `pool.json` (passes are kept); answers
        `{"settings"}` as stored. 422 for a threshold below 1, a rate outside 0..1, a missing
        or an unknown field."""
        pool = update_pool_settings(intake.root, PoolSettings(**body.model_dump()))
        return {"settings": pool.settings.model_dump()}

    def delete_blocked() -> Literal["scoring", "check"] | None:
        """What would refuse a delete now, in the order `DELETE` refuses: `"check"` while an
        availability check runs, `"scoring"` while a pass, a single score or another
        request's delete holds the slot, else `None`. A snapshot: read before a handler takes
        `write_gate`, since `DELETE` holds the checks' lock while it waits for the gate."""
        if checks.running():
            return "check"
        return "scoring" if runs.running() else None

    @app.get("/postings/{posting_id}")
    def read_posting_page(posting_id: str) -> dict:
        """Everything the posting page shows: its pool `row` (exploration off), the `posting`,
        its stored `score` (null without one), the `examples` the judge compared it with that
        still exist, `checkable` (a check can read one of its links: not pasted text or a PDF,
        not only login-walled or non-public links), `screening` (a content-guard classifier
        is configured) and `delete_blocked` (`"scoring"` while a pass or a single score
        computes, `"check"` while an availability check runs, else null: what a delete would
        be refused for). The whole read runs under `write_gate`, so a delete falls before or
        after it. 404 for an unknown or unsafe ID."""
        blocked = delete_blocked()
        with write_gate:
            repository, scores, problems, _ = pool_state(intake.root)
            if posting_id not in repository.postings:
                return problem(404, "not found", f"no posting {posting_id}")
            return posting_page(repository, scores, problems, posting_id) | {
                "delete_blocked": blocked}

    @app.delete("/postings/{posting_id}", status_code=204)
    def remove_posting(posting_id: str) -> Response:
        """Delete a posting with its rating, score and hand-settled values for good
        (`delete_posting`); answers 204 with no body. The delete takes the checks' lock, then
        the run slot, then `write_gate`, and holds them until the delete has run, which may wait
        for a backup's `git commit` to release `write_gate`. `{error, detail}`
        errors: 404 for an unknown or unsafe ID (also a second delete); 409 `scoring in
        progress` (detail: the pass, or `score:<posting ID>`, that computes) or `check in
        progress` (detail: the check's ID) with nothing changed."""
        try:
            with checks.exclusive(), runs.exclusive(f"delete:{posting_id}"):
                delete_posting(intake.root, posting_id)
        except (KeyError, ValueError):
            return problem(404, "not found", f"no posting {posting_id}")
        except RunBusyError as error:
            return problem(409, "scoring in progress", error.run_id)
        except CheckBusyError as error:
            return problem(409, "check in progress", error.check_id)
        return Response(status_code=204)

    @app.post("/postings/{posting_id}/score")
    def score_posting_now(posting_id: str) -> dict:
        """Score one posting now, rated or not, replacing an earlier score; takes no body and
        answers once the judge has (synchronous). 200 is the `GET /postings/{id}` body plus
        the `counter` and `next_pass` as `GET /pool` has them. The `{error, detail}` errors:
        404 unknown posting; 409 `scoring in progress` (a pass or another score computes),
        `excluded` (detail: the rule IDs), `held` (the guard categories) or `unscreened` (no
        guard result and screening off) for a posting no pass would score; 502 `scoring
        failed` when the judge, the label index or the classifier fails (trying again may help);
        a failure to store the guard result or the score is a 500. The judge runs outside
        `write_gate`, which only the answer takes; a posting deleted by then is a 404 too."""
        repository, *_ = pool_state(intake.root)
        if posting_id not in repository.postings:
            return problem(404, "not found", f"no posting {posting_id}")
        try:
            runs.score(posting_id)
        except KeyError:  # deleted since the check above
            return problem(404, "not found", f"no posting {posting_id}")
        except RunBusyError as error:
            return problem(409, "scoring in progress", str(error))
        except ScoreRefused as error:
            return problem(409, error.reason, refusal_detail(error))
        except ScoringFailed as error:
            return problem(502, "scoring failed", str(error))
        blocked = delete_blocked()
        with write_gate:
            repository, scores, problems, pool = pool_state(intake.root)
            if posting_id not in repository.postings:  # deleted after the judge
                return problem(404, "not found", f"no posting {posting_id}")
            return posting_page(repository, scores, problems, posting_id) | {
                "delete_blocked": blocked, "counter": counter(repository, scores, pool),
                "next_pass": next_pass(repository, scores, pool)}

    def posting_page(repository: DataRepository, scores: dict[str, Score],
                     problems: dict[str, str], posting_id: str) -> dict:
        """The posting page body of `GET /postings/{id}` for a posting that exists."""
        row = next(row for row in rank(repository, scores, problems, ALL_STATUSES)
                   if row["posting_id"] == posting_id) | {"exploration": False}
        score = scores.get(posting_id)
        examples = [{"posting_id": example, "title": found.title, "company": found.company}
                    for example in (score.example_ids if score else [])
                    if (found := repository.postings.get(example))]
        posting = repository.postings[posting_id]
        return {"row": row, "posting": posting.model_dump(mode="json"),
                "score": score.model_dump(mode="json", exclude={"schema_version"})
                if score else None, "examples": examples,
                "checkable": checkable(posting, login_wall_hosts(repository.policy_pack)),
                "reason_chips": reason_chips(repository),
                "screening": intake.guard.classifier is not None}

    @app.put("/postings/{posting_id}/rating")
    def rate_posting(posting_id: str, body: RatingBody) -> dict:
        """Store the user's rating of a posting at once, replacing an earlier one; answers its
        pool `row` (with the stored `label`), the `counter` and `next_pass` as `GET /pool` has
        them. A given verdict is kept; without one it is the polarity of the first chip that
        has one. The label replaces the earlier one whole, so an omitted `strength` clears it.
        404 for an unknown posting, 422 for an unknown chip (named), no verdict, or a
        `strength` without a given verdict (a chip-derived verdict has none). The check, the
        write and the answer run under `write_gate`, so a delete falls before or after them."""
        with write_gate:
            repository, *_ = pool_state(intake.root)
            if posting_id not in repository.postings:
                return problem(404, "not found", f"no posting {posting_id}")
            if body.strength and not body.verdict:
                return problem(422, "invalid rating", "strength needs a verdict")
            try:
                verdict = resolve_verdict(body.verdict, body.chips,
                                          repository.policy_pack.reason_chips)
            except ValueError as error:
                return problem(422, "invalid rating", str(error))
            write_label(intake.root, posting_id, Label(
                schema_version="1", kind="rating", verdict=verdict, strength=body.strength,
                chips=body.chips, note=body.note, rated_at=datetime.now(UTC)))
            repository, scores, problems, pool = pool_state(intake.root)
            row = next(row for row in rank(repository, scores, problems, ALL_STATUSES)
                       if row["posting_id"] == posting_id)
            return {"row": row, "counter": counter(repository, scores, pool),
                    "next_pass": next_pass(repository, scores, pool)}

    @app.post("/pool/passes", status_code=202)
    def start_pass(body: PassBody) -> dict:
        """Start a scoring pass in the background; answers its `pass_id` at once, or 409
        naming the pass (or `score:<posting ID>`, a single score) that is still computing.
        Body `{"variant"}`, required: `"unscored"` scores every posting without a score, rated
        or not; `"all"` rescores every posting. A missing or unknown variant is a 422. A
        repository that does not load still starts the pass, which then reports `failed`
        with the reason."""
        try:
            return {"pass_id": runs.start(body.variant == "all")}
        except RunBusyError as error:
            return problem(409, "pass in progress", str(error))

    @app.get("/pool/passes/{pass_id}")
    def read_pass(pass_id: str) -> dict:
        """A pass's `{pass_id, status, started_at, error, progress, cancel_requested, scored,
        unscreened}`. `status` is running, awaiting_answer, done, aborted, cancelled or failed.
        `progress` is the last report `{phase, score: {done, total} | null}` (phase checking,
        scoring or storing; `score` is `null` while checking), or `null` when this
        process holds none (before the first report, after a restart). `cancel_requested` is
        true while the pass runs on after a cancel. `scored` counts the results scored, which a
        cancelled, ended pass has stored. `unscreened` lists the postings the pass asks about,
        with title and company. 404 for an unknown pass."""
        run = runs.read(pass_id)
        if run is None:
            return unknown_pass(pass_id)
        try:
            postings = load(intake.root).postings
        except DataRepositoryError:
            postings = {}
        unscreened = [{"posting_id": i, "title": postings[i].title if i in postings else i,
                       "company": postings[i].company if i in postings else i}
                      for i in run["unscreened"]]
        return {"pass_id": pass_id, "status": run["status"], "started_at": run["started_at"],
                "error": run["error"], "progress": run["progress"],
                "cancel_requested": run["cancel_requested"],
                "scored": sum(r["status"] == "scored" for r in run["results"].values()),
                "unscreened": unscreened}

    @app.post("/pool/passes/{pass_id}/cancel", status_code=202)
    def cancel_pass(pass_id: str) -> dict:
        """Ask the running pass to stop after the posting it works on; answers `{pass_id}` at
        once and the pass reports `cancel_requested` until it has stopped. 404 `not found` for
        an unknown pass, a single score (`score:<posting ID>`) included even while it computes;
        409 `pass not running` for a known pass that waits for the unscreened answer or has
        ended, also one from before a restart."""
        try:
            runs.cancel(pass_id)
        except KeyError:
            return unknown_pass(pass_id)
        except RunStateError as error:
            return problem(409, "pass not running", str(error))
        return {"pass_id": pass_id}

    @app.post("/pool/passes/{pass_id}/unscreened", status_code=202)
    def answer_unscreened(pass_id: str, body: UnscreenedAnswer) -> dict:
        """Continue with or abort a pass paused over unscreened postings; it goes on in the
        background. 409 without that question pending or while another pass or a single score
        computes."""
        try:
            runs.answer_unscreened(pass_id, body.proceed)
        except KeyError:
            return unknown_pass(pass_id)
        except (RunStateError, RunBusyError) as error:
            return problem(409, "no answer expected", str(error))
        return {"pass_id": pass_id}

    @app.post("/postings", status_code=201)
    def add_posting(text: Annotated[str | None, Form()] = None,
                    url: Annotated[str | None, Form()] = None,
                    file: Annotated[UploadFile | None, File()] = None,
                    title: Annotated[str | None, Form()] = None,
                    company: Annotated[str | None, Form()] = None,
                    location_raw: Annotated[str | None, Form()] = None) -> dict:
        """Store a posting from pasted `text`, a `url` or an uploaded PDF `file` (form-encoded,
        exactly one), with optional fields the user supplies. Answers the ID, the stored
        posting, whether screening is on and, for a URL, the ladder's attempts. 422 when no
        posting text results; for a URL, with the attempts, so the user can paste or upload, and
        `closed` true when the link is gone (404, 410, a closed redirect or notice) and no other
        source holds the posting. A page that shows a closed notice beside its posting text is
        stored with the availability closed."""
        given = [value for value in (text and text.strip(), url and url.strip(), file) if value]
        if len(given) != 1:
            return problem(422, "invalid request", "submit exactly one of text, url or file")
        if url and not HTTP_URL.fullmatch(url.strip()):
            return problem(422, "invalid request", "url must be an http or https address")
        supplied = {name: value for name, value in
                    (("title", title), ("company", company), ("location_raw", location_raw))
                    if value and value.strip()}
        attempts = None
        try:
            if url:
                posting_id, posting, duplicate, attempts = add_from_url(
                    intake, url.strip(), supplied)
            else:
                submission = (Submission(text, "text", supplied=supplied) if file is None else
                              Submission(pdf_text(file.file.read()), "pdf", supplied=supplied))
                posting_id, posting, duplicate = add_submission(intake, submission)
        except PostingNotFoundError as error:
            return JSONResponse({
                "error": "posting not found", "detail": NOT_FOUND_DETAIL,
                "attempts": error.attempts, "closed": error.closed}, status_code=422)
        except NoPostingTextError as error:
            return problem(422, "no posting text", str(error))
        return stored_answer(posting_id, posting, duplicate, attempts)

    @app.post("/postings/batch")
    def add_postings(body: BatchBody) -> dict:
        """Store the posting behind each of several URLs, one after the other. Answers 200 with
        `results`, one per URL in order: `{"url", "outcome": "stored" | "duplicate",
        "posting_id"}` for the first two, `{"url", "outcome": "closed" | "failed", "detail",
        "attempts"?}` for the others (`closed`: the link is gone and no other source holds the
        posting), which never stop the rest. 422 for an empty list or a non-string."""
        results = []
        for url in (entry.strip() for entry in body.urls):
            try:
                if not HTTP_URL.fullmatch(url):
                    raise ValueError("url must be an http or https address")
                posting_id, _, duplicate, _ = add_from_url(intake, url)
                results.append({"url": url, "posting_id": posting_id,
                                "outcome": "stored" if duplicate is None else "duplicate"})
            except PostingNotFoundError as error:
                results.append({"url": url, "outcome": "closed" if error.closed else "failed",
                                "detail": NOT_FOUND_DETAIL, "attempts": error.attempts})
            except ValueError as error:  # includes NoPostingTextError
                results.append({"url": url, "outcome": "failed", "detail": str(error)})
        return {"results": results}

    def read_list(file: UploadFile) -> str | None:
        """The text of an uploaded list (UTF-8, a byte order mark is ignored), `None` when the
        file is not UTF-8."""
        try:
            return file.file.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            return None

    @app.post("/imports/preview")
    def preview_import(file: Annotated[UploadFile, File()]) -> dict:
        """What the mapping form shows for an uploaded list (multipart field `file`, UTF-8):
        `{"tables": [{name, columns, entries}], "values": {column: [distinct values]},
        "mapping": the stored ImportMapping or null}` — tables with a link column only, values
        of columns with at most 30 distinct values. Nothing is stored; 422 `invalid upload`
        for a file that is not UTF-8 text."""
        if (text := read_list(file)) is None:
            return problem(422, "invalid upload", "the file is not UTF-8 text")
        stored = read_policy_pack(intake.root).import_mapping
        return preview(text) | {"mapping": stored and stored.model_dump(mode="json")}

    @app.post("/imports", status_code=202)
    def start_import(file: Annotated[UploadFile, File()],
                     mapping: Annotated[str, Form()]) -> dict:
        """Import an uploaded list (multipart field `file`, UTF-8) in the background with the
        confirmed `mapping` (form field, an `ImportMapping` as JSON: `{status_column,
        assessment_column, values: {status value: open|applied|done|skip}}`); answers
        `{"import_id"}` at once. The mapping goes into the policy pack as the next preview's
        default, only once no other import computes. The upload is parsed here, so `total` is
        known to the first `GET`, and never stored. 409 while an import computes (mapping left
        as stored), 422 `invalid upload` for a file that is not UTF-8 text and 422
        `invalid mapping` for a mapping that does not validate (a list without entries is
        fine: total 0)."""
        if (text := read_list(file)) is None:
            return problem(422, "invalid upload", "the file is not UTF-8 text")
        try:
            confirmed = ImportMapping.model_validate_json(mapping, strict=True)
        except ValidationError as error:
            return problem(422, "invalid mapping", str(error))
        try:
            return {"import_id": imports.start(parse_entries(text, confirmed), confirmed,
                                               tables_left_out(text, confirmed))}
        except ImportBusyError as error:
            return problem(409, "import in progress", str(error))

    @app.get("/imports/{import_id}")
    def read_import(import_id: str) -> dict:
        """An import's `status` (running, done, failed), `error` (exception type name, else
        null), `total` entries, how many are `done` and the `counts` per outcome (imported,
        duplicate, skipped_status, skipped_gone, failed). `not_imported` lists in list order
        each entry that was skipped or failed: `{row, url|null, outcome, reason}`, `row` being
        its cells except the link joined with " · ". `conflicts`: stored postings whose status
        differs from the list's, `[{posting_id, title, company, status, list_status}]`
        (statuses open|applied|done), read live so a settled one drops out.
        `tables_left_out`: the tables with links that lack the mapping's status column and so
        were not imported, `[{name, entries}]` in file order (empty without a status column).
        404 for an unknown import (state is in memory, a restart forgets it)."""
        state = imports.read(import_id)
        return state or problem(404, "not found", f"no import {import_id}")

    @app.post("/alert-mails/preview")
    def preview_alert_mail(body: AlertMailBody) -> dict:
        """The postings a pasted alert mail lists, nothing fetched: `{entries: [{url, title,
        duplicate: {posting_id, title} | null, login_walled, ambiguous}], read_by,
        unread_hosts: [{host, links}], held, model_skipped, screening, truncated}`. 502
        `screening failed` or `finder failed` (the user can retry); 422 `invalid request` for
        an empty paste or a part over 2,000,000 characters."""
        try:
            answer = alert_mail.preview(
                intake, body.html if (body.html or "").strip() else None, body.text, mail_record)
        except alert_mail.FinderError as error:
            return problem(502, str(error), "reading the mail failed; try again")
        return answer | {"screening": intake.guard.classifier is not None}

    @app.post("/alert-mails/runs", status_code=202)
    def start_alert_run(body: AlertRunBody) -> dict:
        """Add the chosen entries in the background, each link cleaned again first; answers
        `{run_id}` at once. 409 `{error: "alert run in progress", detail, run_id}` while a run
        computes, so the client can follow it; 422 `invalid request`."""
        entries = [RunEntry(alert_mail.clean_link(entry.url.strip()), entry.title, entry.force)
                   for entry in body.entries]
        try:
            return {"run_id": alert_runs.start(entries)}
        except AlertRunBusyError as error:
            return JSONResponse({"error": "alert run in progress", "detail": str(error),
                                 "run_id": error.run_id}, status_code=409)

    @app.get("/alert-mails/runs/{run_id}")
    def read_alert_run(run_id: str) -> dict:
        """A run's state (`AlertRuns.read`): `{run_id, status, error, total, done, entries:
        [{url, title, state, posting_id?, duplicate_by?, attempts?, reason?}]}`. 404 for an
        unknown run (state is in memory, a restart forgets it)."""
        return alert_runs.read(run_id) or problem(404, "not found", f"no alert run {run_id}")

    @app.post("/availability/checks", status_code=202)
    def start_availability_check() -> dict:
        """Check the open postings' links in the background (`check_batch`); answers
        `{check_id, total}` at once. 409 `{error: "check in progress", detail, check_id}` while a
        check computes, so the client can follow it."""
        try:
            check_id = checks.start()
        except CheckBusyError as error:
            return JSONResponse({"error": "check in progress", "detail": str(error),
                                 "check_id": error.check_id}, status_code=409)
        return {"check_id": check_id, "total": checks.read(check_id)["total"]}

    @app.get("/availability/checks/{check_id}")
    def read_availability_check(check_id: str) -> dict:
        """A check's state (`AvailabilityChecks.read`): `{check_id, status, error, total, done,
        cancel_requested, counts: {available, closed, unknown}, closed: [{posting_id, title,
        company}]}`; `status` is running, done, cancelled or failed. 404 for an
        unknown check (state is in memory, a restart forgets it)."""
        return checks.read(check_id) or problem(404, "not found",
                                                f"no availability check {check_id}")

    @app.post("/availability/checks/{check_id}/cancel", status_code=202)
    def cancel_availability_check(check_id: str) -> dict:
        """Ask the running check to stop after the posting it works on; answers `{check_id}` at
        once and the check reports `cancel_requested` until it has ended `cancelled`. 404
        `not found` for an unknown check, 409 `check not running` for one that has ended."""
        try:
            checks.cancel(check_id)
        except KeyError:
            return problem(404, "not found", f"no availability check {check_id}")
        except CheckStateError as error:
            return problem(409, "check not running", str(error))
        return {"check_id": check_id}

    def password_state() -> Literal["missing", "stored", "unreadable"]:
        """Whether a mailbox password is stored and the key opens it; reads it only to try."""
        if not password_file.exists():
            return "missing"
        if not mailbox_secret.key_configured(settings.mailbox_key):
            return "unreadable"
        try:
            mailbox_secret.read(password_file, settings.mailbox_key)
        except mailbox_secret.PasswordUnreadable:
            return "unreadable"
        return "stored"

    def mailbox_settings() -> dict:
        """The body of `GET /mailbox` (and the answer of `PUT /mailbox`)."""
        stored = read_mailbox(intake.root)
        return {
            "configured": stored is not None,
            "host": stored.host if stored else "", "port": stored.port if stored else 993,
            "user": stored.user if stored else "",
            "folders": stored.folders.model_dump(exclude_none=True) if stored else {"all": True},
            "max_mails": stored.max_mails if stored else 200,
            "since": stored.since.isoformat() if stored and stored.since else None,
            "last_check_at": stored.last_check_at.isoformat()
            if stored and stored.last_check_at else None,
            "password": password_state(),
            "key_configured": mailbox_secret.key_configured(settings.mailbox_key),
            "check_id": mailbox.current()}

    @app.get("/mailbox")
    def read_mailbox_settings() -> dict:
        """The mailbox account without its password: `{configured, host, port, user, folders
        ({all: true} or {names: [...]}), max_mails, since, last_check_at, password, key_configured,
        check_id}`. `password` is `stored`, `missing` or `unreadable` (the key cannot open it, or
        there is none); `check_id` names the running mailbox check, else the one whose pick list
        is not finished, else null. Without a mailbox the values are the defaults (empty host and
        user, port 993, all folders, 200 mails)."""
        return mailbox_settings()

    @app.put("/mailbox")
    def save_mailbox_settings(body: MailboxBody) -> dict:
        """Save the account (`MailboxBody`) and answer like `GET /mailbox`. A non-empty password
        is stored encrypted; an empty or absent one keeps the stored password unless host, port
        or user changed, which removes it first (it must never reach another account, not even
        between the steps; the order is forget, account, store). A host or user
        change also clears the start date and the handled and waiting records and drops an
        unfinished pick list. 409 `no key` for a password without a usable key, 409 `check in
        progress` (with `check_id`) or `read in progress` for a host or user change while a
        check runs or a mail is read, 422 `invalid request` (`max_mails` outside 1 to 1000
        included)."""
        if body.password and not mailbox_secret.key_configured(settings.mailbox_key):
            return problem(409, "no key", MAILBOX_SETUP_REASONS["no key"])
        # Compare and save under one hold of the lock, so another save cannot land between.
        with mailbox.credentials() as moving:
            stored = read_mailbox(intake.root)
            if stored is not None and (body.host, body.user) != (stored.host, stored.user):
                moving()
            # The old password goes first, so no state pairs it with another account.
            if stored is None or (body.host, body.port, body.user) != (
                    stored.host, stored.port, stored.user):
                mailbox_secret.forget(password_file)
            update_mailbox_account(intake.root, body.host, body.port, body.user, body.folders,
                                   body.max_mails)
            if body.password:
                mailbox_secret.store(password_file, body.password, settings.mailbox_key)
        return mailbox_settings()

    @app.post("/mailbox/folders")
    def list_mailbox_folders() -> dict:
        """Log in with the stored account and list its folders: `{folders: [{name, system}]}`.
        409 `not configured`, `no key`, `no password` or `password unreadable` (nothing
        attempted); 502 with a reason (`unreachable`, `certificate`, `login`, `protocol`) as
        `error`, never text from the server."""
        return {"folders": [{"name": folder.name, "system": folder.system}
                            for folder in mailbox.folders()]}

    @app.post("/mailbox/checks", status_code=202)
    def start_mailbox_check(body: MailboxCheckBody | None = None) -> dict:
        """Check the mailbox in the background; answers `{check_id}` at once. The body `{since}`
        (a date) is required while no start date is stored and ignored after that. A check that
        fails (no key, no password, the server) still answers 202 and ends `failed` with its
        `reason`. 409 `check in progress` (with `check_id`), `read in progress` (an oversized
        mail of the pending pick list is being read) or `not configured`; 422 `invalid request`
        for a missing start date."""
        try:
            return {"check_id": mailbox.start(body.since if body else None)}
        except mailbox_checks.SinceRequiredError as error:
            return problem(422, "invalid request", f"since: {error}")

    @app.get("/mailbox/checks/{check_id}")
    def read_mailbox_check(check_id: str) -> dict:
        """A mailbox check's state (`MailboxChecks.read`): `{check_id, status ("running", "done",
        "failed" or "finished"), reason, error, interrupted, cancel_requested, cancelled, total,
        read, remaining, mails, failed, held, not_screened, missing_folders}`. A mail of `mails`
        is `{key, folder, sender, subject, date, oversized, reading, read_failed, preview}`
        with `preview` the finder's answer (`{entries, read_by, unread_hosts, held,
        model_skipped, truncated}`) or null for an unread oversized mail. Never the kept text
        of a mail. 404 for an unknown check (state is in memory, a restart forgets it)."""
        return mailbox.read(check_id) or problem(404, "not found", f"no mailbox check {check_id}")

    @app.post("/mailbox/checks/{check_id}/cancel", status_code=202)
    def cancel_mailbox_check(check_id: str) -> dict:
        """Ask the running check to stop after the mail it reads; answers `{check_id}`. The
        check reports `cancel_requested` until it ends `done` with `cancelled`. 404 for an
        unknown check, 409 `check not running` for one that has ended."""
        try:
            if mailbox.cancel(check_id) is None:
                return problem(404, "not found", f"no mailbox check {check_id}")
        except mailbox_checks.CheckNotRunningError as error:
            return problem(409, "check not running", str(error))
        return {"check_id": check_id}

    @app.post("/mailbox/checks/{check_id}/mails/{key}/read")
    def read_mailbox_mail(check_id: str, key: str) -> dict:
        """Read an oversized mail of a done check on request and answer that mail (the shape of
        an item of `mails`) with its `preview`. 404 for an unknown check or mail, 409 `check not
        done`, `not oversized` (not an unread oversized mail) or `read in progress` (this
        mail is being read), 502 `screening failed` or `finder failed` (retryable, with no
        exception text)."""
        try:
            return mailbox.read_oversized(check_id, key)
        except KeyError:
            return problem(404, "not found", f"no mail {key} in mailbox check {check_id}")
        except mailbox_checks.NotOversizedError as error:
            return problem(409, "not oversized", str(error))
        except alert_mail.FinderError as error:
            return problem(502, str(error), "reading the mail failed; try again")

    @app.post("/mailbox/checks/{check_id}/finish", status_code=202)
    def finish_mailbox_check(check_id: str, body: MailboxFinishBody) -> dict:
        """Finish a done check's pick list with `{entries: [{url, title, force?}]}` (none up to
        all offered, each link cleaned again): one alert run adds them and the check's mails
        count as handled; answers `{run_id}` (null without entries). 404 for an unknown check,
        409 `alert run in progress` (with `run_id`; nothing marked), `check not done` (also a
        second finish) or `read in progress`, 422 `entry not offered` for a link the check did
        not offer, 422 `invalid request`."""
        entries = [RunEntry(alert_mail.clean_link(entry.url.strip()), entry.title, entry.force)
                   for entry in body.entries]
        try:
            return {"run_id": mailbox.finish(check_id, entries)}
        except KeyError:
            return problem(404, "not found", f"no mailbox check {check_id}")
        except mailbox_checks.EntryNotOfferedError as error:
            return problem(422, "entry not offered", str(error))
        except AlertRunBusyError as error:
            return JSONResponse({"error": "alert run in progress", "detail": str(error),
                                 "run_id": error.run_id}, status_code=409)

    def stored_answer(posting_id: str, posting: Posting, duplicate_by: str | None,
                      attempts: list | None) -> JSONResponse:
        """201 with a new posting; 200 with the stored posting a submission duplicates, and
        `duplicate_by` naming the match ("url", "text" or "similar_text")."""
        return JSONResponse({"posting_id": posting_id, "posting": posting.model_dump(mode="json"),
                             "duplicate": duplicate_by is not None, "duplicate_by": duplicate_by,
                             "attempts": attempts,
                             "screening": intake.guard.classifier is not None},
                            status_code=201 if duplicate_by is None else 200)

    @app.patch("/postings/{posting_id}")
    def amend(posting_id: str, body: PostingPatch) -> dict:
        """Correct title, company or location, set the application `status`, set the hand
        setting `availability` and/or release a flagged posting; answers the stored posting
        (a `status` makes it schema version 2). A hand setting replaces any availability, one a
        check set included, and keeps the version; the next check replaces it in turn. 404 for
        an unknown posting, 409 for releasing one the content guard did not flag. The check and
        the write run under `write_gate`, so a delete falls before or after them."""
        with write_gate:
            try:
                read_posting(intake.root, posting_id)
            except ValueError:
                return problem(404, "not found", f"no posting {posting_id}")
            corrections = body.model_dump(exclude_unset=True,
                                          exclude={"release", "availability"})
            try:
                posting = amend_posting(intake.root, posting_id, corrections,
                                        bool(body.release), availability=body.availability)
            except NotFlaggedError as error:
                return problem(409, "not flagged", str(error))
            return {"posting_id": posting_id, "posting": posting.model_dump(mode="json")}

    @app.get("/policy-pack/login-wall-hosts")
    def read_login_wall_hosts() -> dict:
        """The hosts intake never fetches anonymously: the policy pack's list, or the app's
        defaults while it names none."""
        return {"hosts": login_wall_hosts(read_policy_pack(intake.root))}

    @app.put("/policy-pack/login-wall-hosts")
    def save_login_wall_hosts(body: LoginWallHosts) -> dict:
        """Store the login-walled hosts in the policy pack and answer them as stored; 422
        names every entry that is not a bare host name, and nothing is written then."""
        hosts = list(dict.fromkeys(host.strip().lower() for host in body.hosts if host.strip()))
        invalid = [host for host in hosts if not re.fullmatch(HOST_PATTERN, host)]
        if invalid:
            return problem(422, "invalid host", "not a host name: " + ", ".join(invalid))
        return {"hosts": write_login_wall_hosts(intake.root, hosts).login_wall_hosts}

    @app.post("/agent/messages")
    def agent_message(body: AgentMessages) -> dict:
        """The agent's reply to the conversation, with the tool calls it made."""
        reply = agent([message.model_dump() for message in body.messages])
        return {"reply": reply.text, "tool_calls": reply.tool_calls}

    if (frontend / "index.html").is_file():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


def configured_agent(settings: Settings) -> Agent:
    """The agent over `DATA_REPOSITORY` with the `agent` model; every message gets a freshly
    loaded data repository. Raises `DataRepositoryError` when `DATA_REPOSITORY` is unset."""
    root = settings.data_repository
    if root is None:
        raise DataRepositoryError(["DATA_REPOSITORY is not set"])
    model, embedder = chat_model("agent", settings), embeddings(settings)

    def reply(messages: list[dict]) -> Reply:
        directory = state_path(settings, root) / "chroma"
        context = AgentContext(load(root), content_guard(settings),
                               LabelIndex(directory, embedder, settings.embedding_model),
                               PostingIndex(directory, embedder, settings.embedding_model),
                               chat_model("extractor", settings), chat_model("judge", settings))
        return answer(messages, model, context)

    return reply


def configured_intake(settings: Settings) -> Intake:
    """Intake into `DATA_REPOSITORY` with the `intake` model and the configured content guard.
    Raises `DataRepositoryError` when it is unset."""
    if settings.data_repository is None:
        raise DataRepositoryError(["DATA_REPOSITORY is not set"])
    return Intake(settings.data_repository, chat_model("intake", settings),
                  content_guard(settings))


def configured_runs(settings: Settings) -> Runs:
    """Runs over `DATA_REPOSITORY`, checkpointed and indexed under its state directory, with
    the configured models and content guard. Raises `DataRepositoryError` when it is unset."""
    root = settings.data_repository
    if root is None:
        raise DataRepositoryError(["DATA_REPOSITORY is not set"])
    graph = build_graph(checkpointer(checkpoint_path(settings, root)))
    embedder = embeddings(settings)

    def context() -> TriageContext:
        return TriageContext(load(root), content_guard(settings),
                             LabelIndex(state_path(settings, root) / "chroma", embedder,
                                        settings.embedding_model),
                             chat_model("judge", settings))

    return Runs(graph, context)


def pool_state(root: Path) -> tuple[DataRepository, dict[str, Score], dict[str, str], Pool]:
    """The data repository at `root` as it is now, its readable scores, the problems of the
    unreadable score files (by posting ID) and `pool.json`. Raises `DataRepositoryError` when
    the repository or `pool.json` does not load; a bad score file never raises. The three
    reads run under `write_gate`, so a delete shows in all of them or in none."""
    with write_gate:
        scores, problems = read_scores(root)
        return load(root), scores, problems, read_pool(root)


def reason_chips(repository: DataRepository) -> list[dict]:
    """The policy pack's reason chips as `{"id", "label", "polarity"}`."""
    return [{"id": chip.id, "label": chip.label, "polarity": chip.polarity}
            for chip in repository.policy_pack.reason_chips]


def problem(status: int, error: str, detail: str) -> JSONResponse:
    """An error response in the API's `{error, detail}` shape."""
    return JSONResponse({"error": error, "detail": detail}, status_code=status)


def refusal_detail(error: ScoreRefused) -> str:
    """The `detail` of a 409 for a refused single score: the rule IDs or guard categories, else
    what the refusal means."""
    if error.reason == "unscreened":
        return "no content-guard result and screening is off"
    return ", ".join(error.detail) or "flagged by the content guard"


def unknown_pass(pass_id: str) -> JSONResponse:
    """The 404 answer for a pass ID no checkpoint knows."""
    return problem(404, "not found", f"no pass {pass_id}")
