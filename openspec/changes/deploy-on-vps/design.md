# Design

## Context

See proposal.md for motivation. Facts the design relies on (read from the code):

- `create_app` mounts `frontend/dist` at `/` after the API routes when `index.html` exists, and the frontend calls the API with relative paths. One uvicorn process on port 8710 serves everything; no CORS, no second server.
- `REPOSITORY_ROOT` is `Path(__file__).parents[2]` of `settings.py`, and `FRONTEND_BUILD` hangs off it. The image must keep the repository layout and install the backend **editable**, otherwise the package lands in `site-packages` and the build is not found.
- Settings come from the Keychain (absent on Linux, the lookup returns `None`), the environment, `.env` and `local.env` in `REPOSITORY_ROOT`. The image has neither file; Compose supplies the environment. No settings change is needed.
- Chromium is launched by Playwright in `intake/fetch.py` (default launch, no sandbox flag set). The image needs the browser and its system libraries.
- The app only writes files into the data repository and never commits (ADR 0001). Run state (checkpoints, vector index) lives under `STATE_DIRECTORY`, one subdirectory per data repository, and rebuilds from the data.
- The VPS is on the Tailnet, runs Docker and Compose, and already uses `tailscale serve` on port 443 for another service. It reaches the data repository's bare remote on the NAS through an SSH key and host alias it already has (`<nas-remote>` below).

## Goals / Non-Goals

**Goals:**

- One image, one command to update, no public port, persistent data.
- A cutover that loses no pending rating and a restore path that was run once.

**Non-Goals:**

- Anything the proposal lists. No eval: this change touches no LLM-backed behavior, so there is no eval metric or data to name.

## Decisions

**1. Image layout.** Multi-stage build. Stage one: Node (version from `frontend/.nvmrc`) runs `npm ci` and `npm run build`. Stage two: `python:3.12-slim`, `uv sync --locked --no-dev` into `/app/backend/.venv` (editable, keeps `parents[2]` at `/app`), the built `dist` copied to `/app/frontend/dist`, then `playwright install --with-deps chromium` with `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright`. The process runs as a non-root user and starts `uvicorn --factory jobadvaisor.api.app:create_app --host 0.0.0.0 --port 8710` with one worker (runs and checkpoints are in-process). The image is large because of Chromium; accepted, it is pulled once per release.

**2. Compose binds to loopback.** The service publishes `127.0.0.1:8710:8710` only. The container listens on all its interfaces, but the host never exposes it publicly. Settings: the Compose file sets `DATA_REPOSITORY=/data` and `STATE_DIRECTORY=/state`, reads non-secret settings (models, URLs) from `settings.env` and secrets from `secrets.env` (mode 600, never in the image or the repository), both in the deployment directory on the VPS. The deployment directory is `/srv/jobadvaisor` with `data/` (the clone), `state/`, both files and the Compose file.

**3. `tailscale serve` on its own HTTPS port.** `tailscale serve --bg --https=8443 http://127.0.0.1:8710` publishes the service at `https://<vps>.<tailnet>.ts.net:8443`, with the certificate Tailscale already issues for that name. Port 443 and its existing entry stay untouched. The alternative, publishing on the Tailnet IP, gives plain HTTP and fails to start the container if Docker comes up before Tailscale; rejected. A mistaken Compose edit can never expose the port publicly, because the host side is loopback. See [ADR 0009](../../../docs/decisions/0009-container-from-ghcr-behind-tailscale-serve.md).

**4. Release through GHCR.** A workflow on tags `v*` builds the image with `docker/build-push-action` and pushes `ghcr.io/therealmodbom/jobadvaisor` with the tag and `latest`, using the job's `GITHUB_TOKEN` (`packages: write`). The existing `eval-*` tags do not match. The update on the VPS is `docker compose pull` then `docker compose up -d` in the deployment directory. The repository is public (#44 (Make jobadvaisor public and turn on GitHub's secret and branch protection)), but GHCR creates a package private on its first push. The owner sets it to public once in the package settings (a GitHub web step, no code), and the VPS then pulls without a login. The image holds no secret and no personal data, so public is safe; the spec requires that. If the owner keeps it private, the VPS logs in once with a `read:packages` token entered through a hidden prompt. Building on the VPS was rejected: every update would compile Node and install Chromium on a server that also runs another service. The tagged commit is not retested by the release workflow; it was tested on its branch. A `docker build` job in `ci.yml` (no push) plus a smoke check catches a broken Dockerfile before the tag, not at it.

**5. Data on the VPS, VPS as only writer.** `/srv/jobadvaisor/data` is a clone of the bare remote `ssh://<nas-remote>/<path>/jobadvaisor-data.git`, mounted at `/data`. The container user owns the working tree so the app can write; git on the host runs as root with `safe.directory` set for that path, so git objects are root-owned and the app never needs to touch `.git`. Until #63, the owner commits and pushes by hand on the VPS with the three documented commands; an unpushed rating exists only on the VPS. The Mac only pulls. Cutover order: confirm the Mac's data repository is clean and pushed, clone on the VPS, start the container, verify, then stop using the Mac's copy for writes. No migration code: the data format is unchanged.

**6. Restore.** Documented as: stop the service, move `data/` and `state/` aside, `git clone` from the NAS into `data/`, start the service; the state rebuilds from the data (ADR 0004). Tried once on the VPS before the change ends, against the real remote, comparing the file list with the moved-aside copy.

**7. Verification is a walkthrough, not a unit test.** The container passes the client sequence of TASK.md: UI loads from Mac and phone over the Tailnet, add a posting, score it, rate it, reload and see the rating, restart the container and see it persist, then the restore. The Dockerfile smoke check in CI covers only what a test can: the build exists at the expected path and Chromium launches in the image.

## Risks / Trade-offs

- **No login, the Tailnet is the only control** → the host side is loopback and `tailscale serve` is the single entry; anyone on the Tailnet reaches the app. Acceptable for one owner's devices. A shared Tailnet would need an ACL first.
- **Unpushed data lives only on the VPS until #63** → the README states the push command; a lost VPS loses the unpushed ratings. Fixed by #63, not here.
- **Two devices writing at once** (ADR 0001: no concurrent writers) → one owner, one instance; the files are small and the last write wins. No guard is added.
- **Image size and cold pull** → Chromium dominates; accepted, pulled once per release.
- **Playwright default launch in a container** → it runs without the Chromium sandbox, so a malicious page could escape more easily than in a normal browser. Mitigated by the non-root user and by fetching only URLs the owner submits.
- **A public image is downloadable by anyone** → it holds only public code and a browser; the CI smoke check searches it for secret and data files.
- **CPU architecture** → the VPS is `x86_64`, so the workflow builds `linux/amd64` only. An ARM host would need `linux/arm64` added.
