import functools
import json
import os
import shutil
import subprocess
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import Field

from jobadvaisor.settings import Settings

AT = "2026-01-05T09:00:00Z"
PROFILE = {"schema_version": "1", "summary": "Backend developer"}
POLICY_PACK = {"schema_version": "1", "reason_chips": [{"id": "too-junior", "label": "too junior"}]}


@pytest.fixture(autouse=True)
def no_settings_from_the_process_environment(monkeypatch):
    """Drop every setting the process environment carries before each test. An editor's test
    runner can load the repository's `.env` into it, and a real key would then change results
    or make live calls; tests that need a setting pass it explicitly or set it themselves."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


@pytest.fixture(autouse=True)
def no_company_lookup_over_the_network(monkeypatch):
    """Intake looks company facts up on linkedin.com or the employer's site; no test may reach
    them. `test_company_intake.py` puts a fake-served lookup in its place."""
    monkeypatch.setattr("jobadvaisor.intake.postings.look_up", lambda *args, **kwargs: None)


@pytest.fixture(autouse=True)
def no_secrets_from_the_keychain(monkeypatch):
    """Keep the user's real Keychain out of tests, for the same reason as above."""
    monkeypatch.setattr("jobadvaisor.settings.keychain_value", lambda account: None)


POSTING = {
    "schema_version": "1",
    "title": "Backend Engineer",
    "company": "Example Corp",
    "location_raw": "Remote",
    "text": "We build things.",
    "source_type": "text",
    "added_at": AT,
}
LABEL = {"schema_version": "1", "kind": "rating", "verdict": "positive", "chips": ["too-junior"],
         "rated_at": AT}


class FakeStructuredModel:
    """Stands in for a chat model's `with_structured_output`: returns `responses` in order,
    validated against the requested schema, and records each prompt and schema."""

    def __init__(self, *responses: dict):
        self.responses = list(responses)
        self.prompts: list = []
        self.schemas: list = []

    def with_structured_output(self, schema):
        self.schemas.append(schema)
        return RunnableLambda(lambda messages: self._answer(schema, messages))

    def _answer(self, schema, messages):
        self.prompts.append(messages)
        return schema.model_validate(self.responses.pop(0))


class ScriptedModel:
    """Chat-model stand-in for many calls: `with_structured_output(schema)` answers each call
    with `answer(schema, prompt)` validated against `schema`, where `prompt` is the last
    message's text, and records every prompt in `calls`."""

    def __init__(self, answer):
        self.answer = answer
        self.calls: list[str] = []

    def with_structured_output(self, schema):
        return RunnableLambda(lambda messages: self._answer(schema, messages))

    def _answer(self, schema, messages):
        prompt = messages[-1].content
        self.calls.append(prompt)
        return schema.model_validate(self.answer(schema, prompt))


class ToolScriptModel(BaseChatModel):
    """Tool-calling chat-model stand-in for agents: each call answers with the next planned
    tool call from `plan` (`(tool name, args)`, or a list of them for parallel calls in one
    turn), then with a plain "done" once the plan is used up. Records every call's messages in
    `seen` and the bound tools' names in `tool_names`."""

    plan: list = Field(default_factory=list)
    seen: list = Field(default_factory=list)
    tool_names: list = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        self.tool_names = [tool.name for tool in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.seen.append(list(messages))
        if self.plan:
            step = self.plan.pop(0)
            calls = step if isinstance(step, list) else [step]
            message = AIMessage("", tool_calls=[
                {"name": name, "args": args, "id": f"call-{len(self.seen)}-{n}"}
                for n, (name, args) in enumerate(calls)])
        else:
            message = AIMessage("done")
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def _llm_type(self) -> str:
        return "tool-script"

    def seen_text(self) -> str:
        """Every message content the model received, as one text."""
        return "\n".join(str(message.content) for call in self.seen for message in call)


def unknown_features(schema, prompt) -> dict:
    """An extractor answer: "unknown" for every feature of the requested result model."""
    return {field.alias: "unknown" for field in schema.model_fields.values()}


def write_json(path: Path, data: dict) -> Path:
    """Write `data` as JSON to `path`, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


SLOW_SECONDS = 3


class QuietHandler(SimpleHTTPRequestHandler):
    """Static file handler without access log; `/gone.html` answers 410 with an empty body and
    `/slow.html` answers 200 only after `SLOW_SECONDS`."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path not in ("/gone.html", "/slow.html"):
            return super().do_GET()
        if self.path == "/slow.html":
            time.sleep(SLOW_SECONDS)
        status = 410 if self.path == "/gone.html" else 200
        body = b"" if status == 410 else b"<p>slow</p>"
        try:  # the client may have timed out and hung up already
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


@pytest.fixture(scope="session")
def site():
    """Base URL of a local server serving `fixtures/intake/pages`; other paths answer 404,
    except `/gone.html` (410, empty) and `/slow.html` (200 after `SLOW_SECONDS`)."""
    from jobadvaisor.settings import REPOSITORY_ROOT

    pages = REPOSITORY_ROOT / "fixtures/intake/pages"
    server = ThreadingHTTPServer(("127.0.0.1", 0),
                                 functools.partial(QuietHandler, directory=str(pages)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture
def demo_copy(tmp_path) -> Path:
    """A copy of the demo persona under `tmp_path`, so runs never write into `fixtures/`."""
    from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY

    return Path(shutil.copytree(FIXTURE_DIRECTORY, tmp_path / "demo-persona"))


@pytest.fixture(scope="session")
def deepeval_state(tmp_path_factory) -> Path:
    """A state directory for DeepEval, which fixes its folder at the first import in a process."""
    return tmp_path_factory.mktemp("deepeval-state")


@pytest.fixture
def deepeval(deepeval_state):
    """DeepEval loaded through `load_deepeval`, writing under `deepeval_state`."""
    from jobadvaisor.evals.deepeval_runtime import load_deepeval

    return load_deepeval(deepeval_state)


@pytest.fixture
def data_repository(tmp_path) -> Path:
    """A valid data repository with one labeled posting `p1` and one unlabeled posting `p2`."""
    write_json(tmp_path / "profile.json", PROFILE)
    write_json(tmp_path / "policy-pack.json", POLICY_PACK)
    write_json(tmp_path / "postings/p1.json", POSTING)
    write_json(tmp_path / "postings/p2.json", {**POSTING, "title": "Data Engineer"})
    write_json(tmp_path / "labels/p1.json", LABEL)
    return tmp_path


def git(root: Path, *args: str) -> str:
    """Run `git -C root args` for a test and return its stdout; a failing command raises."""
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                          text=True).stdout


@pytest.fixture(autouse=True)
def git_without_user_configuration(monkeypatch):
    """Keep the user's global git configuration (identity, `core.hooksPath` with a hook that
    blocks commits to `main`) out of tests that run real git."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def backed_up(demo_copy, tmp_path) -> SimpleNamespace:
    """The demo persona copy as a git repository on `main` with one commit, a local bare
    repository `remote` as `origin` and `main` pushed to it as its upstream. Has `root` and
    `remote`. The repository has its own identity, so commits need no global configuration."""
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "-b", "main", str(remote))
    git(demo_copy, "init", "-b", "main")
    git(demo_copy, "config", "user.name", "Test")
    git(demo_copy, "config", "user.email", "test@example.com")
    git(demo_copy, "add", "-A")
    git(demo_copy, "commit", "-m", "Initial data")
    git(demo_copy, "remote", "add", "origin", str(remote))
    git(demo_copy, "push", "-u", "origin", "main")
    return SimpleNamespace(root=demo_copy, remote=remote)
