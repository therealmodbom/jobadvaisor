# Spec Delta

## Purpose

Defines how the app runs as one always-available instance on a private server: what it ships as, who can reach it, where its configuration, secrets and data live, and how a release and a restore from the data repository's remote work.

## ADDED Requirements

### Requirement: One service for UI and API
A release image SHALL start one service in one container that answers both the API and the built UI on one port, and SHALL contain the browser that pages built by scripts need.

#### Scenario: Open the UI from the service
- **WHEN** the service runs and a browser requests `/`
- **THEN** the UI loads, and its requests to the API succeed on the same address

#### Scenario: Script-built posting page
- **WHEN** the user adds a link whose text the page builds with scripts
- **THEN** intake reads the page text with the browser in the image and does not fail with `browser failed`

### Requirement: Reachable on the private network only
The deployed service SHALL be reachable only from devices on the user's private network. It SHALL NOT listen on a public network interface.

#### Scenario: From a device on the private network
- **WHEN** a device on the private network opens the service's address
- **THEN** the UI loads without a login

#### Scenario: From the public internet
- **WHEN** a client outside the private network connects to the server's public address on the service's port
- **THEN** the connection is refused

### Requirement: Configurable port
The port the server publishes the service on SHALL be a setting of the deployment, with a default, and changing it SHALL NOT need a new image.

#### Scenario: Another port
- **WHEN** the user sets a different port in the deployment settings and recreates the service with the documented command
- **THEN** the UI answers on that port and no longer on the default

### Requirement: Secrets and settings from the host
The image SHALL contain no secret and no personal data. The service SHALL read its secrets from a file on the host that only its owner can read, and its other settings from the environment, using the same setting names as everywhere else.

#### Scenario: Image inspection
- **WHEN** the release image is searched for the values of the host's secret file and for data repository files
- **THEN** none is found

#### Scenario: Secret only in the host file
- **WHEN** the model key is set only in the host's secret file and the user starts a scoring pass
- **THEN** the pass reaches the model provider with that key

### Requirement: Data survives a restart
The data repository and the rebuildable state SHALL live outside the container, so that replacing or restarting the container keeps every posting, score and rating.

#### Scenario: Restart
- **WHEN** the user rates a posting, the container is restarted, and the user reloads the page
- **THEN** the posting shows the rating

#### Scenario: Update
- **WHEN** a newer image replaces the running one
- **THEN** all stored postings, scores and ratings are still there

### Requirement: Release produces the image
Pushing a release tag SHALL build the image and publish it to the registry under that tag, and the deployment documentation SHALL give the one command that updates the running service to it.

#### Scenario: Tag a release
- **WHEN** a release tag is pushed and the build passes
- **THEN** the registry holds an image with that tag

#### Scenario: Update the server
- **WHEN** the user runs the documented update command on the server
- **THEN** the service runs the newest image and the UI loads

### Requirement: The server works on a clone of the data repository's remote
The server SHALL hold the working copy of the data repository, cloned from the data repository's remote, which the server can read and write with the credentials stored on it. The remote MAY also be changed from other machines. The deployment documentation SHALL name the commands that commit and push the server's changes and that bring in the remote's changes, and a conflict between the two SHALL never be resolved silently: the sync stops, nothing is overwritten on either side, and the user resolves it on the server. The documented sync SHALL run with the service stopped, so that the app neither writes during it nor reads a half-merged file, and SHALL start the service again only when the sync has finished or been aborted. The data repository SHALL NOT be pushed to a publicly readable remote.

#### Scenario: Copy to a local computer
- **WHEN** the user has pushed the server's data and pulls on a local computer
- **THEN** that computer's data repository equals the server's committed data

#### Scenario: Unpushed changes
- **WHEN** the user rates a posting and has not yet committed and pushed
- **THEN** the documentation names the command that does both, and the remote lacks that rating until it runs

#### Scenario: Remote changed elsewhere
- **WHEN** another machine pushed a commit to the remote that does not touch what the server changed, and the user runs the documented sync
- **THEN** the server's data repository contains that commit and the app shows its data

#### Scenario: Conflicting change
- **WHEN** the remote and the server changed the same file differently and the user runs the documented sync
- **THEN** the sync stops with the conflicting file named, neither side is overwritten, the service stays stopped, and the user resolves the conflict on the server or aborts the sync, which restores the data from before it

#### Scenario: Aborted sync
- **WHEN** the user aborts a stopped sync and starts the service
- **THEN** the service shows exactly the data from before the sync, including every rating made since the last push

### Requirement: Restore from the data repository's remote
The deployment documentation SHALL describe how to rebuild the server's data repository and state from the remote alone, and the restore SHALL have been run once against a fresh clone.

#### Scenario: Restore
- **WHEN** the server's data repository directory and state directory are empty and the user follows the documented restore
- **THEN** the service starts with the postings, scores and ratings of the last push, and the state rebuilds from them
