# Tasks

## 1. Backend

- [ ] 1.1 Test first, then replace `GET /version` in `create_app` with `GET /health` per design decisions 1 and 2, with a docstring naming the answer shape and the 200/503 contract; verify `env -C backend uv run pytest -q tests/test_api.py` covers: a loading repository (200, `ok`, version), an invalid `pool.json` (503, `fail`, the load error in `checks.data_repo`, version still present), a missing `VERSION` file (`dev`), the trimmed file content, and an environment variable of any name not changing the version; the three `/version` tests are replaced, not kept

## 2. Frontend

- [ ] 2.1 Test first, then point `useBackendVersion` in `frontend/src/lib/version.ts` at `/health` per design decision 4, taking `version` from a 503 `ApiError` body too, and update its doc comment; verify `frontend/src/version.test.tsx` covers a 200 answer, a 503 answer with a version (footer shows it, no banner for equal versions, banner for a different one) and a 503 without a version (unknown, no mismatch)
- [ ] 2.2 Replace `/version` by `/health` in `API_ROUTES` of `frontend/vite.config.ts` and the default route in `frontend/src/test-api.ts` (`GET /health` answering `{status: 'ok', checks: {data_repo: 'ok'}, version: 'dev'}`); verify no `/version` reference remains in `frontend/` (`grep -rn "/version" frontend/src frontend/vite.config.ts`) and `npm test` passes

## 3. Deployment

- [ ] 3.1 Change the healthcheck path in `deploy/compose.yaml` from `/` to `/health`; verify with a scratch copy and dummy env files that `docker compose config` renders the new test command
- [ ] 3.2 Update `deploy/smoke.sh` per design decision 5 (stub `intake` with an empty directory as `root`, request `/health`, assert only `version`); verify the script passes on an image built with `--build-arg APP_VERSION=v0.0.0-ci`, fails on one built without it, and its comments no longer name `/version`
- [ ] 3.3 README: in "Which version runs" add that the server also answers `GET /health` with its status and version, and say that the healthcheck in `deploy/compose.yaml` needs a release that contains `/health` (an older image answers 404 and shows `unhealthy`); verify by reading the section next to the update steps

## 4. Verification

- [ ] 4.1 Run `env -C backend uv run pytest -q`, `env -C backend uv run pytest -m e2e` (after `npm run build` in `frontend/`), and in `frontend/` `npm run lint`, `npm test`, `npm run build`; all pass
- [ ] 4.2 Build the image with a fake version, start it with an empty data directory, and verify `curl` on `/health` answers 503 with that version and `docker inspect` reports the container `unhealthy`; then with the demo persona fixture mounted, `/health` answers 200 `ok` and the container becomes `healthy`
- [ ] 4.3 Open the built app in Chromium: with the demo persona the footer shows the version; with a data repository that does not load it still shows the version and no status (say what the browser test cannot show: a real release tag)
