"""Regenerate the README images `docs/images/pool.png` and `docs/images/posting.png`.

Command, from the repository root:
    uv run --directory backend python ../scripts/readme_images.py

Prerequisites: backend and frontend dependencies installed (`uv sync`, `npm --prefix frontend
ci`) and Playwright's Chromium (`uv run --directory backend playwright install chromium`).

It builds the frontend, then serves the real app on 127.0.0.1:8719 over a temporary copy of
`fixtures/demo-persona` with the scores of `fixtures/readme-scores` overlaid and committed to a
fresh git repository. The model parts record and raise, so no model is called and no key is
needed; data repository and state directory live inside the temporary directory, which is
removed when the script ends. The images are 1280 x 800 viewport shots in light mode, Europe/Berlin
time and reduced motion. Exit code 1 (and a list of what happened) when a model part was reached,
the server answered with status 500 or higher or the page reported an error.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import uvicorn
from langgraph.checkpoint.memory import InMemorySaver
from playwright.sync_api import expect, sync_playwright

from jobadvaisor.api.app import create_app
from jobadvaisor.intake.postings import Intake
from jobadvaisor.settings import REPOSITORY_ROOT
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.triage.graph import build_graph
from jobadvaisor.triage.runs import Runs

HOST, PORT = "127.0.0.1", 8719
URL = f"http://{HOST}:{PORT}"
OUT = REPOSITORY_ROOT / "docs/images"
FIXTURES = REPOSITORY_ROOT / "fixtures"
FILTER = "Noch nicht bewertet"


class ModelReached(RuntimeError):
    """Raised by every model stub; the script's exit code reports it."""


def run(*command: str, cwd: Path, env: dict[str, str] | None = None) -> None:
    """Run `command` in `cwd` (process environment unless `env` is given); raises
    `CalledProcessError` on a non-zero exit."""
    subprocess.run(command, cwd=cwd, env=env, check=True)


def build_frontend() -> None:
    """`npm --prefix frontend run build` without `VITE_APP_VERSION`, so frontend and backend both
    report `dev` and no stale-page banner appears."""
    env = {key: value for key, value in os.environ.items() if key != "VITE_APP_VERSION"}
    run("npm", "--prefix", "frontend", "run", "build", cwd=REPOSITORY_ROOT, env=env)


def prepare_data(root: Path) -> None:
    """Copy the demo persona to `root`, overlay the seeded scores and commit everything to a new
    git repository on `main` (no remote), so the backup control reads "Gesichert"."""
    shutil.copytree(FIXTURES / "demo-persona", root)
    shutil.copytree(FIXTURES / "readme-scores", root / "scores")
    run("git", "init", "-q", "-b", "main", cwd=root)
    run("git", "add", "-A", cwd=root)
    run("git", "-c", "user.name=readme-images", "-c", "user.email=readme-images@localhost",
        "commit", "-q", "-m", "Demo persona with sample scores", cwd=root)


def start_server(root: Path, reached: list[str]) -> uvicorn.Server:
    """Serve `create_app` over the data repository `root` on `HOST:PORT` in a thread and return
    the started server; set `.should_exit` to stop it. Every model part appends what was reached
    to `reached` and raises `ModelReached`. Exits with a message when the port is taken."""
    def reach(name: str):
        reached.append(name)
        raise ModelReached(f"model part reached: {name}")

    class NoModel:
        """A chat model whose every attribute access counts as a call."""

        def __getattr__(self, name: str):
            reach(f"intake model .{name}")

    app = create_app(Runs(build_graph(InMemorySaver()), lambda: reach("judge context")),
                     Intake(root, NoModel(), ContentGuard(None, {})),
                     agent=lambda messages: reach("agent"),
                     frontend=REPOSITORY_ROOT / "frontend/dist")
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        sys.exit("the app did not start")
    return server


def first_unrated_scored(root_url: str) -> dict:
    """The first row of `GET /pool` that is unrated (no verdict) and scored: the row the pool
    image selects at the top. Raises `StopIteration` when there is none."""
    with urllib.request.urlopen(f"{root_url}/pool") as response:
        rows = json.load(response)["rows"]
    return next(row for row in rows if row["state"] == "scored" and row["status"] == "open"
                and not (row["label"] and row["label"]["verdict"]))


def take_images(row: dict, problems: list[str]) -> None:
    """Write `pool.png` and `posting.png` for `row` (the pool's first unrated, scored posting).
    Page errors and responses with status 500 or higher are appended to `problems`."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_context(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1, color_scheme="light",
            timezone_id="Europe/Berlin", reduced_motion="reduce", locale="de-DE").new_page()
        page.set_default_timeout(15_000)
        page.on("pageerror", lambda error: problems.append(f"page error: {error}"))
        page.on("response", lambda response: response.status >= 500 and problems.append(
            f"server error: {response.status} {response.request.method} {response.url}"))

        def shoot(name: str) -> None:
            expect(page.get_by_role("button", name="Gesichert")).to_be_visible()
            page.evaluate("document.fonts.ready.then(() => true)")
            page.screenshot(path=OUT / name)

        page.goto(f"{URL}/#/pool")
        page.get_by_role("button", name=FILTER).click()
        first = page.get_by_role("list", name="Anzeigen").get_by_role("listitem").first
        expect(first.get_by_role("heading", name=row["title"])).to_be_visible()
        shoot("pool.png")

        page.goto(f"{URL}/#/anzeigen/{row['posting_id']}")
        expect(page.get_by_role("heading", level=1, name=row["title"])).to_be_visible()
        expect(page.get_by_text("Verglichen mit:")).to_be_visible()
        shoot("posting.png")
        browser.close()


def main() -> None:
    """Build the frontend, take both images and exit with code 1, listing what was recorded, when
    a model part was reached or the server or the page reported an error."""
    with socket.socket() as probe:
        if probe.connect_ex((HOST, PORT)) == 0:
            sys.exit(f"port {PORT} on {HOST} is taken; stop what uses it and run again")
    os.environ["GIT_CONFIG_GLOBAL"] = os.devnull  # as backend/tests/conftest.py: the user's git
    os.environ["GIT_CONFIG_NOSYSTEM"] = "1"  # configuration must not change the demo commit
    build_frontend()
    reached: list[str] = []
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="readme-images-") as temporary:
        root = Path(temporary) / "data"
        os.environ["DATA_REPOSITORY"] = str(root)  # before create_app builds its Settings
        os.environ["STATE_DIRECTORY"] = str(Path(temporary) / "state")
        prepare_data(root)
        server = start_server(root, reached)
        try:
            take_images(first_unrated_scored(URL), problems)
        except Exception as error:  # a reached stub usually surfaces as a timeout here
            problems.append(f"script error: {type(error).__name__}: {error}")
        finally:
            server.should_exit = True
    problems = [f"model call: {name}" for name in reached] + problems
    if problems:
        sys.exit("README images not trusted:\n" + "\n".join(f"- {line}" for line in problems))
    print(f"wrote {OUT / 'pool.png'} and {OUT / 'posting.png'}")


if __name__ == "__main__":
    main()
