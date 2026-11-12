# Proposal

## Why

The app writes ratings, scores and postings into the data repository and never commits them. The user commits and pushes by hand, on the server with `git -C /srv/jobadvaisor/data …`, so the remote lacks every rating since the last time they remembered, and a lost server loses them. This change is the first of four slices of [#63](https://github.com/therealmodbom/jobadvaisor/issues/63) (Back up user data automatically), tracked as its sub-issue [#97](https://github.com/therealmodbom/jobadvaisor/issues/97): the app commits and pushes on a button press, and shows when something is not backed up yet.

## What Changes

- A backup button on every view. A press commits everything pending in the data repository on `main`, with a message that says in a few words what changed, then pushes to the branch's upstream. Without an upstream it commits only and says so.
- The button is highlighted while the data repository has uncommitted changes, also ones made outside the app, or commits its upstream lacks. Otherwise it is quiet.
- The UI shows the time of the last successful backup, and a failed commit or push with its reason. A failure does not block the app, and the next press retries.
- One write gate in the app: every write to the data repository and every backup commit take it, so a commit never contains a half-finished write and no write lands while git stages and commits.
- The release image carries `git` and an SSH client. The deployment mounts a key and a `known_hosts` file read-only, so the container pushes to an SSH remote with credentials that stay on the host. The remote comes from the data repository itself, and the key's location is a deployment setting, so any installation can push to its own host and provider with the same image.
- A press runs the backup in the background and shows its progress: the step, the number of files, and the push's percentage.
- **BREAKING** (documentation contract): the app commits its own changes. ADR 0010 supersedes the "never commits" part of ADR 0001 and the hand commit in ADR 0009. The README's "Commit and push the server's data" section becomes the backup button and the credential setup. The rejected-push recovery stays manual until slice 3.

Later slices, each its own change and PR, proposed once the slice before it has merged:

2. The modes `manual`, `on_change` (debounced, default 60 seconds) and `scheduled` (daily clock times in the user's time zone), set on a new settings page reached by a gear icon in the header and stored in the state directory.
3. Sync with the remote: fetch, a conflict check that leaves the working tree untouched, merge, push. A conflict stops the sync without touching anything; the button's highlight also shows remote changes not yet applied.
4. Conflicts keep the app running: a banner on every view names the file, writes to that file are held back, and the app continues by itself once the user resolves or aborts.

## Non-goals

- Automatic modes, the settings page, fetching and merging from the remote, and the conflict banner (slices 2 to 4).
- AI-assisted conflict resolution (out of scope for #63).
- Pushing to a remote the app configures itself. The app never adds or changes a remote, and pushes only to the upstream the user set.
- HTTPS remotes with a token. The documented setup is SSH. Any remote git reaches with the mounted credentials works, but nothing else is set up or tested.
- Showing other devices' changes live (#66 (Show changes live on every open device)).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `data-repository`: the app commits and pushes its data on request, writes and commits never interleave, and the app reports what is not backed up.
- `deployment`: the image carries git and an SSH client, push credentials are mounted from the host, and the documentation names the backup button instead of the hand commit.
- `web-ui`: a backup button on every view with its highlight, its result and the last successful backup.

## Impact

- Backend: `data/writer.py` (one write gate replaces `_pool_lock` and `_update_lock`), a new `data/backup.py` (status, commit, push through the `git` command), `GET /backup` and `POST /backup` in `api/app.py`, the last successful backup in the state directory.
- Frontend: a backup control in the app shell (`App.tsx`), its status hook and API types. Its look and position are settled in a Design artifact session before any UI code.
- Image and deployment: `Dockerfile` (git, openssh-client), `deploy/compose.yaml` (read-only key mount, placeholder paths), `deploy/smoke.sh` (git and ssh present, a commit as uid 10001).
- Docs: ADR 0010, ADR 0001 and 0009 marked as partly superseded, README Deployment section, `writer.py` module docstring.
- Dependencies: no new Python or npm package. The `git` command does the work.
