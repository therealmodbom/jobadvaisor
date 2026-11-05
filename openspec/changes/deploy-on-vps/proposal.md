# Proposal

## Why

The app runs only on the machine of whoever starts it. The owner wants one always-running instance, reachable from the owner's computers and phone, without leaving the private network. The container needs the data repository, so it ships together with the move of that repository to the VPS and its backup remote on the NAS (#61 (Deploy as a container on the VPS, reachable over the Tailnet), #62 (Data repository on the VPS with the NAS as its backup remote)).

## What Changes

- A `Dockerfile` builds one image with the backend, the built frontend and Chromium. One process serves UI and API on port 8710 (the app already mounts `frontend/dist` at `/`).
- A Compose file runs it on the VPS: the container listens on `127.0.0.1:8710` only, secrets come from a mode-600 `.env` on the VPS, the data repository and the state directory are volumes.
- A release tag builds the image in GitHub Actions and pushes it to GHCR. One documented command (`docker compose pull && docker compose up -d`) updates the VPS.
- The VPS holds a clone of `jobadvaisor-data.git` from the NAS and is the only writer. The Mac only pulls. Until #63 (Back up user data automatically) exists, the VPS commits and pushes by hand, with a documented command.
- `tailscale serve` publishes the container to the Tailnet over HTTPS on its own port. This is a one-time setup step on the VPS, documented in the README.
- A README section covers deployment, update, backup and the restore from the NAS, which is tried once.
- `web-ui` requirement "served on localhost" widens to "localhost or a Tailnet-only deployment".
- ADR 0009 records the registry-and-Tailnet decision and the VPS as sole writer.
- The owner sets the GHCR package to public once after the first release (GitHub web step), so the VPS pulls without a login.

## Capabilities

### New Capabilities

- `deployment`: the container image, its release, how it is configured (secrets, settings, volumes), who can reach it, where the data repository lives and how it is backed up and restored.

### Modified Capabilities

- `web-ui`: the UI is served to a single user on localhost, or when deployed on the owner's private network only; still no accounts or login.

## Impact

- New files: `Dockerfile`, `.dockerignore`, `compose.yaml`, a release workflow under `.github/workflows/`, ADR 0009, a README section.
- `.env.example` and `settings.py` do not change: container configuration uses the existing variables (`DATA_REPOSITORY`, `STATE_DIRECTORY`, secrets via the environment). If the image build shows a needed variable, the change adds it to both.
- The VPS gets the data clone, a `.env`, the Compose file and one `tailscale serve` entry. Existing `tailscale serve` entries stay untouched.
- No change to LLM-backed behavior, so no new eval.

## Non-goals

- Automatic commit and push by the app (#63 (Back up user data automatically)).
- Reading job alert mails (#56 (Intake: find the postings in a job alert mail), #57 (Intake: pasted job alert text with a pick list), #58 (Intake: read job alert mails from a configured mailbox)).
- Accounts or login. The Tailnet is the only access control.
- Putting the NAS into the Tailnet. The VPS reaches the NAS with the SSH key it already has.
- Postgres or any change to the stores (ADR 0004).
- Anything else running on the VPS.
