# Proposal

## Why

The page is the only place to see which release the server runs, and there is no way to tell which backend a page talks to or whether an open tab predates an update (#67). The user is often away from a computer and has no terminal on the server, so a wrong or stale version goes unnoticed.

## What Changes

- The release image carries the release tag as its version; a build outside a release (local, CI) reports `dev`.
- The backend answers `GET /version` with its version.
- The app shell gets a footer that shows the frontend version, the backend version and the origin the page's requests go to.
- The page fetches the backend version on load and when the tab becomes visible again. When it differs from the version the frontend was built with, a banner says so and offers a reload button.
- The release workflow passes the tag into the image build; the smoke check verifies the version in the image.
- The README Deployment section says where to see the version.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `web-ui`: adds the version footer and the stale-page banner.
- `deployment`: adds that a release image reports its release tag as version, and that other builds report `dev`.

## Impact

- Backend: `backend/jobadvaisor/api/app.py` (new route), `backend/tests/test_api.py`, e2e in `backend/tests/e2e`.
- Frontend: `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/test-api.ts`, `frontend/src/App.test.tsx`, `frontend/vite.config.ts` (`/version` in `API_ROUTES`).
- Build and release: `Dockerfile`, `.github/workflows/release.yml`, `deploy/smoke.sh`, README.
- No new dependency, no data format change, no change to existing API routes.

## Non-goals

- No automatic reload: the app keeps its views mounted so a chat, an intake result or a running pass survives, and a forced reload would drop them.
- No change to the versions in `backend/pyproject.toml` and `frontend/package.json`; they stay placeholders and do not follow releases.
- No settings page and no other global place for the display.
- No host names or infrastructure details beyond the origin the browser already uses (the repository is public).
- No LLM-backed behavior, so no eval.
