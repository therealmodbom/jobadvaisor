# Design

## Context

See proposal.md for motivation and the archived `version-display` change for the version mechanism (build argument, `VERSION` file, frontend build constant), which stays as it is.

- The backend has one version route today, `GET /version` (`create_app` in `backend/jobadvaisor/api/app.py`), with `VERSION_FILE` read per request. Its tests are three in `backend/tests/test_api.py`, and the smoke check calls it through a `TestClient` over stub dependencies (`deploy/smoke.sh`).
- The data repository is loaded per request: `load(root)` and `read_pool(root)` raise `DataRepositoryError` when it does not load; `pool_state` adds `read_scores`, which never raises.
- `api()` in `frontend/src/api.ts` rejects a non-2xx answer with an `ApiError` that carries the parsed body in `body`.
- `deploy/compose.yaml` checks `GET /` with `urllib.request.urlopen`, which raises on a 4xx or 5xx status. `restart: unless-stopped` restarts a stopped container, not an unhealthy one.
- `/version` is in no release: the server runs `v0.1.0`, which predates it.

## Goals / Non-Goals

**Goals:**
- One route answers both "does the backend work" and "which release".
- The version stays readable when the data repository does not load.

**Non-Goals:**
- No readiness/liveness split and no further checks (see proposal Non-goals).
- No compatibility alias for `/version`.

## Decisions

1. **`GET /health` replaces `GET /version`, in one route.** It answers `{"status": "ok"|"fail", "checks": {"data_repo": "ok"|"<error>"}, "version": "<tag or dev>"}`, status 200 for `ok` and 503 for `fail`, built with `JSONResponse` so the 503 carries the whole body (the API's `problem()` shape `{error, detail}` would drop the version). The docstring names the shape, as for the other routes. The shape follows the common health-check convention (status, per-check results, version) so that a later settings page can add checks under `checks` without changing the top level. Alternative: keep `/version` next to a new `/health`. Rejected (owner decision): two routes for one backend, one of them removed later. Alternative: answer 200 with `status: fail`. Rejected: Docker's check and any other client read the HTTP status, and a 200 would hide the failure from them.

2. **The check is `load(root)` and `read_pool(root)` on `intake.root`, catching `DataRepositoryError` only.** That is the load `/pool` needs, without `read_scores`: a bad score file never raises, so reading every score on each check would only cost time. Any other exception is a bug and answers 500 through the existing handler, which the Compose check also counts as failed. `checks.data_repo` carries `str(error)`. `/pool` already shows the same text as `detail` of its 500, so the health answer adds no exposure; the route has no auth, like every route (the container listens on loopback). Alternative: reuse `pool_state`. Rejected for the cost above. Cost accepted: a full load every 30 seconds by the Compose check; the repository is local and small.

3. **The Compose check requests `/health`.** The command stays the same `urlopen` one-liner with the path changed; a 503 raises, so the container turns `unhealthy`. `retries: 3` and `start_period: 30s` stay, so a sync that holds the repository for a moment does not flip it at once. No restart follows, since the policy does not restart unhealthy containers: a data repository that does not load is fixed by the user (recovery section of the README), not by a restart.

4. **The frontend reads the version from `/health`, also from a 503.** `useBackendVersion` calls `api('/health')`. On success it takes `answer.version`; on an `ApiError` with `status === 503` and a string `body.version` it takes that. Every other failure (unreachable, 404 from an old backend, a 503 without a version from a proxy) changes nothing, as before. The hook's one-sentence contract and the footer stay as they are. Alternative: a second request to `/version` when `/health` fails. Rejected: that is the two-route design again.

5. **The smoke check builds its app over a stub whose `root` is an empty directory.** The empty directory does not load, so the real route answers 503 with its version, and the check asserts only `version` of the body. That is what the deployment spec asks ("whether or not a data repository is present") and it keeps the check independent of fixture data in the image. Both existing checks (the build's version and the environment override) use the same script.

## Risks / Trade-offs

- [A `compose.yaml` with the `/health` check run against an image of `v0.1.0` or older marks the container unhealthy: there is no such route there, so it answers 404] → The README says the new check needs the release that ships it, and `compose.yaml` is copied once to the server (README setup), so the server's file only changes when the user copies it again.
- [An unhealthy container is not restarted] → Intended (decision 3); the status shows in `docker compose ps`, and the version still shows on the page.
- [An old tab from before this change polls `/version`, which the new backend no longer has] → Impossible for a deployed tab: `/version` was never released. A tab served by a local build during development reloads on the next start.
