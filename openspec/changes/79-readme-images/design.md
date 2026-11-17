# Design

## Context

- **Serving.** The backend serves `frontend/dist` at `/` (`backend/jobadvaisor/api/app.py`, `StaticFiles` mount). One uvicorn process and a fresh `npm --prefix frontend run build` are enough.
- **Injected parts.** `create_app(runs, intake, agent, frontend, …)` takes injected parts. The e2e walkthrough (`backend/tests/e2e/test_score_walkthrough.py`) uses this to serve the real app over a temporary data repository with fake models. Its `Harness` and `ScriptedModel` live under `backend/tests/`, so a script cannot import them.
- **Settings at startup.** `create_app` still builds `Settings()` for the state directory. That path holds the alert-mail record and the backup history.
- **Demo persona.** `fixtures/demo-persona` has 150 postings, 130 labels, no `scores/` and fixed `added_at` values. Its generator (`jobadvaisor.data.demo_persona`) replaces only `postings/`, `labels/` and `companies/`.
- **Spike (2026-11-17, scratchpad).** The app ran on a demo copy with 11 seeded score files, served by `Runs(build_graph(InMemorySaver()), <context that raises>)` and `Intake(root, <model that raises>, ContentGuard(None, {}))`. Without any key, the pool and the posting page rendered fully. Two runs wrote byte-identical viewport images. Full-page images differed, because the footer shows the server's random port. The web fonts come bundled in `dist`. On a copy that is no git repository, `GET /backup` answered 409 and the button showed disabled.

## Goals / Non-Goals

**Goals:**
- One file of script, no new dependency, no change to app code.
- Any accidental model use fails loudly instead of spending money.

**Non-Goals:**
- No shared server fixture with the e2e tests. The script stays independent of `backend/tests/`.
- No command-line options (output directory, image subset) until someone needs them.

## Decisions

- **Seeded score files instead of real score clicks.** `fixtures/readme-scores/<posting-id>.json` are plain score files (`schemas/score.schema.json`). The script copies them into the copy's `scores/`. Alternative: a few „Score berechnen“ clicks on the real judge. Rejected: a few cents per retake, a configured key, and reasoning that changes on every run, which breaks the repeatability requirement.
- **The fixture covers exactly the unrated, scorable postings (11).** These are the rows the pool image lists. Rated postings stay unscored, so the pass button in the image reads „Neue Anzeigen bewerten (130)“, where the old image read „(0)“. This is visible and honest: a pass would score those 130. Alternative: seed all 141 scorable postings to match the old image. Rejected: 130 extra files that no image shows, each needing a plausible reasoning.
- **Hand-written fixture content.** Each file holds a score that fits the persona's preferences, one or two German sentences of reasoning in the judge's style, three rated postings of a similar role as `example_ids`, and a fixed `scored_at`. The posting page then shows the „Verglichen mit“ list, the learning part of the app. Alternative: empty `example_ids`. Rejected: the page would hide the comparison, which is what sets the app apart.
- **A separate fixture directory.** The fixture lives next to `fixtures/demo-persona`, not inside it. Tests and evals that expect a demo persona without scores stay untouched, and the generator never overwrites the fixture. Alternative: `fixtures/demo-persona/scores/`. Rejected for both reasons.
- **Models that raise.** The script passes `create_app` a `Runs` whose context factory raises, an `Intake` whose model raises on any attribute access, `ContentGuard(None, {})` and an agent that raises. The images need no pass, no intake and no chat, so this costs nothing. Alternative: configured models that are simply never clicked. Rejected: it needs a key, and a stray request would cost money silently.
- **Isolation by environment.** Before the app is built, the script sets `DATA_REPOSITORY` and `STATE_DIRECTORY` to paths inside one `tempfile.TemporaryDirectory`. The `Settings()` inside `create_app` therefore never points at the user's data or state, and leaving the context deletes everything, also on an exception.
- **The copy becomes a git repository.** The script runs `git init` and one commit with an inline author (`git -c user.name=… -c user.email=…`), so it works without a global git identity. The backup button then shows its quiet state instead of the disabled one. Alternative: keep the disabled button. Rejected: it would look broken in the README, and the README's quick start also starts with `git init`.
- **Viewport-only capture with fixed browser settings.** The browser context uses viewport 1280 × 800, `device_scale_factor=1`, `color_scheme="light"`, `timezone_id="Europe/Berlin"`, `reduced_motion="reduce"` and the locale `de-DE`. Before each shot the script waits for the expected content and for `document.fonts.ready`. Alternative: full-page shots. Rejected: the footer carries the random port, and long pages make huge README images.
- **The script builds the frontend.** It runs `npm --prefix frontend run build` with `VITE_APP_VERSION` removed from the environment. A stale `dist` cannot leak into the images, and frontend and backend both report `dev`, so no stale-page banner appears. Alternative: fail with a hint when `dist` is missing, as the e2e tests do. Rejected: a present but stale `dist` would pass silently.
- **Which posting the page image shows.** The script reads `GET /pool` and takes the first row in rank order that is unrated and scored. That is the row selected at the top of the pool image. The two images stay consistent when the ranking changes.
- **Location and invocation.** `scripts/readme_images.py`, run as `uv run --directory backend python ../scripts/readme_images.py`, uses the backend venv's Playwright, uvicorn and `jobadvaisor` package. Ruff in CI runs only inside `backend/`, so the task list lints the script explicitly.
- **One regression test, no eval.** `backend/tests/test_readme_scores.py` runs in the default `pytest`. It checks that every fixture file validates as a `Score`, that the fixture's posting IDs are exactly the demo persona's unrated postings a pass would score (decided by the pool's own ranking code, not a copy of its rules), and that every `example_id` names a rated demo posting. It is a regression test for fixture data, not an eval. The change has no LLM-backed behavior, so it names no eval.

## Risks / Trade-offs

- [Byte-identical images hold only on one machine, because font rasterisation and Chromium builds differ] → the spec promises repeatability per machine. A retake from another machine may show a pixel diff with no UI change. The PR author judges the images visually.
- [The demo persona generator changes the set of unrated postings] → the regression test fails and names the missing or extra IDs, so the fixture is updated in the same PR.
- [A future UI change moves the score card below 800 px on the posting page] → the scenario "Comparison examples visible" fails on review of the image. The fix is a scroll to the card or a taller viewport, decided then.
- [The pool's first row changes when the ranking code changes] → intended. Both images follow it, and the retake shows it as a visible diff.
- [Playwright's Chromium is missing in a fresh checkout] → the setup task "backend: install browser (playwright)" installs it. The script fails with Playwright's own install hint otherwise.
