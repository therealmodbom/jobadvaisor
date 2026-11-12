# Tasks

TDD per task: a failing test first, then the code. Backend tests use real git on a copy of `fixtures/demo-persona` with a local bare repository as the remote, never mocked git. Commands from `backend/`: `uv run ruff check`, `uv run pytest`. From `frontend/`: `npm run lint`, `npm test`, `npm run build`.

## 1. Write gate

- [x] 1.1 Add a reentrant `write_gate` to `data/writer.py` that every public write function holds, and replace `_pool_lock` and `_update_lock` with it. Verify with a test where a thread holding the gate makes every public write function (`write_label`, `write_score`, `write_company`, `write_pool`, `write_guard`, `create_posting`, `update_posting`, `append_pass`, `update_pool_settings`, `merge_extraction_labels`, `write_login_wall_hosts`, `write_import_mapping`) wait until it is released. The existing writer tests must still pass.
- [x] 1.2 Rewrite the `writer.py` module docstring ("the user commits") to name the gate and the backup. Verify with `uv run ruff check`.

## 2. Backup module (`data/backup.py`)

- [x] 2.1 Status: own-repository check, uncommitted count (with changes made outside the app, temporary files excluded), unpushed count, branch (`null` when detached), upstream name, in-progress operation. Verify with tests for:
  - a clean repository;
  - a hand-edited file;
  - an untracked new posting;
  - a leftover `.pool.json.tmp`, which is not pending;
  - a commit ahead of the upstream;
  - no remote;
  - another branch;
  - a `MERGE_HEAD` present;
  - a rebase stopped on a conflict (detached HEAD);
  - a plain directory and a subdirectory of another repository, both unavailable.
- [x] 2.2 Commit message by kind (ratings, scores, postings, company records, other files; singular for 1). Verify with a test on staged paths of mixed kinds, including the spec scenario of 3 ratings and 1 posting.
- [x] 2.3 Backup: refuse off `main` or during an operation, then stage under the gate with temporary files excluded, commit with the repository's identity or the fallback, and push to the upstream with a timeout and without force. Verify with tests for:
  - pending changes are committed and pushed;
  - nothing pending, but an unpushed commit, is pushed;
  - no upstream commits only and adds no remote;
  - another branch changes nothing;
  - a merge stopped on a conflict changes nothing and names the operation;
  - a subdirectory of another repository commits nothing in that repository;
  - a leftover `.pool.json.tmp` is not committed, also when it was staged by hand before the backup, and the status is clean afterwards;
  - a rejected commit (a failing `pre-commit` hook in the test repository) keeps every change pending and reports `commit failed`;
  - the fallback identity is used without a repository identity.
- [ ] 2.4 Failures: an unreachable remote (a bare-repository path that does not exist) and a rejected push (a second clone pushed first) both keep the commit, report git's reason and leave both histories unchanged, and a later backup pushes. Verify with tests. Add a test that a push exceeding the timeout counts as failed, using a fake `GIT_SSH_COMMAND` that sleeps.
- [ ] 2.5 `backup.json` in the data repository's `state_path`: last success, last failure with step and reason, the failure cleared on success, and a missing or unreadable file read as "none". Verify with tests.
- [ ] 2.6 Background run: refusals are checked synchronously, then the backup runs in a thread. A second backup while one runs is refused, not queued. Progress reports `{step, files, percent}`, with the percent parsed from `--progress` stderr split on `\r`, and `last_result` records the outcome. Verify with tests for:
  - a test holding the first backup in its push, which sees the second refused and the progress step `pushing` with the file count;
  - the parser on captured git output: `2% (1/42)` gives 2, and a push without progress lines gives `null`.
- [ ] 2.7 Concurrency (spec: "Writes and backups never interleave"): threads write labels and scores in a loop while backups run repeatedly. Every committed blob loads as a schema-valid file, and every written rating is in a commit or pending at the end. A rating during a slow push is stored without waiting. Verify with these tests.

## 3. API

