# AGENTS.md

Guidance for any AI coding agent working in this repository. This file is the single source of truth. `CLAUDE.md` only points here.

## What this repository is

JobAdvAIsor, a local-first AI job search assistant. Its core is a learning job match: the user rates suggested postings, and those ratings feed future scoring. Later changes add CV tailoring, cover letters, a Markdown and PDF review UI, and job sourcing.

The agreed scope, decisions and open assumptions are in [`docs/kickoff-brief.md`](docs/kickoff-brief.md). Read it before planning any change.

**This section and the ones below are self-contained on purpose.** Write everything here for a reader who has only this repository. Never add instructions that depend on an external repository, a machine-specific path, an environment variable outside `env.example`, or a skill that only exists on one machine.

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

`scripts/review-workspace.sh` writes `jobadvaisor.code-workspace` (gitignored) next to the repository root: this checkout and every worktree under `worktrees/` as folders, plus the pull-request inbox. Re-run it after adding or removing a worktree, or use the task `0 - Review Workspace`.

A pull request whose branch is already checked out in a worktree cannot be checked out from the pull-request view. Review it in its worktree folder instead. Cursor keeps one window per worktree.

## Current state

The history lives in OpenSpec, not here: `openspec/specs/` is the baseline (one folder per capability) and `openspec/changes/archive/` holds every finished change with its proposal, design and tasks. Open work is in the GitHub issues. Keep this section to a pointer plus the last two archived changes; when archiving a change, drop the oldest entry.

