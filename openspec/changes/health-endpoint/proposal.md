# Proposal

## Why

The version display (#67) added `GET /version` to the backend. The backend has no health endpoint, and the Compose healthcheck only requests `/`, which proves the static frontend is served and nothing about the data repository. A health endpoint is the usual place for a version, so the version moves there before the first deployment of `/version`, instead of keeping two endpoints and removing one later.

## What Changes

- The backend answers `GET /health` with `{"status", "checks": {"data_repo"}, "version"}`: `status` is `ok` or `fail`, `checks.data_repo` is `ok` or the load error, `version` is the release tag or `dev`. The status is 200 for `ok` and 503 for `fail`, with the same body shape.
- `GET /version` is removed. Nothing has deployed it.
- The deployment's Compose healthcheck requests `/health` instead of `/`, so a data repository that does not load makes the container `unhealthy`.
- The page reads the backend version from the `/health` answer, also from a 503 answer, so the footer and the stale-page banner keep working while the data repository is broken. The footer itself does not change.
- The smoke check and the README follow.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `deployment`: adds the health answer and the Compose healthcheck on it; the version is read from that answer.
- `web-ui`: the footer still shows the backend version when the health answer says `fail`.

## Impact

- Backend: `backend/jobadvaisor/api/app.py` (route replaced), `backend/tests/test_api.py`.
- Frontend: `frontend/src/lib/version.ts`, `frontend/src/test-api.ts`, `frontend/src/version.test.tsx`, `frontend/vite.config.ts` (`/health` replaces `/version` in `API_ROUTES`).
- Deployment: `deploy/compose.yaml`, `deploy/smoke.sh`, README.
- No new dependency, no data format change. The route is not in a release yet, so nothing external uses `/version`.

## Non-goals

- No status hint in the footer: the footer shows versions only, the status belongs to the healthcheck.
- No detailed status in the health answer beyond the one data repository check; richer status for a settings page is a later change.
- No check of the LLM provider, the state directory or the data remote: they would make the container `unhealthy` for causes a restart does not fix.
- No change to the version mechanism (build argument, `VERSION` file, frontend build constant) or to the stale-page banner.
- No LLM-backed behavior, so no eval.
