# Design

## Context

See proposal.md for the motivation. The current state that shapes the approach:

- Every app write to the data repository goes through the public functions of `backend/jobadvaisor/data/writer.py`. They write a temporary file (`.<name>.tmp`, `.<random>.new` for new postings) and rename it into place. The one exception is the rollback of `merge_extraction_labels`, which writes the old content back in place. Two process-local locks, `_pool_lock` and `_update_lock`, serialise some read-modify-writes. `write_label`, `write_score`, `write_company`, `write_pool`, `create_posting` and `merge_extraction_labels` take no lock. Scripts that write a data root (`data/demo_persona.py`, `data/trim_linkedin.py`, the evals) run outside the server process.
- One uvicorn worker (`Dockerfile`, last line). Sync routes and background passes run in threads of that one process.
- The release image (`python:3.12-slim`) has no `git` and no `ssh`. The service user is uid 10001 with no home directory. The README's first-time setup chowns the data directory to 10001 and sets a repository-local `user.name` and `user.email`.
- `/health` loads the whole repository. The backup status does not touch it.

## Goals / Non-Goals

**Goals:**

- A backup that can run while ratings and passes write, without a commit ever holding a temporary file or missing half of one write.
- A status check cheap enough to poll every 15 seconds per open tab.
- A container that commits and pushes over SSH with credentials that never enter the image.

**Non-Goals:**

- Fetching, merging and conflict handling (slices 3 and 4). This slice never changes the working tree's tracked content through git: it only stages, commits and pushes.
- Locks across processes. A script writing the same data repository while the server commits is not guarded (see Risks).

## Decisions

### Why the app commits at all

[ADR 0010](../../../docs/decisions/0010-the-app-commits-and-pushes-the-data-repository.md) records the decision and the rejected alternatives. It supersedes the "never commits" part of ADR 0001 and the hand commit of ADR 0009.

### One write gate in `writer.py`

A module-level `threading.RLock`, `write_gate`, replaces `_pool_lock` and `_update_lock`. Every public write function holds it for its whole read-modify-write, and the backup holds it from `git add` to the end of `git commit`. It is reentrant because write functions call each other (`write_guard` → `update_posting` → `_update_json`).

- The gate is in the writer, not at the call sites (`api/app.py`, `triage/graph.py`, `intake/*`, `tools/guard.py`). Every call site goes through the writer, so one place covers them all, and a new call site is covered without remembering to.
- Writes wait for the gate instead of being refused. Staging and committing a few hundred small files takes well under a second, so a rating during a backup only takes a little longer. A rating is never refused or lost.
- Rejected: per-file locks. A commit needs a moment in which no file changes, so it would have to take every lock anyway.
- Rejected: a write queue in a worker thread. It adds ordering and error-propagation code for no gain over a lock, in a single process.

Slice 3 holds the same gate while git changes the working tree. A rating during a sync then waits, so slice 3 modifies the baseline scenario "Rating during a sync", which says the user sees that the rating was not saved.

### `git` through `subprocess`, in `data/backup.py`

A new module `data/backup.py` runs the `git` command (`git -C <root> …`) with a timeout, and adds no Python package. ADR 0010 says why no git library is used.

Every call runs with `GIT_TERMINAL_PROMPT=0`, so git never waits for input. Status calls also run with `GIT_OPTIONAL_LOCKS=0`, so a poll never takes `index.lock` while a backup commits.

- **Own repository:** `git rev-parse --show-toplevel` must equal the resolved data repository path. Otherwise the backup is unavailable. A plain directory fails this check, and so does a directory inside another repository: a commit there would land in the enclosing repository.
- **Temporary files:** status and staging use the same exclude pathspecs, `':(exclude,glob)**/.*.tmp' ':(exclude,glob)**/.*.new'`. A crashed write's leftover then never counts as pending and is never committed.
- **Status:**
  - `git status --porcelain=v1 -z --untracked-files=all -- . <excludes>` gives the uncommitted changes, also those made outside the app.
  - `git symbolic-ref --short -q HEAD` gives the branch, or `null` on a detached HEAD, as during a rebase.
  - `git rev-list --count @{upstream}..HEAD` gives the commits the upstream lacks, as of the last push or fetch.
  - A `MERGE_HEAD`, `CHERRY_PICK_HEAD`, `REVERT_HEAD`, `rebase-merge` or `rebase-apply` under `git rev-parse --git-dir` means an operation is in progress.
