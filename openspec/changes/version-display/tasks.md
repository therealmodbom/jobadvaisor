# Tasks

## 1. Backend

- [x] 1.1 Test first, then add `GET /version` to `create_app`, answering `{"version"}` from the file `VERSION` at the repository root (`dev` when it does not exist), with a docstring; verify `env -C backend uv run pytest -q tests/test_api.py` covers the missing file and a file with a value, and that an environment variable of any name does not change the answer
- [x] 1.2 Add `/version` to `API_ROUTES` in `frontend/vite.config.ts`; verify with the dev server that `curl http://127.0.0.1:5710/version` returns the backend's JSON, not `index.html`

## 2. Frontend

- [x] 2.1 Give `stubApi` users a default `GET /version` answer (`dev`) in `frontend/src/test-api.ts`; verify `npm test` still passes for the existing tests
- [x] 2.2 Test first, then add the footer with a `useBackendVersion` hook (fetch on mount and on `visibilitychange` to visible): frontend version, backend version, `window.location.origin`, "unbekannt" while no fetch has succeeded, last successful version kept after a failed refetch; verify tests for released page, `dev`, unreachable on load, failed refetch after a success, and refetch on visibility
- [x] 2.3 Test first, then add the stale-page banner (`role="status"`, button "Neu laden" calling `window.location.reload()`) derived from the last successfully fetched backend version (shown while it differs, removed when it equals the frontend's); verify tests for mismatch, equal versions, unreachable on load (no banner), a failed refetch after a mismatch (banner stays), a refetch that returns the frontend's version after a mismatch (banner removed) and that mounted views keep their input
- [x] 2.4 Verify the existing automated accessibility check covers footer and banner in both themes and reports no violations; extend it with a mismatch state if it does not reach the banner

## 3. Build and release

- [ ] 3.1 Declare `ARG APP_VERSION=dev` in both Dockerfile stages (`VITE_APP_VERSION` for the build, the file `/app/VERSION` written with `RUN` for the runtime, no `ENV`) and pass `build-args: APP_VERSION=${{ github.ref_name }}` in `release.yml`; verify `docker build --build-arg APP_VERSION=v0.0.0-test` yields an image whose `/version` answers `v0.0.0-test`, and that running it with `-e APP_VERSION=other` still answers `v0.0.0-test`
- [ ] 3.2 Extend `deploy/smoke.sh` to take the expected version, check the backend's answer and the built frontend's `index.html`/assets for it, and have `ci.yml` build with a fake version and pass it; verify the check fails on an image built without the argument and passes on one built with it

## 4. Verification

- [ ] 4.1 Run `env -C backend uv run pytest -q`, `env -C backend uv run pytest -m e2e` (after `npm run build`), and in `frontend/` `npm run lint`, `npm test`, `npm run build`; all pass
- [ ] 4.2 Click through the built image in Chrome: footer on all three views and on a posting page, banner after replacing the server with an image of another version in a tab left open, reload button ends the banner, and a normal reload fetches the new `index.html`. If it does not, add `Cache-Control: no-cache` for `index.html` with a test; report what the browser check cannot show

## 5. Documentation

- [ ] 5.1 Add to the README Deployment section where the version shows (footer) and that a banner asks for a reload after an update; verify the text against the running page
- [ ] 5.2 Note in the README's build/dev text that a local build reports `dev` and the release workflow sets the version; verify the wording matches the Dockerfile argument name
- [ ] 5.3 Check whether the footer lies inside the README screenshot's 1280 by 800 viewport and whether it shows anything beyond the origin used; regenerate the screenshot only if it changes what the screenshot shows, with the demo persona
