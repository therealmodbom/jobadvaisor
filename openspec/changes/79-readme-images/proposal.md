# Proposal

## Why

AGENTS.md ("README screenshot") asks every visible UI change to retake `docs/images/pool.png` after a fresh demo copy and one scoring pass. Since #74 (Score rated postings in a pass) that pass scores all 141 scorable demo postings, about 32 minutes at an unmeasured cost, for a picture that shows a few scored rows. So retakes get skipped: #46 (Show the date a posting was added) and #105 (Pool: filter by score range and sort) both left `pool.png` stale. #79 (Retake the README screenshots with a cheap script) asks for a cheap, repeatable retake.

## What Changes

- A new command, `uv run --directory backend python ../scripts/readme_images.py`, regenerates every README image. It builds the frontend, copies `fixtures/demo-persona` into a temporary directory, overlays committed score files, serves the app on the copy with no model attached, takes the screenshots with Playwright and deletes the copy.
- No model is called and no API key is needed, so a retake costs nothing. The scores in the images are seeded, not computed by the judge.
- A new fixture, `fixtures/readme-scores/`, holds one score file for every posting that the "Noch nicht bewertet" filter lists on the demo persona. Each file has a fixed score, a short German reasoning and three rated postings as comparison examples.
- Two images: `docs/images/pool.png` (refreshed: added-date line, score range and sort controls) and a new `docs/images/posting.png` (a posting's page with score, reasoning and comparison examples).
- Two consecutive runs on the same machine write byte-identical images.
- The README gets the second image. Both captions say the scores are sample data, not model output.
- AGENTS.md "README screenshot" points at the command, states its measured runtime and its cost (none), and drops "one scoring pass (paid, a few cents)". It keeps the rule that a visible UI change retakes the images in the same PR.
- A default-pytest regression test pins the fixture to the demo persona.

## Capabilities

### New Capabilities

- `readme-images`: the command that regenerates the README images, what each image shows, where its scores come from, its cost and its repeatability.

### Modified Capabilities

None.

## Impact

- New: `scripts/readme_images.py`, `fixtures/readme-scores/*.json` (11 files), one test in `backend/tests/`, `docs/images/posting.png`.
- Changed: `docs/images/pool.png`, `README.md` (captions, second image), `AGENTS.md` ("README screenshot").
- Uses Playwright and uvicorn from the backend venv, plus npm for the frontend build. No new dependency.
- The issue's precondition "a configured model key" falls away: the command runs without one.
- No change to app code, API or data format.

## Non-goals

- Images beyond the pool and the posting page, such as the chat, the add-posting page or the disabled score button. Each needs a reason in the README first.
- Running the command in CI, or a CI check that the committed images are current. Font rendering differs between macOS and Linux, so such a check would flag noise.
- Real model output in the images.
- Byte-identical images across machines. The guarantee covers one machine.
- Changes to `fixtures/demo-persona` or its generator.
- No LLM-backed behavior, so no eval.
