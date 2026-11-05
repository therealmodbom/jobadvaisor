# Tasks

Order: the data repository on the VPS (#62 (Data repository on the VPS with the NAS as its backup remote)) first, then the container (#61 (Deploy as a container on the VPS, reachable over the Tailnet)). Server steps run over SSH to the VPS (`<vps>`); concrete host names, the Tailnet name and the NAS remote are in the git-excluded `TASK.md`, never in this repository. Secrets are never printed; check names and modes only.

## 1. Data repository on the VPS (#62)

- [ ] 1.1 Parallel work check (`git worktree list`, `gh pr list`, `git diff --name-only origin/main...HEAD` against `README.md`, `.env.example`, `AGENTS.md`, `.github/workflows/`) and confirm the Mac's `jobadvaisor-data` is clean and equal to `origin/main`. Verify: `git status --short` prints nothing and `git rev-parse HEAD origin/main` prints one hash twice after `git fetch`.
- [ ] 1.2 Create `/srv/jobadvaisor/{data,state}` on the VPS, clone the NAS remote (`ssh://<nas-remote>/<path>/jobadvaisor-data.git`) into `data/`, set `safe.directory` for it and a git identity for commits made there. Verify: `git -C /srv/jobadvaisor/data log -1 --format=%H` equals the Mac's hash and `git status` is clean.
- [ ] 1.3 Check that a push from the VPS works without changing the remote's history: create an empty commit on a scratch branch `vps-write-test`, push it, delete that branch on the remote. Verify: `git ls-remote` on the NAS lists `main` unchanged and no `vps-write-test` afterwards.

## 2. Image (#61)

- [ ] 2.1 Write the smoke check `deploy/smoke.sh` first: it takes an image name and fails unless, inside the image, `FRONTEND_BUILD/index.html` exists, Chromium launches through Playwright and loads a `data:` page, the process user is not root, and no `.env`, `local.env` or `*.json` data file sits under `/app`. Verify: run against `python:3.12-slim` and see it fail on the first check.
- [ ] 2.2 Write `.dockerignore` and the multi-stage `Dockerfile` per design decision 1 (Node stage from `frontend/.nvmrc`, `uv sync --locked --no-dev` editable, Chromium in `/ms-playwright`, fixed non-root uid 10001, uvicorn on `0.0.0.0:8710`, one worker). Verify: `docker build` succeeds (locally if Docker is present, otherwise in the job of 2.3) and `deploy/smoke.sh` passes on it.
- [ ] 2.3 Add an `image` job to `.github/workflows/ci.yml` that builds the image without pushing and runs `deploy/smoke.sh`. Verify: the job is green on the pushed branch.
- [ ] 2.4 Add `.github/workflows/release.yml`: on tags `v*`, build `linux/amd64`, push `ghcr.io/therealmodbom/jobadvaisor` with the tag, and `latest` for non-prerelease tags only (`docker/metadata-action`); `permissions: contents: read, packages: write`. Verify: `actionlint` (or `gh workflow view`) accepts the file; the run itself is verified in 4.1.

## 3. Compose and VPS configuration

- [ ] 3.1 Write `deploy/compose.yaml` per design decision 2: image `ghcr.io/therealmodbom/jobadvaisor:${JOBADVAISOR_TAG:-latest}`, port `127.0.0.1:8710:8710`, `DATA_REPOSITORY=/data`, `STATE_DIRECTORY=/state`, volumes `/srv/jobadvaisor/data` and `/srv/jobadvaisor/state`, `env_file` for `settings.env` and `secrets.env`, `restart: unless-stopped`, a healthcheck on `/`. Verify: in a scratch copy of `deploy/` on the Mac holding two empty dummy env files (never the real ones), `docker compose config` renders and shows the loopback binding.
- [ ] 3.2 Put the Compose file and `settings.env` (non-secret values only: models and URLs taken from the Mac's `local.env`, no paths) on the VPS under `/srv/jobadvaisor`, with a project `.env` holding the one line `JOBADVAISOR_TAG=v0.1.0-rc1`, and `chown` `data/` and `state/` to uid 10001. Verify: `ls -ln` shows the owner, `settings.env` contains no key named in `SECRETS`, and `cat .env` in that directory prints exactly the one tag line (the resolved image is checked with `docker inspect` in 4.3; `docker compose config` is not used on the VPS, since it needs `secrets.env` and prints its values).
- [ ] 3.3 The owner creates `/srv/jobadvaisor/secrets.env` with mode 600 through a hidden prompt (a one-line command given to the owner, never the values in the transcript). Verify: `stat -c %a` prints `600` and `cut -d= -f1` lists the expected key names only.

## 4. Release and deploy

- [ ] 4.1 Push the prerelease tag `v0.1.0-rc1` on the branch head (ask the owner first: a tag is public). Verify: the release run is green and `docker manifest inspect ghcr.io/therealmodbom/jobadvaisor:v0.1.0-rc1` succeeds.
- [ ] 4.2 The owner sets the GHCR package to public (GitHub web step). Verify: `docker pull` of the tag on the VPS succeeds without `docker login`.
- [ ] 4.3 On the VPS run `docker compose up -d` in `/srv/jobadvaisor` (the tag comes from the project `.env` of 3.2). Verify: `docker inspect` shows the image tag `v0.1.0-rc1`, the container is healthy, `curl -s http://127.0.0.1:8710/pool` on the VPS returns JSON for the real data, and `docker inspect` shows the container user 10001.
- [ ] 4.4 Publish with `tailscale serve --bg --https=8443 http://127.0.0.1:8710` and confirm the existing entry on 443 still answers. Verify: from the Mac `curl -sI https://<vps>.<tailnet>.ts.net:8443/` returns 200; from the Mac against the VPS's public address `curl --max-time 5` on ports 8710 and 8443 fails; `tailscale serve status` shows the same 443 entry as before the change.

## 5. Walkthrough with the real client sequence

- [ ] 5.1 Browser from the Mac over the Tailnet: open the pool, add a posting by link, score it, rate it, reload and see the rating. Verify: the rating shows after reload, and a new label file appears in `/srv/jobadvaisor/data` (`git status` on the VPS).
- [ ] 5.2 A link whose page builds its text with scripts, added through the UI. Verify: the intake outcome is stored and does not report `browser failed`.
- [ ] 5.3 The owner opens the address on the phone and rates one posting. Verify: the rating appears on the Mac after a reload.
- [ ] 5.4 `docker compose restart`, then `docker compose pull` and `up -d` (same tag, read from the project `.env`). Verify: `docker inspect` still shows `v0.1.0-rc1` and every rating from 5.1 and 5.3 is still there.

## 6. Backup and restore

- [ ] 6.1 On the VPS commit and push the data with the three documented commands, pull on the Mac. Verify: the NAS `main` hash equals the VPS's, and the Mac's `jobadvaisor-data` has the new labels after `git pull --ff-only`.
- [ ] 6.2 Restore trial: stop the service, move `data/` and `state/` aside, clone from the NAS, `chown`, `docker compose up -d` (tag from the project `.env`). Verify: the image tag is unchanged and the pool shows the same postings, scores and ratings as before, and `diff -r` of the old and new `data/` (excluding `.git`) is empty.

## 7. Documentation

- [ ] 7.1 Write ADR 0009 (`docs/decisions/0009-container-from-ghcr-behind-tailscale-serve.md`: GHCR over building on the VPS, `tailscale serve` over binding the Tailnet IP, VPS as sole writer with the NAS as backup remote) and add it to the ADR index. Verify: the five ADR sections are present and the design's link resolves.
- [ ] 7.2 Add a README "Deployment" section: first-time setup of the VPS (directories, clone, files, `tailscale serve`), the update command with the `JOBADVAISOR_TAG` line of the project `.env`, the manual commit-and-push commands with the note that #63 (Back up user data automatically) replaces them, and the restore from 6.2. Verify: following the section's commands in order reproduces the state of tasks 1 to 4 (read it once against the shell history).
- [ ] 7.3 Update the AGENTS.md "Current state" pointer (this change in, oldest entry out). Verify: the list holds two entries.

## 8. Final checks

- [ ] 8.1 Run `env -C backend uv run pytest -q`, `env -C backend uv run ruff check .`, `npm --prefix frontend test` and `npm --prefix frontend run lint`, and confirm `tests/test_env_example.py` passes unchanged. Verify: all four commands exit 0.
- [ ] 8.2 Self-review the diff and run `openspec validate deploy-on-vps --strict`. Verify: no findings left open and validation passes.
