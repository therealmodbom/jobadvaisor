# AGENTS.md

Guidance for any AI coding agent working in this repository. This file is the single source of truth. `CLAUDE.md` only points here.

## What this repository is

JobAdvAIsor, a local-first AI job search assistant. Its core is a learning job match: the user rates suggested postings, and those ratings feed future scoring. Later changes add CV tailoring, cover letters, a Markdown and PDF review UI, and job sourcing.

The agreed scope, decisions and open assumptions are in [`docs/kickoff-brief.md`](docs/kickoff-brief.md). Read it before planning any change.

**This section and the ones below are self-contained on purpose.** Write everything here for a reader who has only this repository. Never add instructions that depend on an external repository, a machine-specific path, an environment variable outside `.env.example`, or a skill that only exists on one machine.

## Privacy

- No personal data in this repository, ever. That covers CVs, postings someone applied to, ratings, correspondence, and API keys.
- That includes indirect traces: example values, feature names, rule details or docs wording derived from one real user's profile or constraints. Describe mechanisms generically. Concrete rules live in the data repository.
- User data lives in a separate data repository (a plain git repository with the documented JSON-Schema format). The app reads its location from configuration.
- Tests, CI and demos use the fictional demo persona fixture only.

## Git workflow

Feature branch, then PR, then merge to `main`. Never commit to `main`.

```bash
git switch -c feat/my-change     # or fix/…, docs/…
# commit continuously
gh pr create
```

⚠️ **Enable the pre-commit hook once per clone:**

```bash
git config core.hooksPath .githooks
```

That points git at [`.githooks/pre-commit`](.githooks/pre-commit), which blocks commits on `main`. Verify without risking a real commit:

```bash
git config --get core.hooksPath          # expect: .githooks
test -x .githooks/pre-commit && echo executable
.githooks/pre-commit                     # on main: expect BLOCKED, exit 1
```

`core.hooksPath` replaces `.git/hooks`. Set it only once `.githooks/` exists on the checked-out branch.

Worktrees live under `worktrees/` (gitignored), one per branch: `git worktree add worktrees/<kebab-name> -b <branch> origin/main`.

### Review workspace

Agents work in `worktrees/`, one per branch, and an editor window only ever shows one working tree. The branch switcher cannot cross that boundary either, since git refuses to check out a branch that is already checked out in another worktree, so reviewing several agents' pull requests otherwise means one window per worktree.

`scripts/review-workspace.sh` generates `jobadvaisor.code-workspace` next to the repository root: the main checkout as the first folder and every worktree under `worktrees/` as a further one, each path relative to the workspace file, with `prunable` worktrees skipped. It works from any folder of the clone, a worktree included, because it derives the main checkout from the common git dir. Re-run it after worktrees were added or removed, then open the file in VS Code; the script is also the first task in `.vscode/tasks.json` (`0 - Review Workspace`), so a refresh is one command. The pull-request view starts on an inbox rather than a URL: the repository's open pull requests, your own, and the ones where your review is requested.