- [ ] 3.1 `GET /backup` and `POST /backup` in `api/app.py` with the bodies and errors from design.md, and `create_app(backup=…)`. Verify with `test_api.py` tests for:
  - `202` with `running` true;
  - each `last_result.result` value once the run finished;
  - `409 backup running`;
  - `409 backup refused`;
  - `409 backup unavailable` for a data directory that is not a git repository;
  - a push failure and a commit failure, each in `last_failure` with its step and git's reason.

## 4. Design artifact session (spec phase, gate for the implementation)

- [x] 4.1 (approved by the owner 2026-11-12) With the owner, design in the Design artifact [Backup-Button und Einstellungen](https://claude.ai/artifact/36PaFpC4LN6NpeKsFYrBUL) on the JobAdvAIsor design system, before task 1.1 starts:
  - the backup button in the header, quiet and highlighted;
  - the running state with its progress (step, files, push percent);
  - the success, committed-without-remote and failure states;
  - the unavailable state (disabled, with an info icon);
  - the last-backup line;
  - slice 2's gear icon for the settings page, so the header is laid out once.

  Verify by the owner approving the artifact. Implementation (group 1 onward) starts only after this.

## 5. Frontend

- [ ] 5.1 API types and `useBackupStatus` (fetch on mount, when the tab becomes visible, every second while a backup runs, otherwise every 15 seconds while visible; a failed fetch keeps the last status). Verify with Vitest tests using fake timers and visibility changes.
- [ ] 5.2 `BackupControl` in the app shell as designed in 4.1: highlight, disabled while running with the progress (step, files, percent when known), the result line per outcome, the failure reason, the last successful backup or "noch keine Sicherung", and the unavailable state (disabled, with a focusable info icon giving the reason). Verify with component tests for each state, and for a `last_failure` that leaves the button enabled.
- [ ] 5.3 e2e (`uv run pytest -m e2e`) on a demo-persona copy made a repository (`git init`, initial commit, a bare remote as upstream): rate a posting, the button is highlighted, press, it is quiet and shows the time, and the bare remote holds the rating. Verify that the test passes.

## 6. Image and deployment

- [ ] 6.1 `Dockerfile`: install `git` and `openssh-client` with `--no-install-recommends`. Verify with `docker build`.
- [ ] 6.2 `deploy/smoke.sh`:
  - the service user commits in a fresh repository with the fallback identity;
  - `ssh -V` runs;
  - git is at least 2.38;
  - no private key file (`id_*`, `*.pem`, `*.key`, a file starting with `-----BEGIN`) exists outside the dependency and browser directories.

  Verify with `deploy/smoke.sh <image>` on the built image.
- [ ] 6.3 `deploy/compose.yaml`: read-only `/keys` mount from `${JOBADVAISOR_SSH_DIR:-…}`, and `GIT_SSH_COMMAND` with the key name from `${JOBADVAISOR_SSH_KEY:-…}`. No host, provider or remote is named anywhere. Verify that `docker compose -f deploy/compose.yaml config --no-interpolate` parses, run with dummy env files so no secret is read.
- [ ] 6.4 Built-image check against a real SSH remote:
  1. Run the image with a demo-persona clone owned by 10001 bind-mounted.
  2. Run an SSH server container holding a bare repository as the remote, with the key and `known_hosts` mounted as documented.
  3. Use a non-default key directory and key name set in the Compose project's `.env`.
  4. Press the backup through `POST /backup`.

  Verify that the remote holds the commit, and that a run without the key reports `push failed` with ssh's reason while `GET /pool` still answers.

## 7. Documentation

- [ ] 7.1 ADR 0010 "The app commits and pushes the data repository" (alternatives: hand commits as today; a host cron job without UI feedback; GitPython or dulwich instead of the `git` command; an HTTPS token). Mark ADR 0001 and 0009 as partly superseded with a link, and add the index row. Verify that the links resolve.
- [ ] 7.2 README Deployment section:
  - "Commit and push the server's data" becomes the backup button, with its highlight and result;
  - first-time setup gains the keys directory (placeholders, owner 10001, mode 600), and the `.env` table gains `JOBADVAISOR_SSH_DIR` and `JOBADVAISOR_SSH_KEY` with their defaults; the remote comes from the data repository's `origin`, any SSH host;
  - "When the push is rejected" stays as the manual recovery until the sync slice, names the button instead of the hand commit, and ends with `chown -R 10001:10001 data` (git run as root leaves root-owned objects the container cannot write);
  - the update steps for this release add the one-time `chown` and the keys directory;
  - one sentence says not to point the scripts that write a data root (demo persona, evals) at a server's data repository;
  - the quick start says the backup button needs the demo copy to be a git repository, with the `git init` commands.

  Verify by reading it against the deployment delta's scenarios.
- [ ] 7.3 `AGENTS.md` "Current state": add this change and drop the oldest entry. Verify that it lists two changes.
- [ ] 7.4 Retake `docs/images/pool.png` per `AGENTS.md` ("README screenshot"), since the header gains the backup button. Verify that the new image shows the button at 1280 by 800 in light mode.
- [ ] 7.5 Run `/opsx:sync` after the last delta edit and `openspec validate backup-data-repository --strict`. Verify that both pass and the baseline specs in the diff show the target text.

## 8. Before the PR

- [ ] 8.1 Full suite: backend `uv run ruff check`, `uv run pytest`, `uv run pytest -m e2e`; frontend `npm run lint`, `npm test`, `npm run build`; `deploy/smoke.sh` on the built image. Verify that all pass.
- [ ] 8.2 Browser click test on the demo persona, made a repository with a bare remote as in 5.3: rate, watch the highlight, press, see the time; then with the bare remote moved away, press and see the failure while the pool still works. Verify by screenshots in the PR.
- [ ] 8.3 Review before the PR leaves draft:
  - a fresh review agent without history checks the diff against the specs and tasks;
  - `/code-review high` runs on the diff;
  - real findings from both are fixed in the same turn.

  Then `gh pr ready` on #95, rewrite its description for the implementation with `Closes #97` and `Refs #63`, and check that the follow-up monitor still runs. Verify that the PR is ready and the monitor is listed by `pr-monitor.sh status`.
- [ ] 8.4 On "fertig zum Mergen": tick the tasks, run `openspec archive backup-data-repository --yes` on this branch, and check that the baseline specs hold no duplicate requirement. Verify that `openspec list` shows no active change.

## Later slices (outline; each its own change, proposed after the previous one merges)

- **Slice 2, `backup-modes` (#98):**
  - settings page behind the header's gear icon, with a backup section only (#68 (Settings page for app-wide settings) moves the pool thresholds there later);
  - mode `manual` / `on_change` / `scheduled`;
  - debounce, default 60 seconds;
  - daily clock times in the user's time zone (check zone data in the image);
  - stored in the state directory;
  - the scheduler and debounce in the uvicorn process.
- **Slice 3, `sync-with-remote` (#99):**
  - a regular fetch in every mode, also without local changes (the interval a setting on the settings page): in `manual` it only feeds the highlight, in `on_change` and `scheduled` the remote's changes are applied;
  - a `git merge-tree --write-tree` check that leaves the working tree untouched;
  - merge under the write gate, then push;
  - on a conflict, stop with nothing touched and the file named;
  - the highlight also counts remote commits not yet applied;
  - the write gate held while git changes the tree, so the baseline scenario "Rating during a sync" (the rating is not saved) is modified to "the rating waits";
  - an ADR for merge over rebase, from the spike in which `rebase --abort` dropped writes made during the conflict and `merge --abort` failed after one;
  - the README's manual recovery replaced.
- **Slice 4, `conflict-banner` (#100):**
  - a banner on every view naming the file;
  - writes to that file held back;
  - reads skip it, `/health` included;
  - resume detection by repository state, with no restart;
  - `Closes #100`. #63 closes once all of its sub-issues are closed.