- **Backup:**
  1. Refuse when not on `main` or when an operation is in progress.
  2. Under the gate: `git add -A -- . <excludes>`, then `git reset -q -- ':(glob)**/.*.tmp' ':(glob)**/.*.new'`. The exclude only keeps `add` from staging a temporary file; one already staged by hand would still be committed, and the reset unstages it. Then `git diff --cached --name-only` for the message, and `git commit` when something is staged.
  3. Outside the gate: when `main` has an upstream, `git push --progress <remote> HEAD:<merge ref>` from `branch.main.remote` and `branch.main.merge`, with a 60-second timeout. Never `--force`.
- **Background run and progress:** `POST /backup` checks the refusals, then starts the backup in a thread and answers at once, like `POST /pool/passes`. The thread records its step (`staging`, `committing`, `pushing`), the number of staged files, and the push percentage. It reads the percentage from git's `Writing objects:  60% (12/20)` lines on stderr, which `--progress` writes even without a terminal, separated by `\r` rather than newlines (probed with git 2.56). A push too small to print progress shows no percentage.
- **Identity:** the repository's own `user.name` and `user.email` when it has them, as the README's setup gives it. Otherwise `JobAdvAIsor <jobadvaisor@localhost>` through `GIT_AUTHOR_*` and `GIT_COMMITTER_*` for that one commit. The container has no global git config to fall back on.
- **Message:** one subject line, for example `Backup: 2 ratings, 12 scores, 1 posting, 1 company record, 1 other file`. The kinds appear in that fixed order. Kinds come from the first path segment:
  - `labels/` are ratings.
  - `scores/` are scores.
  - `postings/` are postings.
  - `companies/` are company records.
  - Anything else counts as other files.
  - A kind gets the singular form for a count of 1, and only kinds with a count appear.
- **One backup at a time:** a second press while one runs gets `409 backup running` (a non-blocking lock in `Backup`). It does not queue.

### API

The routes follow the `{error, detail}` convention of the other routes:

- `GET /backup` → `{"pending", "uncommitted", "unpushed", "branch", "remote", "operation", "running", "progress", "last_result", "last_success", "last_failure"}`.
  - `pending` is `uncommitted > 0 or unpushed > 0`.
  - `remote` is the upstream's name or `null`.
  - `operation` is the in-progress git operation or `null`.
  - `progress` is `{step, files, percent}` while a backup runs, else `null`. `percent` is `null` until git reports one.
  - `last_result` is `{at, result, commit}` of the last backup that finished. `result` is `pushed`, `committed` (no upstream) or `up_to_date`.
  - `last_failure` is `{at, step, reason}` or `null`, where `step` is `commit` or `push` and `reason` is git's message.
  - A data directory that is not the top level of its own git repository answers `409 backup unavailable`, with the reason as the detail. `POST` answers the same.
- `POST /backup` takes no body. It starts the backup and answers `202 {"status"}`, with `running` true.
  - `409 backup running`.
  - `409 backup refused`, with the branch or the operation as the detail.
  - `409 backup unavailable`.
  - A commit or push failure appears later in `last_failure` of `GET /backup`. The commit stays.

`create_app` takes an optional `backup`, built from `intake.root` and that repository's `state_path` (`index.py`) when absent, the same way the other dependencies are. Tests pass their own.

### Last success and failure in the state directory

The file `backup.json` in the data repository's own state path (`<STATE_DIRECTORY>/<name>-<hash>`, as the local stores use) holds `last_success` and `last_failure`. A success clears the failure.

- Git cannot hold this information: a failed push leaves no trace in git, and "last successful backup" includes the push.
- Losing the file loses only the display until the next backup, so the state directory stays rebuildable in practice.
- Slice 2 adds the backup settings next to it, and changes the state directory's contract in its spec at that point.

### Frontend

The pieces:

