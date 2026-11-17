# Tasks

## 1. Score fixture

- [ ] 1.1 Test first: add `backend/tests/test_readme_scores.py` (default `pytest`, a regression test for fixture data, not an eval). It checks that every file in `fixtures/readme-scores/` validates as a `Score`. It checks that the file names are exactly the demo persona's unrated postings a pass would score, using the pool's own ranking code on the demo persona and naming missing and extra IDs in the failure. It checks that every `example_id` is a rated demo posting. Verify: the test fails, because the directory does not exist yet.
- [ ] 1.2 Write the 11 score files in `fixtures/readme-scores/`, as `design.md` describes. Each has a score that fits the persona, one or two German sentences of reasoning on demo data only, three rated postings of a similar role as `example_ids`, and a fixed `scored_at`. Verify: the test from 1.1 passes, and a read-through finds no real company, host or person.

## 2. Script

- [ ] 2.1 Write `scripts/readme_images.py`, with a module docstring that names the command and what it writes, and a docstring on each function. It builds the frontend without `VITE_APP_VERSION` and sets `DATA_REPOSITORY` and `STATE_DIRECTORY` inside one temporary directory. It copies the demo persona and overlays the fixture, then runs `git init` and one commit with an inline author. It serves `create_app` with parts that raise, as `design.md` describes, on a free localhost port. It takes the two viewport images with the fixed browser settings, after waiting for the expected content and `document.fonts.ready`, and stops the server. Verify: the command ends with exit code 0, and `docs/images/pool.png` and `docs/images/posting.png` are rewritten.
- [ ] 2.2 Look at both images against the spec. The pool image is filtered to „Noch nicht bewertet“, shows the score range and sort controls, and selects the first row with its added date and score. The posting image shows the same posting with score, reasoning and the complete „Verglichen mit“ list. In both, the backup button is not disabled and no stale-page banner shows. Verify: each point is checked off in the task note, and anything that fails is fixed in the script or the fixture.
- [ ] 2.3 Check isolation. Before a run, record `git -C <data repository> status --short` and a listing with modification times of the state directory, and compare both after the run. Verify: both are unchanged, and no temporary directory of the script is left. The run ending with exit code 0 shows that no model was reached, because every model part raises.
- [ ] 2.4 Lint the script, which CI's ruff run in `backend/` does not cover: `uv run --directory backend ruff check ../scripts/readme_images.py`. Verify: no findings.

## 3. Repeatability and cost

- [ ] 3.1 Commit the images, run the command a second time, and check `git status --short docs/images/`. Verify: no change is listed.
- [ ] 3.2 Measure one run from a clean state (`rm -rf frontend/dist` first) with `/usr/bin/time -p`. Verify: the measured wall time is noted here, the cost is zero (no model call), and both values go into AGENTS.md in 4.2.

## 4. Documentation

- [ ] 4.1 Update `README.md`. Rewrite the pool caption so it says the scores are sample data, and add `docs/images/posting.png` with a caption in the same spirit where the README describes scoring. Verify: neither caption says the model produced the scores, and both images render in the GitHub preview of the branch.
- [ ] 4.2 Rewrite AGENTS.md "README screenshot". It names the command, its measured runtime, its cost (none, no model call) and both images. It keeps the rule that a visible UI change in an image's view retakes the images in the same PR, and drops "one scoring pass (paid, a few cents)". Verify: the section reads correctly against the spec requirement "The workflow rule names the command".
- [ ] 4.3 Update the „Current state“ section of AGENTS.md with this change and drop its oldest entry. Verify: the section holds the last two changes.

## 5. Verification

- [ ] 5.1 Run `npm --prefix frontend test`, `npm --prefix frontend run lint`, `npm --prefix frontend run build`, `env -C backend uv run pytest -q`, `env -C backend uv run ruff check .` and `env -C backend uv run pytest -m e2e`. Verify: all pass.
- [ ] 5.2 Run `openspec validate 79-readme-images --strict`. Verify: no errors.
