"""The localhost API (`design.md` → API and frontend). Serve it with
`uvicorn --factory jobadvaisor.api.app:create_app`. Every error answers `{error, detail}`."""

import re
from collections.abc import Callable
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Annotated, Literal, Self

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError, model_validator
from starlette.exceptions import HTTPException

from jobadvaisor.agent import AgentContext, Reply, answer
from jobadvaisor.data.loader import DataRepository, DataRepositoryError, load
from jobadvaisor.data.models import (
    HOST_PATTERN,
    ImportMapping,
    Label,
    Pool,
    PoolSettings,
    Posting,
    Score,
)
from jobadvaisor.data.writer import (
    read_pool,
    read_posting,
    read_scores,
    update_pool_settings,
    write_label,
    write_login_wall_hosts,
)
from jobadvaisor.index import LabelIndex, PostingIndex, state_path
from jobadvaisor.intake.entries import parse_entries, preview, tables_left_out
from jobadvaisor.intake.imports import ImportBusyError, Imports
from jobadvaisor.intake.ladder import login_wall_hosts
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
from jobadvaisor.triage.graph import TriageContext, build_graph, checkpoint_path, checkpointer
from jobadvaisor.triage.runs import RunBusyError, Runs, RunStateError

HTTP_URL = re.compile(r"https?://[^\s/]+\S*")
NOT_FOUND_DETAIL = "no attempt yielded the posting; paste its text or upload a PDF instead"


class BatchBody(BaseModel):
    """`POST /postings/batch` body: `{"urls": [...]}`, at least one string."""

    model_config = ConfigDict(extra="forbid")

    urls: list[StrictStr] = Field(min_length=1)


class UnscreenedAnswer(BaseModel):
    """`POST /pool/passes/{id}/unscreened` body: `{"continue": true}` continues with the
    unscreened postings, `{"continue": false}` aborts the pass."""

    model_config = ConfigDict(extra="forbid")

    proceed: bool = Field(alias="continue")


class PoolSettingsBody(BaseModel):
    """`PUT /pool/settings` body: both fields required."""

    model_config = ConfigDict(extra="forbid")

    correction_threshold: int = Field(ge=1)
    correction_rate: float = Field(ge=0, le=1)


