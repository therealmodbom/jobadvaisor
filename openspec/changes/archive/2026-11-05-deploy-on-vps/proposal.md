# Proposal

## Why

The app runs only on the machine of whoever starts it. A user who wants one always-running instance, reachable from several devices without leaving a private network, has no way to deploy it. The container needs the data repository, so it ships together with moving that repository's working copy to the server, a clone of the repository's remote (#61, #62).

## What Changes

- A `Dockerfile` builds one image with the backend, the built frontend and Chromium. One container, one process serves UI and API on one port (the app already mounts `frontend/dist` at `/`).
- A Compose file runs it on a server: the container is published on the server's loopback address only, on a configurable port (default 8710). Secrets come from a mode-600 file on the server, other settings from a second file, the data repository and the state directory are volumes.
- A release tag builds the image in GitHub Actions and pushes it to GHCR. One documented command updates the server (`docker compose pull && docker compose up -d`).
- The server holds a clone of the data repository's remote, which it can read and write. The remote may also change from other machines, so the documentation gives the commands to commit and push the server's changes, plus a recovery path for a rejected push. During that recovery the app neither writes nor reads half-merged files, and a conflict stops it until the user resolves it or aborts on the server. Until #63 exists, the user runs commit and push by hand, and the recovery stops the service to meet that.
- The README documents publishing the loopback port to a private network. It uses `tailscale serve` as the worked example; any private-network setup that forwards to the loopback port works the same.
- A README section covers deployment, update, sync and the restore from the remote, which is tried once.
- `web-ui` requirement "served on localhost" widens to "localhost, or on a private network only when deployed".
- ADR 0009 records the registry and private-network decisions and the server's data clone.
- The user sets the GHCR package to public once after the first release (GitHub web step), so the server pulls without a login.

## Capabilities

### New Capabilities

- `deployment`: the container image, its release, how it is configured (secrets, settings, port, volumes), who can reach it, where the data repository lives and how it is backed up and restored.

### Modified Capabilities

- `web-ui`: the UI is served to a single user on localhost, or when deployed on a private network only; still no accounts or login.

## Impact

- New files: `Dockerfile`, `.dockerignore`, `compose.yaml`, a release workflow under `.github/workflows/`, ADR 0009, a README section.
- `.env.example` and `settings.py` do not change: container configuration uses the existing variables (`DATA_REPOSITORY`, `STATE_DIRECTORY`, secrets via the environment). If the image build shows a needed variable, the change adds it to both.
- The server gets the data clone, the settings and secrets files, the Compose file and one entry that publishes the loopback port to the private network. Existing entries stay untouched.
- No change to LLM-backed behavior, so no new eval.

## Non-goals

- Automatic commit and push by the app (#63).
- Reading job alert mails (#56, #57, #58).
- Accounts or login. The private network is the only access control.
- Changing how the server reaches the remote (joining it to the private network, new credentials). The server uses the access it already has.
- Automatic, scheduled sync with the remote and notifying the user of a conflict: #63.
- AI-assisted conflict resolution. Changes git can combine without overlap go through on their own; a real conflict is resolved by the user on the server. Agent support would need much more in the app and is a later change.
- Postgres or any change to the stores (ADR 0004).
- Anything else running on the server.