- A hook `useBackupStatus` fetches `GET /backup` on mount, when the tab becomes visible, every second while `running`, and every 15 seconds otherwise while the tab is visible. Its shape is the same as `useBackendVersion`.
- A component `BackupControl` in the app shell shows the button, its highlight, the progress (step, files, percent), the result line and the last successful backup.
- The button is on every view as a trial. Whether it stays there or moves to the settings page is decided after daily use.

Its look and position in the header are settled in a Design artifact session on the JobAdvAIsor design system **before any UI code** (tasks.md, group 4). Slice 2's gear icon for the settings page is designed in the same session, so the header is laid out once.

### Image and deployment

- `Dockerfile`: `apt-get install --no-install-recommends git openssh-client` in the runtime stage. Slice 3 needs `git merge-tree --write-tree` (git ≥ 2.38), so the smoke check asserts the version.
- `deploy/compose.yaml`:
  - Mounts `${JOBADVAISOR_SSH_DIR:-/srv/jobadvaisor/keys}` read-only at `/keys`. The directory holds the key and `known_hosts`, owned by 10001, with the key at mode 600.
  - Sets `GIT_SSH_COMMAND=ssh -i /keys/${JOBADVAISOR_SSH_KEY:-id_ed25519} -o UserKnownHostsFile=/keys/known_hosts -o StrictHostKeyChecking=yes -o BatchMode=yes`.
  - Both variables live in the Compose project's `.env` next to `JOBADVAISOR_TAG`, so each installation sets its own without editing `compose.yaml`.
  - The remote, and with it the host, the port (`ssh://host:port/path`) and the provider, comes only from the data repository's own `origin`. Nothing in the image or the code names one.
  - `GIT_SSH_COMMAND` is a git variable, not an app setting, so `.env.example` and `Settings` do not change.
  - A local run outside the container uses the user's own `ssh` setup unchanged.
- `deploy/smoke.sh`:
  - As the service user, `git init` a repository in a temporary directory, commit with the fallback identity, and check that it succeeded.
  - Check that `ssh -V` runs.
  - Check that the git version is at least 2.38.

### No LLM-backed behaviour

This change adds no LLM call, so it needs no eval.

## Risks / Trade-offs

- [A script (`demo_persona.py`, an eval) writes the same data repository while the server commits] → Those scripts write their own roots, not a live server's data. The README gains a sentence saying not to point them at a server's data repository (task 7.2). A cross-process lock is out of proportion for this.
- [A write sequence spans several writer calls (intake creates a posting, then stores its guard result), so a backup can commit the first half] → Every file is valid on its own and the second half is pending afterwards, so the next backup has it. No reader depends on the two arriving in one commit.
- [The push holds no gate, so a write during a push is not in the pushed commit] → It shows as pending, which is the truth. The spec requires exactly this.
- [Without mounted credentials, every press on the server fails the push, and the button stays highlighted] → That is the honest state until the key is mounted. The README's setup step names it, and the failure shows git's reason.
- [ssh as a user without a home directory warns that it cannot create `~/.ssh`] → The known-hosts file and the key are given explicitly and `BatchMode` is set, so the warning has no effect. The built image is verified against a real SSH remote before the PR (tasks.md, group 5).
- [Git run as root on the host (the hand commits so far, the manual recovery that stays until slice 3) leaves root-owned directories under `.git/objects`, so the container's commit fails with "insufficient permission"] → The migration plan and the README's recovery end with `chown -R 10001:10001` on the data directory.
- [A pre-commit hook in the data repository rejects the commit] → It is reported as `commit failed` with the hook's output. The data repository's rules say it has no hook.

## Migration Plan

1. Release the image with git, and copy the new `compose.yaml` together with the new release, as the README already says for compose changes.
2. On the server, create `/srv/jobadvaisor/keys` with the key and `known_hosts`, chown them to 10001 and set the key to mode 600 (README).
3. Run `chown -R 10001:10001` on the data directory once, since earlier hand commits as root may have left root-owned objects.
4. The first press commits everything uncommitted since the last hand commit, in one commit.

Rollback: the previous image ignores the new mount and variable. The commits the app made are ordinary commits.