- `113-posting-delete` (#113): a posting can be deleted for good, with no trash; the data repository's git history is the way back (ADR 0015). `delete_posting(root, id)` (`data/writer.py`) removes the label, the score and the `extraction-labels.json` entry, then the posting file last, so a crash leaves a loadable repository. `write_gate` lives in `data/loader.py`; `load`, `read_scores` and `pool_state` read under it, and `GET /postings/{id}`, `PUT …/rating`, `PATCH` and `DELETE` each run from their 404 check to their answer in one gate section (`POST …/score` takes it only after the judge returned), so no reader sees half a delete. `DELETE /postings/{id}` answers 204, 404, or 409 `scoring in progress` / `check in progress`; it holds `checks.exclusive()`, then `runs.exclusive("delete:<id>")`, then the gate, and nothing takes the gate and then waits for the other two. `AvailabilityChecks.start` claims its slot before it loads the batch. A pass paused over its unscreened question gives a posting deleted meanwhile `{"status": "deleted"}` and leaves the total. Other scores keep a deleted ID in `example_ids`. `GET /postings/{id}` answers `delete_blocked` (`"scoring"`, `"check"` or `null`, read before the gate). The frontend has `DeleteButton` and `DeleteDialog` (Radix `AlertDialog`) in `components/posting.tsx`: in each pool row after `StatusControl` (disabled while the view's pass is busy or a check runs) and in the posting page's head row, where all four controls are 44 px high and the page re-reads `delete_blocked` every `POLL_MS` while blocked. The pool's key handler skips `[role="alertdialog"]`. The e2e walkthrough `test_delete_walkthrough.py` deletes from both places over a demo copy.
- `58-mailbox-alert-mails` (#58): alert mails can be read from an IMAP mailbox. `mailbox.json` (`Mailbox`: host, port, user, `folders` as `{all}` or `{names}`, `max_mails` 1 to 1000 (200 when absent), `since`, `last_check_at`, and the `handled` and `waiting` `MailRecord`s, each by folder with `validity` and UIDs and by `ids`) is read with `read_mailbox` and written only through the gated `update_mailbox`, `update_mailbox_account` and `mark_mails`; an ID is the first 16 hex characters of SHA-256 over the trimmed lower-case Message-ID (`message_id_hash`), and no sender, subject or text is stored. A change of host or user clears `since`, `last_check_at` and both records. The password exists only as Fernet ciphertext in `<state_path>/mailbox-password` (`mailbox_secret.store`, `read`, `forget`, mode 600); its key `MAILBOX_KEY` is in `SECRETS`, a malformed key counts as none (`key_configured`), and the file is forgotten when host, port or user change without a new password (ADR 0016). `intake/mailbox.py` is the access layer behind `connect(account, password)` (imapclient over TLS with `ssl.create_default_context()`, 30 s, the `imapclient` logger at WARNING; ADR 0017): `imap_errors` maps every IMAP, TLS or socket error to one `Reason` (`unreachable`, `certificate`, `login`, `folder`, `protocol`, plus the three that fail before a login: `no key`, `no password`, `password unreadable`), never to server text; `list_folders` drops `\Noselect` and `\NonExistent` folders and marks `\Trash`, `\Junk`, `\Sent`, `\Drafts`, `\All`, `\Flagged` and `\Important` as system folders; `searched_folders` applies the choice; `find_candidates` selects read-only, searches `SINCE`, fetches headers with `BODY.PEEK` in batches of `HEADER_BATCH`, skips marked mails by UID under the validity or by ID hash, counts a mail in two folders once and keeps the `max_mails` oldest by INTERNALDATE (`remaining` counts the rest); `parse_mail` and `mail_parts` give the finder `(html, text)` (blank HTML is `None`, an unknown charset decodes as UTF-8 with replacement characters, attachments are never read). `intake/mailbox_checks.py` holds `MailboxChecks` (one worker, one check at a time, state in memory, its lock before `write_gate`, IMAP calls and the finder outside the lock): each mail goes through `alert_mail.preview` as a paste does; `FinderError` puts it into `failed` unmarked, `screening off` into `not_screened` and `waiting`, a held mail into `held` marked, an empty one is marked unreported, one with entries joins `mails`; more than `MAX_MAIL` characters in both parts makes it `oversized` and unmarked, its parts kept in memory until `read_oversized` (a `reading` flag; `finish`, a second read, `start` and `account_change` raise `ReadInProgressError`); `cancel` ends after the current mail (`cancelled`, `CheckNotRunningError` for a check not running); a lost connection ends `done` with `interrupted`; `finish` marks exactly the offered mails handled (never `failed` or `not_screened`), starts the entries as an `AlertRuns` run (busy: nothing marked), and a second finish is refused; the last `done` check whose list is not finished stays pending, and `GET /mailbox` names it as `check_id`. The routes are `GET` and `PUT /mailbox` (the password is never answered: `password` is `missing`, `stored` or `unreadable`), `POST /mailbox/folders` and `POST /mailbox/checks` with `GET`, `/cancel`, `/mails/{key}/read` and `/finish` under `/mailbox/checks/{id}`; `create_app(connect=…)` takes the IMAP factory, and `tests/fake_imap.py` is the fake client that fails a select without `readonly=True` and a fetch item without `PEEK`. The frontend: the gear is a link to `#/einstellungen[/<section>]` (`views/SettingsPage.tsx`: `scoren` holds the former popover's `SettingsForm`, `postfach` is `components/mailbox-settings.tsx`), the source „Postfach“ is `views/MailboxView.tsx` with `lib/mailbox-check.ts` (the check ID in browser storage) and `components/mailbox-pick.tsx` (the pick list grouped by mail, tri-state mail heads, an oversized mail read on ticking), and the run part of `AlertMailView` became `AlertRunView` (`components/alert-run.tsx`). Tests: the `.eml` fixtures `linkedin-mime`, `ba-mime` and `career-site-mime` are a regression test through `mail_parts` and `preview` with a model and guard that fail when called, `unknown-preheader`, `unknown-quoted-printable` and `unknown-multipart` are eval cases (`load_cases` reads `.eml` through `mail_parts`), and #154 anchored the bare-domain alternative of `MASKED_URL` at a token start (`(?<![\w.-])`), so masking takes linear time. The e2e walkthrough `test_mailbox_walkthrough.py` serves the real app with `FakeImap` injected through `create_app(connect=…)`, sets the account up on the settings page, checks, collapses one mail, clears another, adds the rest and checks again to see nothing new, and asserts that the password is in no file and no mail is fetched twice.

The README covers setup, the demo persona, the pool workflow, the deployment and the evals. `docs/company-facts.md` and `docs/extractor-benchmark.md` hold the longer guides.

## README screenshot

`docs/images/pool.png` shows the "Anzeigen" pool on the demo persona, filtered to "Noch nicht bewertet", and `docs/images/posting.png` shows the page of the posting listed first. A change that visibly alters either view retakes both images in the same PR. From the repository root:

```bash
uv run --directory backend python ../scripts/readme_images.py
```

Install first: `uv sync --directory backend`, `uv run --directory backend playwright install chromium` and `npm --prefix frontend ci` (the VS Code task "1 - Setup Worktree" does all three). The script builds the frontend itself and takes about 9 seconds from a clean `frontend/dist`. It costs nothing: no model call, no API key. The scores come from `fixtures/readme-scores/`, laid over a temporary copy of the demo persona. A second run without a UI change leaves `docs/images/` unchanged on the same machine. Another machine may render fonts slightly differently.

## Spec-driven workflow (OpenSpec)

All new work goes through `openspec/changes/<change-id>/` (`proposal.md`, `design.md`, spec deltas under `specs/`, `tasks.md`). `openspec/specs/` (`openspec list --specs`) is the baseline every change modifies.

- **Explore first, only when the kickoff needs it:** `openspec-propose` has its own ambiguity gate and grounding (reads `openspec/config.yaml`, inspects code and specs). Run `openspec-explore` first only when the request cannot answer propose's scope, behavior and "done" questions, and no existing artifact (a brief, a scoped issue) can serve as input.
- **Planning:** the native `openspec-propose` skill (`/opsx:propose` in Claude Code, `/opsx-propose` in Cursor and OpenCode, `$openspec-propose` in Codex). Do not plan new changes with Superpowers' `brainstorming`/`writing-plans`.
- **Execution:** Superpowers' `executing-plans`/`subagent-driven-development`, reading the change's `tasks.md`. TDD per task, a worktree per branch, review checkpoints. Do not use `openspec-apply-change`, since it enforces none of these. Superpowers is a public plugin, not part of this repository: install it from [obra/superpowers](https://github.com/obra/superpowers) per its README. Without it, work through `tasks.md` by hand under the same rules: one task at a time, a failing test before the code, a worktree per branch, and a review before the next task.
- **Spec review:** the change folder stays the review artefact. After every edit to a delta spec, run `openspec-sync-specs` (`/opsx:sync`) so the baseline spec in the PR already shows the target diff. Never paste a hand-made diff into a PR description or comment.
- **Archive:** `openspec archive <change-id> --yes` is the last action of a completed change, run on the branch of the change's last PR before it merges (tick the open tasks first), so code, baseline specs and archive land together. Skipping it leaves `openspec/specs/` stale for the next change. When several open changes touch one capability, archive them in the order they merge. The archive moves the change one directory deeper, so every relative link from its files to a destination outside the change (usually the ADR link in `design.md`) needs one more `../`; links between the change's own files keep their paths. Check that each link resolves before pushing the archive commit.
- **Milestone gate:** after each archived change, the next change starts only on an explicit decision.

## Architecture decisions

A significant, non-obvious decision (a real alternative was rejected) gets an ADR in [`docs/decisions/`](docs/decisions/README.md), in the same change that makes it.

**ADR or OpenSpec `design.md`:** `openspec/specs/` hold *what* the system does, a change's `design.md` holds *how* that change is built, and an ADR holds *why* a significant decision was made and what was rejected. The same decision never lives in both places. `design.md` links the ADR with one sentence and does not restate the rationale.

## Evaluation

Every LLM-backed behavior ships with an automated quality eval in its own change. A structural or mocked test does not count. The mechanism per rule (prompt, retrieval, graph node, guardrail, decision model) is chosen case by case and backed by an eval result.

**Evals and regression tests are two things.** An eval or benchmark measures an LLM: how well a model or a prompt does a task, so that the figures can be compared between models, prompt versions and over time. It lives in `evals/`, runs on request or at a change's wrap-up, and its paid runs name their cost first. A regression test pins the behavior of deterministic code (rules, parsers, graph wiring) to a fixture, runs in the default `pytest` and needs no model. It may report through DeepEval, but it is never an eval and never sits in `evals/`: a figure that is always 1.0 for the same code measures nothing. A fixture belongs to one of the two, and a test names which.

## Issue tracking

Open points and deferred work are GitHub Issues in this repository. Labels: `bug`, `enhancement`, `documentation`, `housekeeping`, `priority:high|medium|low`.

## .env handling

Never commit a filled `.env`. `env.example` documents required keys without values.

Secrets (`SECRETS` in `backend/jobadvaisor/settings.py`) come from a gitignored `.env` in the repository root or from the environment; agents never read or print `.env`. On macOS they can live in the Keychain instead, service `jobadvaisor`, account = setting name in lower case with dashes (`llm-api-key`). The app reads them itself; do not export them from a shell profile. Agents never print a Keychain value: check presence with `security find-generic-password -s jobadvaisor -a <account>` without `-w`. `local.env` (gitignored, repository root) holds every non-secret setting (models, URLs, paths, thresholds, `LANGFUSE_PUBLIC_KEY`), and agents may edit it; never put a secret there. Precedence: Keychain, environment, `.env`, `local.env`. Tests never read the Keychain (`tests/conftest.py`). In a worktree, symlink `local.env` (and `.env`, if one exists) from the main checkout.

## Language

All code, docs, specs and issues are in English.
