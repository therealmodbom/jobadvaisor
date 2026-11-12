# deployment Specification

## Purpose
Defines how the app runs as one always-available instance on a private server: what it ships as, who can reach it, where its configuration, secrets and data live, and how a release and a restore from the data repository's remote work.

## Requirements

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
The server SHALL hold the working copy of the data repository, cloned from the data repository's remote, which the server can read and write with the credentials stored on it. The remote MAY also be changed from other machines. The data repository SHALL NOT be pushed to a publicly readable remote.

#### Scenario: Copy to a local computer
- **WHEN** the user has pushed the server's data and pulls on a local computer
- **THEN** that computer's data repository equals the server's committed data

### Requirement: The documentation names the sync commands
The deployment documentation SHALL name the backup button as the way to commit and push the server's changes, and SHALL name the recovery path for when a push is rejected because the remote has changes the server lacks.

#### Scenario: Unpushed changes
- **WHEN** the user rates a posting and has not pressed the backup button since
- **THEN** the documentation says the remote lacks that rating until the button is pressed

#### Scenario: Remote changed elsewhere
- **WHEN** another machine pushed a commit to the remote that does not touch what the server changed, the server's push is rejected, and the user follows the documented recovery
- **THEN** the server's data repository contains that commit together with its own changes, the push succeeds, and the app shows the data of both

### Requirement: A sync never races the app
While a sync changes the working copy of the data repository, the app SHALL NOT write to it and SHALL NOT read a file that is half-merged or in conflict. This holds until the sync has finished or been aborted.

#### Scenario: Rating during a sync
- **WHEN** a sync is changing the working copy and the user submits a rating
- **THEN** the rating is not written into the changing working copy, and the user sees that it was not saved

#### Scenario: Conflict pending
- **WHEN** a sync has stopped on a conflict
- **THEN** the app serves no data from the conflicted file until the user has resolved the conflict or aborted the sync

### Requirement: A conflict is never resolved silently
When the remote's changes and the server's changes conflict, the sync SHALL stop with nothing overwritten on either side, and the user SHALL resolve the conflict on the server or abort the sync.

#### Scenario: Conflicting change
- **WHEN** the remote and the server changed the same file differently and the user follows the documented recovery
- **THEN** the sync stops with the conflicting file named, neither side is overwritten, and the user resolves the conflict on the server or aborts the sync, which restores the data from before it

#### Scenario: Aborted sync
- **WHEN** the user aborts a sync that stopped on a conflict
- **THEN** the app shows exactly the data from before the sync, including every rating made since the last push

### Requirement: Restore from the data repository's remote
The deployment documentation SHALL describe how to rebuild the server's data repository and state from the remote alone, and the restore SHALL have been run once against a fresh clone.

#### Scenario: Restore
- **WHEN** the server's data repository directory and state directory are empty and the user follows the documented restore
- **THEN** the service starts with the postings, scores and ratings of the last push, and the state rebuilds from them

### Requirement: The image reports its release
The image built for a release tag SHALL report that tag as its version, in the backend's health answer and in the frontend it serves, and the image built without a tag SHALL report `dev`. Both come from the same build, and the deployment's settings and environment SHALL NOT change the version.

#### Scenario: Version of a release image
- **WHEN** the image of release `v0.1.0` runs and a client requests the backend's health
- **THEN** the answer's version is `v0.1.0`, and the frontend served by the same image carries `v0.1.0`

#### Scenario: Settings cannot change the version
- **WHEN** the deployment's settings or environment name a different version for the container of release `v0.1.0`
- **THEN** the backend's health answer still carries `v0.1.0`

#### Scenario: Image outside a release
- **WHEN** the image is built without a version, as a local build is
- **THEN** its backend and its frontend report `dev`

#### Scenario: Check of the built image
- **WHEN** the smoke check runs on an image built with a version
- **THEN** it fails unless the image's backend and frontend both report that version, whether or not a data repository is present

### Requirement: The documentation names where the version is shown
The deployment documentation SHALL say where to see the running version.

#### Scenario: Looking up the running version
- **WHEN** the user reads the deployment documentation to find out which release runs
- **THEN** it names the page footer and the backend's health answer as the places that show it

### Requirement: The backend reports its health
The backend SHALL answer a health request with its status, the result of each check and the version it runs. The one check is that the data repository loads. When it passes, the status SHALL be `ok` and the answer a success; when it fails, the status SHALL be `fail`, the check SHALL carry its error, and the answer SHALL be an error status with the same fields, so that the version is reported in both cases. The request SHALL need no credentials.

#### Scenario: Data repository loads
- **WHEN** a client requests the health of a backend whose data repository loads
- **THEN** the answer is a success with status `ok`, the data repository check `ok` and the backend's version

#### Scenario: Data repository does not load
- **WHEN** a client requests the health of a backend whose data repository does not load
- **THEN** the answer is an error status with status `fail`, the data repository check carrying the load error, and the backend's version

### Requirement: The container healthcheck uses the health answer
The deployment's container healthcheck SHALL request the backend's health, so that a data repository that does not load shows the container as unhealthy.

#### Scenario: Container healthcheck
- **WHEN** the data repository of a running container stops loading
- **THEN** the container shows as unhealthy, and is not restarted by that alone

### Requirement: The image can commit and push
The release image SHALL contain git and an SSH client, and its service user SHALL be able to commit in a data repository owned by that user, without a home directory.

#### Scenario: Commit in the image
- **WHEN** the smoke check runs on a built image
- **THEN** it fails unless the service user can commit in a fresh repository and both git and the SSH client report a version

### Requirement: No push credential in the image
The release image SHALL NOT contain a push credential, such as an SSH key or a token.

#### Scenario: Image inspection for keys
- **WHEN** the release image is searched for private key files
- **THEN** none is found

### Requirement: Push credentials from the host
The deployment SHALL mount the SSH key and the known-hosts file from the host read-only, and the documentation SHALL describe this with placeholder paths. Without them, a push SHALL fail with a reported reason and the app SHALL keep running.

#### Scenario: Credentials mounted
- **WHEN** the key and known-hosts file are mounted as documented and the user presses the backup button
- **THEN** the push reaches the data repository's SSH remote

#### Scenario: Credentials missing
- **WHEN** the container runs without the key and the user presses the backup button
- **THEN** the changes are committed, the push fails with its reason shown, and the app keeps serving
