# 0010. The app commits and pushes the data repository

## Status

Accepted, 2026-11-12. Supersedes the "the app never commits" part of [ADR 0001](0001-git-repository-as-user-data-store.md) and the hand commit and push of [ADR 0009](0009-container-from-ghcr-behind-tailscale-serve.md).

## Context

Ratings, scores and postings live as files in the data repository, and until now only the user's hand commit made them safe. On the server that meant a login and a `git commit` after every session, and a rating was lost with the server until someone did it ([#63](https://github.com/therealmodbom/jobadvaisor/issues/63)). The app already writes every file itself, through one module, so it knows best when something changed. The image is public and holds no secret (ADR 0009), and the data repository's remote is the user's own, usually reached over SSH.

## Decision

- **The app commits and pushes.** A backup button, in every view, stages what changed (also what was changed outside the app), commits it to `main` with a one-line message that says what changed, and pushes to the upstream of `main`. Without an upstream it only commits and says so. It never forces a push and never adds or changes a remote.
- **One write gate.** Every write of the app to the data repository holds one reentrant lock in `data/writer.py`, and the backup holds it from `git add` to the end of `git commit`, so a commit never holds half a write. The push holds no gate, so a rating during a slow push is stored at once and stays pending.
- **The `git` command, in a thread.** `data/backup.py` runs `git` through `subprocess`, with a timeout and without ever waiting for input. A press answers at once and the backup runs in a thread of the one uvicorn process, so the UI can show its progress.
- **Credentials from the host.** The image carries `git` and `openssh-client`, no key and no known hosts. The deployment mounts a directory read-only (key and `known_hosts`) and sets `GIT_SSH_COMMAND`. The remote itself, with its host, port and provider, is only the data repository's own `origin`; nothing in the image or the code names one.
- **The last result in the state directory.** The time of the last success and the last failure live in `backup.json` there. Losing the file loses only the display until the next backup.

## Alternatives considered

- **Hand commits, as before.** Nothing to build, but the server keeps unsaved data until someone logs in. Rejected: that is the problem.
- **A host cron job that commits and pushes.** Needs no app code, but it knows nothing about the write in progress, shows nothing in the UI, and a failed push is only a mail nobody reads. Rejected: no feedback.
- **GitPython or dulwich instead of the `git` command.** A Python API, but a new dependency, its own idea of hooks, config and SSH, and a lag behind git's behaviour. The `git` command is what the user runs by hand too. Rejected.
- **An HTTPS token as the credential.** It would put a secret into an environment variable or a file the container reads. The remote this was built for is SSH only, and a key mounted read-only keeps the secret on the host. Rejected for now; an HTTPS remote can be added later without changing the rest.
- **Per-file locks or a write queue.** A commit needs a moment in which no file changes, so it would have to take every lock anyway, and a queue adds ordering and error code for no gain in one process. Rejected for the one gate.

## Consequences

- A rating is only as safe as the last backup. The button shows when something is pending, and a failed backup keeps its reason on screen.
- `ADR 0001`'s statement that the user commits holds only for a data repository the app does not back up; the user may still commit by hand, and the next backup includes it.
- The image gains `git` and `openssh-client`, and the deployment gains a keys directory and two settings (`JOBADVAISOR_SSH_DIR`, `JOBADVAISOR_SSH_KEY`).
- Git run as root on the host leaves root-owned objects the container's user cannot write; the setup chowns the data directory to uid 10001.
- A script that writes a data root (the demo persona, the evals) is outside the gate. It must not point at a server's data repository.
- Fetching, merging a remote change and conflicts are not part of this decision; they follow in later slices, each with its own ADR where it decides something.
