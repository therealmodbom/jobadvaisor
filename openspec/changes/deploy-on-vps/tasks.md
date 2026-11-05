# Tasks

Order: the data repository on the server (#62) first, then the container (#61). Server steps run over SSH to the server (`<server>`); concrete host names, the private-network name and the remote are in the git-excluded `TASK.md`, never in this repository. Secrets are never printed; check names and modes only.

## 1. Data repository on the server (#62)

- [x] 1.1 Parallel work check (`git worktree list`, `gh pr list`, `git diff --name-only origin/main...HEAD` against `README.md`, `.env.example`, `AGENTS.md`, `.github/workflows/`) and confirm the existing local data repository is clean and equal to its `origin/main`. Verify: `git status --short` prints nothing and `git rev-parse HEAD origin/main` prints one hash twice after `git fetch`.
- [x] 1.2 Create `/srv/jobadvaisor/{data,state}` on the server, clone the data repository's remote (`<remote-url>`) into `data/`, set `safe.directory` for it and a git identity for commits made there. Verify: `git -C /srv/jobadvaisor/data log -1 --format=%H` equals the local computer's hash and `git status` is clean.
- [x] 1.3 Check that a push from the server works without changing the remote's history: create an empty commit on a scratch branch `write-test`, push it, delete that branch on the remote. Verify: `git ls-remote` on the remote lists `main` unchanged and no `write-test` afterwards.

## 2. Image (#61)

- [x] 2.1 Write the smoke check `deploy/smoke.sh` first: it takes an image name and fails unless, inside the image, `FRONTEND_BUILD/index.html` exists, Chromium launches through Playwright and loads a `data:` page, the process user is not root, and no `.env`, `local.env` or `*.json` data file sits under `/app`. Verify: run against `python:3.12-slim` and see it fail on the first check.
- [x] 2.2 Write `.dockerignore` and the multi-stage `Dockerfile` per design decision 1 (Node stage from `frontend/.nvmrc`, `uv sync --locked --no-dev` editable, Chromium in `/ms-playwright`, fixed non-root uid 10001, uvicorn on `0.0.0.0:8710`, one worker). Verify: `docker build` succeeds (locally if Docker is present, otherwise in the job of 2.3) and `deploy/smoke.sh` passes on it.
- [x] 2.3 Add an `image` job to `.github/workflows/ci.yml` that builds the image without pushing and runs `deploy/smoke.sh`. Verify: the job is green on the pushed branch.
- [x] 2.4 Add `.github/workflows/release.yml`: on tags `v*`, build `linux/amd64`, push `ghcr.io/therealmodbom/jobadvaisor` with the tag, and `latest` for non-prerelease tags only (`docker/metadata-action`); `permissions: contents: read, packages: write`. Verify: `actionlint` (or `gh workflow view`) accepts the file; the run itself is verified in 4.1.

## 3. Compose and server configuration

- [x] 3.1 Write `deploy/compose.yaml` per design decision 2: image `ghcr.io/therealmodbom/jobadvaisor:${JOBADVAISOR_TAG:-latest}`, port `127.0.0.1:${JOBADVAISOR_PORT:-8710}:8710`, `DATA_REPOSITORY=/data`, `STATE_DIRECTORY=/state`, volumes `/srv/jobadvaisor/data` and `/srv/jobadvaisor/state`, `env_file` for `settings.env` and `secrets.env`, `restart: unless-stopped`, a healthcheck on `/`. Verify: in a scratch copy of `deploy/` on the local computer holding two empty dummy env files (never the real ones), `docker compose config` renders, shows the loopback binding on 8710, and shows the changed host port when `JOBADVAISOR_PORT=8720` is set.
- [x] 3.2 Put the Compose file and `settings.env` (non-secret values only: models and URLs taken from the local `local.env`, no paths) on the server under `/srv/jobadvaisor`, with a project `.env` holding the one line `JOBADVAISOR_TAG=v0.1.0-rc1`, and `chown` `data/` and `state/` to uid 10001. Verify: `ls -ln` shows the owner, `settings.env` contains no key named in `SECRETS`, and `cat .env` in that directory prints exactly the one tag line (the resolved image is checked with `docker inspect` in 4.3; `docker compose config` is not used on the server, since it needs `secrets.env` and prints its values).
- [x] 3.3 The user creates `/srv/jobadvaisor/secrets.env` with mode 600 through a hidden prompt (a one-line command given to the user, never the values in the transcript). Verify: `stat -c %a` prints `600` and `cut -d= -f1` lists the expected key names only.

## 4. Release and deploy

- [x] 4.1 Push the prerelease tag `v0.1.0-rc1` on the branch head (ask the user first: a tag is public). Verify: the release run is green and `docker manifest inspect ghcr.io/therealmodbom/jobadvaisor:v0.1.0-rc1` succeeds.
- [x] 4.2 The user sets the GHCR package to public (GitHub web step). Verify: `docker pull` of the tag on the server succeeds without `docker login`.
- [x] 4.3 On the server run `docker compose up -d` in `/srv/jobadvaisor` (the tag comes from the project `.env` of 3.2). Verify: `docker inspect` shows the image tag `v0.1.0-rc1`, the container is healthy, `curl -s http://127.0.0.1:8710/pool` on the server returns JSON for the real data, and `docker inspect` shows the container user 10001.
- [x] 4.4 Publish the loopback port to the private network (README worked example: `tailscale serve --bg --https=<https-port> http://127.0.0.1:8710`) and confirm any existing entry still answers. Verify: from a local computer on the private network `curl -sI https://<server>.<tailnet>.ts.net:<https-port>/` returns 200; from the same computer against the server's public address `curl --max-time 5` on 8710 and `<https-port>` fails; the serve status shows the earlier entries unchanged.
- [x] 4.5 Change the port once: set `JOBADVAISOR_PORT=8720` in the project `.env`, `docker compose up -d`, then set it back. Verify: `curl -s http://127.0.0.1:8720/pool` answers and 8710 does not, then the reverse after the revert.

## 5. Walkthrough with the real client sequence

- [ ] 5.1 Browser on a local computer over the private network: open the pool, add a posting by link, score it, rate it, reload and see the rating. Verify: the rating shows after reload, and a new label file appears in `/srv/jobadvaisor/data` (`git status` on the server).
- [ ] 5.2 A link whose page builds its text with scripts, added through the UI. Verify: the intake outcome is stored and does not report `browser failed`.
- [ ] 5.3 The user opens the address on a second device (a phone) and rates one posting. Verify: the rating appears on the local computer after a reload.
- [ ] 5.4 `docker compose restart`, then `docker compose pull` and `up -d` (same tag, read from the project `.env`). Verify: `docker inspect` still shows `v0.1.0-rc1` and every rating from 5.1 and 5.3 is still there.

## 6. Sync and restore

- [ ] 6.1 On the server run the documented commit and push with the service running, pull on a local computer. Verify: the remote's `main` hash equals the server's, and the local data repository has the new labels after `git pull --ff-only`.
- [ ] 6.2 Recovery trial for a rejected push, on a scratch branch of the real remote (deleted afterwards): push a non-overlapping change from a local computer so the server's push is rejected, and follow the documented recovery on the server (service stopped, then started with `up -d`); then make a conflicting change to one file on both sides and run it again, once resolving it and once aborting. Verify: the first run leaves the server containing both changes with a clean `git status`; the second stops naming the conflicting file with the service still stopped; after the abort and `up -d` the pool shows exactly the pre-sync ratings, after the resolution it shows the resolved file; `git log` shows nothing lost on either side and nothing was force-pushed.
- [ ] 6.3 Restore trial: stop the service, move `data/` and `state/` aside, clone from the remote, `chown`, `docker compose up -d` (tag from the project `.env`). Verify: the image tag is unchanged and the pool shows the same postings, scores and ratings as before, and `diff -r` of the old and new `data/` (excluding `.git`) is empty.

## 7. Documentation

- [ ] 7.1 Write ADR 0009 (`docs/decisions/0009-container-from-ghcr-behind-tailscale-serve.md`: GHCR over building on the server, publishing the loopback port with `tailscale serve` over binding the Tailscale IP, the server working on a clone of the data repository's remote with a manual, conflict-stopping sync) and add it to the ADR index. Verify: the five ADR sections are present and the design's link resolves.
- [ ] 7.2 Add a README "Deployment" section: first-time setup of the server (directories, clone, files, publishing the loopback port with `tailscale serve` as the worked example and a note that any private-network forwarder works), the update command with the `JOBADVAISOR_TAG` and `JOBADVAISOR_PORT` lines of the project `.env`, the normal commit and push, and the recovery for a rejected push (stop the service, commit, bring in the remote's changes, push, `docker compose up -d`, which does not happen by itself) with how to resolve a conflict or abort on the server while the service stays stopped, and the note that #63 replaces both, and the restore from 6.3. Verify: following the section's commands in order reproduces the state of tasks 1 to 4 (read it once against the shell history).
- [ ] 7.3 Update the AGENTS.md "Current state" pointer (this change in, oldest entry out). Verify: the list holds two entries.

## 8. Final checks

- [ ] 8.1 Run `env -C backend uv run pytest -q`, `env -C backend uv run ruff check .`, `npm --prefix frontend test` and `npm --prefix frontend run lint`, and confirm `tests/test_env_example.py` passes unchanged. Verify: all four commands exit 0.
- [ ] 8.2 Self-review the diff and run `openspec validate deploy-on-vps --strict`. Verify: no findings left open and validation passes.