The generated file is gitignored. Checking out a pull request from the pull-request view fails while that branch is already checked out in a worktree; review it in the open worktree folder instead. Cursor keeps one window per worktree, and the agent flow there is unchanged ([#107](https://github.com/therealmodbom/jobadvaisor/issues/107)).

## Current state

The history lives in OpenSpec, not here: `openspec/specs/` is the baseline (one folder per capability) and `openspec/changes/archive/` holds every finished change with its proposal, design and tasks. Open work is in the GitHub issues. Keep this section to a pointer plus the last two archived changes; when archiving a change, drop the oldest entry.

- `show-added-date`: every pool row and the posting page show „Hinzugefügt 12.11.2026, 14:05“ above the title, to the minute, in the browser's time zone (`addedLabel` in `lib/german.ts`, a `<p><time dateTime>` in `PoolView.tsx` and `PostingPage.tsx`), 11 px in the `subtle-foreground` token. Vitest pins `TZ` to Europe/Berlin in `vite.config.ts`, the e2e page uses `timezone_id="Europe/Berlin"`. Display only: no sorting, filter or API change.
- `backup-data-repository` (slice 1 of #63): the app commits and pushes the data repository on a button press ([ADR 0010](docs/decisions/0010-the-app-commits-and-pushes-the-data-repository.md)). Every public writer function holds the reentrant `write_gate` (`data/writer.py`), so a commit never holds half a write. `data/backup.py` runs the `git` command (status, commit message by kind, commit and push of `main` to its configured upstream, never forced; the last success and failure in `backup.json` in the state directory). `GET /backup` and `POST /backup` (202, runs in a thread with step, files and push percent; 409 `backup running`, `backup refused`, `backup unavailable`). The header's `BackupControl` and `BackupStrip` (`components/backup.tsx`, `lib/backup.ts`) follow the Design artifact; the image carries `git` and `openssh-client`, and Compose mounts a keys directory read-only with `GIT_SSH_COMMAND`. Modes, the settings page, fetching the remote and the conflict banner are the sub-issues #98 to #100.

The README covers setup, the demo persona, the pool workflow, the deployment and the evals. `docs/company-facts.md` and `docs/extractor-benchmark.md` hold the longer guides.

## README screenshot

`docs/images/pool.png` shows the "Anzeigen" pool on the demo persona after one scoring pass, filtered to "Noch nicht bewertet". A change that visibly alters that view retakes the screenshot in the same PR: a fresh copy of `fixtures/demo-persona`, one scoring pass (paid, a few cents), a 1280 by 800 viewport, light mode.

## Spec-driven workflow (OpenSpec)

All new work goes through `openspec/changes/<change-id>/` (`proposal.md`, `design.md`, spec deltas under `specs/`, `tasks.md`). `openspec/specs/` (`openspec list --specs`) is the baseline every change modifies.

- **Explore first, only when the kickoff needs it:** `openspec-propose` has its own ambiguity gate and grounding (reads `openspec/config.yaml`, inspects code and specs). Run `openspec-explore` first only when the request cannot answer propose's scope, behavior and "done" questions, and no existing artifact (a brief, a scoped issue) can serve as input.
- **Planning:** the native `openspec-propose` skill (`/opsx:propose` in Claude Code, `/opsx-propose` in Cursor, `$openspec-propose` in Codex). Do not plan new changes with Superpowers' `brainstorming`/`writing-plans`.
- **Execution:** Superpowers' `executing-plans`/`subagent-driven-development`, reading the change's `tasks.md`. TDD per task, a worktree per branch, review checkpoints. Do not use `openspec-apply-change`, since it enforces none of these. Superpowers is a public plugin, not part of this repository: install it from [obra/superpowers](https://github.com/obra/superpowers) per its README. Without it, work through `tasks.md` by hand under the same rules: one task at a time, a failing test before the code, a worktree per branch, and a review before the next task.
- **Spec review:** the change folder stays the review artefact. After every edit to a delta spec, run `openspec-sync-specs` (`/opsx:sync`) so the baseline spec in the PR already shows the target diff. Never paste a hand-made diff into a PR description or comment.
- **Archive:** `openspec archive <change-id> --yes` is the last action of a completed change, run on the branch of the change's last PR before it merges (tick the open tasks first), so code, baseline specs and archive land together. Skipping it leaves `openspec/specs/` stale for the next change. When several open changes touch one capability, archive them in the order they merge. The archive moves the change one directory deeper, so every relative link from its files to a destination outside the change (usually the ADR link in `design.md`) needs one more `../`; links between the change's own files keep their paths. Check that each link resolves before pushing the archive commit.
- **Milestone gate:** after each archived change, the next change starts only on an explicit decision.

## Architecture decisions

A significant, non-obvious decision (a real alternative was rejected) gets an ADR in [`docs/decisions/`](docs/decisions/README.md), in the same change that makes it.

**ADR or OpenSpec `design.md`:** `openspec/specs/` hold *what* the system does, a change's `design.md` holds *how* that change is built, and an ADR holds *why* a significant decision was made and what was rejected. The same decision never lives in both places. `design.md` links the ADR with one sentence and does not restate the rationale.

## Evaluation

Every LLM-backed behavior ships with an automated quality eval in its own change. A structural or mocked test does not count. The mechanism per rule (prompt, retrieval, graph node, guardrail, decision model) is chosen case by case and backed by an eval result.

## Issue tracking

Open points and deferred work are GitHub Issues in this repository. Labels: `bug`, `enhancement`, `documentation`, `housekeeping`, `priority:high|medium|low`.

## .env handling

Never commit a filled `.env`. `.env.example` documents required keys without values.

Secrets (`SECRETS` in `backend/jobadvaisor/settings.py`) come from a gitignored `.env` in the repository root or from the environment; agents never read or print `.env`. On macOS they can live in the Keychain instead, service `jobadvaisor`, account = setting name in lower case with dashes (`llm-api-key`). The app reads them itself; do not export them from a shell profile. Agents never print a Keychain value: check presence with `security find-generic-password -s jobadvaisor -a <account>` without `-w`. `local.env` (gitignored, repository root) holds every non-secret setting (models, URLs, paths, thresholds, `LANGFUSE_PUBLIC_KEY`), and agents may edit it; never put a secret there. Precedence: Keychain, environment, `.env`, `local.env`. Tests never read the Keychain (`tests/conftest.py`). In a worktree, symlink `local.env` (and `.env`, if one exists) from the main checkout.

## Language

All code, docs, specs and issues are in English.