class PostingPatch(BaseModel):
    """`PATCH /postings/{id}` body: corrected fields, the application `status` and/or
    `"release": true` for a posting the content guard flagged. At least one is required."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(None, min_length=1)
    company: str | None = Field(None, min_length=1)
    location_raw: str | None = Field(None, min_length=1)
    status: Literal["open", "applied", "done"] | None = None
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
FRONTEND_BUILD = REPOSITORY_ROOT / "frontend" / "dist"


def create_app(runs: Runs | None = None, intake: Intake | None = None,
               agent: Agent | None = None, frontend: Path = FRONTEND_BUILD,
               imports: Imports | None = None) -> FastAPI:
    """The app over `runs`, `intake`, `agent` (conversation → reply) and `imports`,
    by default those of the configured data repository (imports over `intake`); the default
    agent is built on its first message. The built frontend in `frontend` is served at `/`
    after the API routes, so they take precedence; without a build (no `index.html`) the API
    runs alone."""
    if runs is None or intake is None:
        settings = Settings()
        runs, intake = runs or configured_runs(settings), intake or configured_intake(settings)
    imports = imports or Imports(intake)
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

    @app.exception_handler(RequestValidationError)
    def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        detail = "; ".join(f"{'.'.join(map(str, item['loc']))}: {item['msg']}"
                           for item in error.errors())
        return problem(422, "invalid request", detail)

    @app.get("/pool")
    def read_pool_view() -> dict:
        """The posting pool: `rows` of every status in rank order, the correction `counter`,
        `settings`, `next_pass` and the policy pack's `reason_chips`. A corrupt score file shows
        as `score_problem` on its row; a data repository that does not load answers 500."""
        repository, scores, problems, pool = pool_state(intake.root)
        return {"rows": rank(repository, scores, problems, ALL_STATUSES),
                "counter": counter(repository, scores, pool),
                "settings": pool.settings.model_dump(),
                "next_pass": next_pass(repository, scores, pool),
                "reason_chips": reason_chips(repository)}

    @app.put("/pool/settings")
    def save_pool_settings(body: PoolSettingsBody) -> dict:
        """Store the correction threshold and rate in `pool.json` (passes are kept); answers
        `{"settings"}` as stored. 422 for a threshold below 1, a rate outside 0..1, a missing
        or an unknown field."""
        pool = update_pool_settings(intake.root, PoolSettings(**body.model_dump()))
        return {"settings": pool.settings.model_dump()}

    @app.get("/postings/{posting_id}")
    def read_posting_page(posting_id: str) -> dict:
        """Everything the posting page shows: its pool `row` (exploration off), the `posting`,
        its stored `score` (null without one) and the `examples` the judge compared it with that
        still exist. 404 for an unknown or unsafe ID."""
        repository, scores, problems, _ = pool_state(intake.root)
        posting = repository.postings.get(posting_id)
        if posting is None:
            return problem(404, "not found", f"no posting {posting_id}")
        row = next(row for row in rank(repository, scores, problems, ALL_STATUSES)
                   if row["posting_id"] == posting_id) | {"exploration": False}
        score = scores.get(posting_id)
        examples = [{"posting_id": example, "title": found.title, "company": found.company}
                    for example in (score.example_ids if score else [])
                    if (found := repository.postings.get(example))]
        return {"row": row, "posting": posting.model_dump(mode="json"),
                "score": score.model_dump(mode="json", exclude={"schema_version"})
                if score else None, "examples": examples,
                "reason_chips": reason_chips(repository)}

    @app.put("/postings/{posting_id}/rating")
    def rate_posting(posting_id: str, body: RatingBody) -> dict:
        """Store the user's rating of a posting at once, replacing an earlier one; answers its
        pool `row` (with the stored `label`), the `counter` and `next_pass` as `GET /pool` has
        them. A given verdict is kept; without one it is the polarity of the first chip that
        has one. The label replaces the earlier one whole, so an omitted `strength` clears it.
        404 for an unknown posting, 422 for an unknown chip (named), no verdict, or a
        `strength` without a given verdict (a chip-derived verdict has none)."""
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
    def start_pass() -> dict:
        """Start a scoring pass in the background; answers its `pass_id` at once, or 409
        naming the pass that is still computing. Takes no body. Postings with a rating are
        rescored when a correction was counted since the last pass. A repository that does not
        load still starts the pass, which then reports `failed` with the reason."""
        try:
            repository, scores, _, pool = pool_state(intake.root)
            rescore = counter(repository, scores, pool)["corrections"] > 0
        except DataRepositoryError:
            rescore = False
        try:
            return {"pass_id": runs.start(rescore)}
        except RunBusyError as error:
            return problem(409, "pass in progress", str(error))

    @app.get("/pool/passes/{pass_id}")
    def read_pass(pass_id: str) -> dict:
        """A pass's `status` (running, awaiting_answer, done, aborted, failed), `error`, `total`
        postings in its results, how many are `done` and the `unscreened` postings with title
        and company. 404 for an unknown pass."""
        run = runs.read(pass_id)
        if run is None:
            return unknown_pass(pass_id)
        results = run["results"]
        unfinished = {"pending", "extracted", "unscreened"}
        try:
            postings = load(intake.root).postings
        except DataRepositoryError:
            postings = {}
        unscreened = [{"posting_id": i, "title": postings[i].title if i in postings else i,
                       "company": postings[i].company if i in postings else i}
                      for i in run["unscreened"]]
        return {"pass_id": pass_id, "status": run["status"], "started_at": run["started_at"],
                "error": run["error"], "total": len(results),
                "done": sum(r["status"] not in unfinished for r in results.values()),
                "unscreened": unscreened}

    @app.post("/pool/passes/{pass_id}/unscreened", status_code=202)
    def answer_unscreened(pass_id: str, body: UnscreenedAnswer) -> dict:
        """Continue with or abort a pass paused over unscreened postings; it goes on in the
        background. 409 without that question pending or while another pass computes."""
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
        posting text results; for a URL, with the attempts, so the user can paste or upload."""
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
                "error": "posting not found",
                "detail": NOT_FOUND_DETAIL, "attempts": error.attempts}, status_code=422)
        except NoPostingTextError as error:
            return problem(422, "no posting text", str(error))
        return stored_answer(posting_id, posting, duplicate, attempts)

    @app.post("/postings/batch")
    def add_postings(body: BatchBody) -> dict:
        """Store the posting behind each of several URLs, one after the other. Answers 200 with
        `results`, one per URL in order: `{"url", "outcome": "stored" | "duplicate" | "failed",
        "posting_id"}` for the first two, `{"url", "outcome": "failed", "detail", "attempts"?}`
        for a failure, which never stops the rest. 422 for an empty list or a non-string."""
        results = []
        for url in (entry.strip() for entry in body.urls):
            try:
                if not HTTP_URL.fullmatch(url):
                    raise ValueError("url must be an http or https address")
                posting_id, _, duplicate, _ = add_from_url(intake, url)
                results.append({"url": url, "posting_id": posting_id,
                                "outcome": "stored" if duplicate is None else "duplicate"})
            except PostingNotFoundError as error:
                results.append({"url": url, "outcome": "failed", "detail": NOT_FOUND_DETAIL,
                                "attempts": error.attempts})
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
        """Correct title, company or location, set the application `status` and/or release a
        flagged posting; answers the stored posting (a `status` makes it schema version 2). 404
        for an unknown posting, 409 for releasing one the content guard did not flag."""
        try:
            read_posting(intake.root, posting_id)
        except ValueError:
            return problem(404, "not found", f"no posting {posting_id}")
        corrections = body.model_dump(exclude_unset=True, exclude={"release"})
        try:
            posting = amend_posting(intake.root, posting_id, corrections, bool(body.release))
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
                             chat_model("extractor", settings), chat_model("judge", settings))

    return Runs(graph, context)


def pool_state(root: Path) -> tuple[DataRepository, dict[str, Score], dict[str, str], Pool]:
    """The data repository at `root` as it is now, its readable scores, the problems of the
    unreadable score files (by posting ID) and `pool.json`. Raises `DataRepositoryError` when
    the repository or `pool.json` does not load; a bad score file never raises."""
    scores, problems = read_scores(root)
    return load(root), scores, problems, read_pool(root)


def reason_chips(repository: DataRepository) -> list[dict]:
    """The policy pack's reason chips as `{"id", "label", "polarity"}`."""
    return [{"id": chip.id, "label": chip.label, "polarity": chip.polarity}
            for chip in repository.policy_pack.reason_chips]


def problem(status: int, error: str, detail: str) -> JSONResponse:
    """An error response in the API's `{error, detail}` shape."""
    return JSONResponse({"error": error, "detail": detail}, status_code=status)


def unknown_pass(pass_id: str) -> JSONResponse:
    """The 404 answer for a pass ID no checkpoint knows."""
    return problem(404, "not found", f"no pass {pass_id}")
