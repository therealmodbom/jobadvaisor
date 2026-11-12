# Spec Delta

## ADDED Requirements

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

### Requirement: Any SSH remote, configured per installation
The image and the code SHALL name no remote host or provider: a backup pushes to the upstream the data repository itself names. The host directory that holds the key and the known-hosts file, and the key's file name, SHALL be deployment settings with defaults, so that another installation uses its own host, provider and key without changing the image or the Compose file.

#### Scenario: Another installation
- **WHEN** an installation's data repository has an SSH remote at another provider, and its deployment settings name its own key directory and key file
- **THEN** the backup pushes to that remote with that key, with the same image and Compose file

## MODIFIED Requirements

### Requirement: The documentation names the sync commands
The deployment documentation SHALL name the backup button as the way to commit and push the server's changes, and SHALL name the recovery path for when a push is rejected because the remote has changes the server lacks.

#### Scenario: Unpushed changes
- **WHEN** the user rates a posting and has not pressed the backup button since
- **THEN** the documentation says the remote lacks that rating until the button is pressed

#### Scenario: Remote changed elsewhere
- **WHEN** another machine pushed a commit to the remote that does not touch what the server changed, the server's push is rejected, and the user follows the documented recovery
- **THEN** the server's data repository contains that commit together with its own changes, the push succeeds, and the app shows the data of both
