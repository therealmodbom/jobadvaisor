# Design

## Context

See proposal.md for motivation. Current state:

- The API has no `/api` prefix: routes are `/pool`, `/postings`, `/agent` and so on, and the built frontend is mounted at `/` last (`create_app`). The Vite dev server proxies a fixed list of routes (`API_ROUTES` in `frontend/vite.config.ts`), so a new route must be added there or the dev server answers it with `index.html`.
- The frontend calls the API with relative paths (`frontend/src/api.ts`), so the connected backend is `window.location.origin`; in dev that is the Vite origin.
- The `Dockerfile` has two stages (frontend build, runtime). Vite reads a variable at build time, the backend reads one at run time, so the version must reach both stages from one build argument.
- `release.yml` builds with `docker/build-push-action@v6` and passes no `build-args`; the tag is `github.ref_name`. `ci.yml` builds `jobadvaisor:ci` and runs `deploy/smoke.sh`.
- The app shell (`App.tsx`) has a header with navigation and no footer. All three main views stay mounted while hidden.
- `StaticFiles` sends validators (ETag, Last-Modified) and no `Cache-Control`. Hashed assets are safe; whether a normal reload fetches a new `index.html` is verified in the build (task 4.2).

## Goals / Non-Goals

**Goals:**
- One value, the release tag, reaches frontend and backend from one build argument, so the two cannot disagree within an image.
- A page that is older than the server says so without losing work.

**Non-Goals:**
- No version negotiation or compatibility ranges: any difference counts as stale.
- No LLM-backed behavior, so no eval is needed.
- No ADR: the choices below are small and cheap to reverse, and no alternative needs a recorded rejection.

## Decisions

1. **One build argument `APP_VERSION`, default `dev`, baked into two artifacts.** The Dockerfile declares `ARG APP_VERSION=dev` in both stages. The frontend stage exports it as `VITE_APP_VERSION` for `npm run build`, which bakes it into the built JavaScript; the runtime stage writes it with `RUN` into the file `/app/VERSION` and sets no `ENV`. `release.yml` passes `build-args: APP_VERSION=${{ github.ref_name }}`; `ci.yml` and local builds pass nothing and get `dev`. Alternative: read the tag from the image's OCI label or from `JOBADVAISOR_TAG` of the compose file. Rejected: a label is not readable by the app, and the compose tag may be `latest`, which names no release.

2. **The version is a file, not a setting.** The backend reads `VERSION` at the repository root (`REPOSITORY_ROOT`, which is `/app` in the image) and answers `dev` when the file does not exist, as in a checkout. A container's `environment`, `env_file` or `settings.env` can override an image `ENV` but cannot change a file in the image, so the backend cannot drift from the frontend it serves (the invariant of the deployment spec). The version is not in `Settings`, `.env.example` or `settings.env`. The frontend reads `import.meta.env.VITE_APP_VERSION` with the same default. Alternative: `ENV APP_VERSION` read at run time. Rejected: overridable by the deployment's settings, which is the case the spec rules out. Alternative: a generated `version.json`. Rejected: the smoke check's "no `*.json` under `/app`" rule would need an exception, and a plain file is enough.

3. **`GET /version` answers `{"version": "<tag or dev>"}`.** Registered before the static mount, with a docstring in the style of the other routes, and added to `API_ROUTES` in the Vite config. No auth, no other fields: nothing about the host or the data repository is exposed.

4. **Footer in the app shell, fed by one hook.** A `useBackendVersion` hook in `App.tsx`'s tree fetches `/version` on mount and on `visibilitychange` when `document.visibilityState === 'visible'`. It returns the last backend version fetched successfully, or `null` before the first success. A failed fetch changes nothing: `null` shows as "unbekannt" and is never a mismatch, and a version already known (and a banner it caused) stays as it is. The footer shows frontend version, backend version and `window.location.origin`. The footer is German like the rest of the UI. Alternative: poll on a timer. Rejected: a visibility check catches the case that matters (coming back to an old tab) at no cost while the tab is in the background.

5. **Mismatch banner, no auto-reload.** When the backend version is known and differs from the frontend's, a banner (`role="status"`) above the header says the page runs version A and the server version B, with a button "Neu laden" calling `window.location.reload()`. The banner is derived from the last successfully fetched backend version, so it goes when a fetch shows the versions equal again (a rollback) and a reload ends it by loading the new frontend; the views stay mounted, so a chat, an intake result or a running pass survives until the user chooses. Alternative: reload on mismatch. Rejected (owner decision): it drops views' state.

6. **Cache of `index.html`.** If a normal reload after an update still serves the old `index.html` from cache, the banner would loop. Task 4.2 verifies this against the built image with a real browser; if it does, `index.html` gets `Cache-Control: no-cache` (revalidate every time; the hashed assets keep their names and stay cacheable). Nothing is added before that is shown to be needed.

7. **Test doubles.** `stubApi` fails on an unrouted request, so every frontend test that renders `App` needs a `GET /version` route; the shared helper gets a default so existing tests are not touched one by one.

## Risks / Trade-offs

- [A release image built without the argument reports `dev`] → `release.yml` passes the tag; CI builds the image with a fake version and the smoke check fails unless both sides report it (task 3.2). A wrong `dev` would also show on the page right after the first update.
- [Old tab from before this change has no check at all] → unavoidable; the first reload brings it in.
- [Origin shown in the footer is visible on screenshots] → it is the host the user already typed; the README screenshot is deferred until the implementation is known, and then checked for the footer and for what it shows.
- [Footer lies beyond the 1280 by 800 README screenshot viewport] → checked when the screenshot is regenerated (task 5.3).
