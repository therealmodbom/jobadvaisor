# Spec Delta

## ADDED Requirements

### Requirement: Backup on request
On request, the system SHALL commit every pending change in the data repository, also changes made outside the app, as one commit on `main`, and then push `main` to its upstream. With nothing pending it SHALL make no commit and still push commits the upstream lacks. The data repository's history SHALL only grow: no force push, no rewritten commit.

#### Scenario: Pending changes
- **WHEN** the user has rated a posting and a file was edited by hand, and a backup runs
- **THEN** one new commit on `main` holds both changes, and the upstream has it afterwards

#### Scenario: Nothing pending
- **WHEN** the working tree is clean, the upstream lacks one earlier commit, and a backup runs
- **THEN** no commit is made and the upstream has the earlier commit afterwards

### Requirement: The commit message says what changed
A backup commit's message SHALL count the changed files by kind (ratings, scores, postings, company records, other files), and SHALL name only the kinds that changed.

#### Scenario: Ratings and a posting
- **WHEN** a backup commits three changed rating files and one new posting file
- **THEN** the message names 3 ratings and 1 posting, and no other kind

### Requirement: Backup without an upstream
When `main` has no upstream, a backup SHALL commit only, and its result SHALL say that nothing was pushed because no remote is set. The system SHALL NOT add or change a remote.

#### Scenario: Repository without a remote
- **WHEN** the data repository has no remote and a backup runs with pending changes
- **THEN** the changes are committed, the result says no remote is set, and the repository still has no remote

### Requirement: Backup only on main
When the data repository is not on branch `main`, or a merge, rebase or other git operation is in progress in it, a backup SHALL change nothing and SHALL report why.

#### Scenario: Another branch checked out
- **WHEN** the data repository is on another branch and a backup runs
- **THEN** no commit is made, nothing is pushed, and the result names the branch

### Requirement: A failed backup keeps every change
A failed commit or push SHALL leave every change on disk and every commit made in the repository, SHALL be reported with its reason, and SHALL NOT stop the app. A later backup SHALL retry what is still missing. A push that does not finish within a time limit SHALL count as failed.

#### Scenario: Remote unreachable
- **WHEN** a backup commits and the push cannot reach the remote
- **THEN** the commit stays, the result reports the push failure with git's reason, the app keeps serving, and the next backup with the remote reachable pushes that commit

#### Scenario: Push rejected
- **WHEN** the upstream has a commit the data repository lacks and a backup pushes
- **THEN** the push is rejected and reported, and the local commit and the remote's commit are both unchanged

### Requirement: Backup status
The system SHALL report whether anything is not backed up yet, meaning uncommitted changes or commits the upstream lacks (as git last saw the upstream), together with the time of the last successful backup and the last failure since then. A backup succeeds when everything is committed and, with an upstream, pushed.

#### Scenario: Change outside the app
- **WHEN** a file in the data repository is changed by hand after a successful backup
- **THEN** the status reports that something is not backed up

#### Scenario: After a successful backup
- **WHEN** a backup has committed and pushed everything
- **THEN** the status reports nothing pending, and the time of that backup

### Requirement: Writes and backups never interleave
No write of the app to the data repository SHALL run while a backup stages and commits. A write that arrives during that time SHALL wait and then run, so every write is either wholly in the commit or wholly outside it, and none is lost. The push SHALL NOT hold back writes.

#### Scenario: Rating during a backup
- **WHEN** a scoring pass writes scores, the user rates a posting, and a backup commits at the same time
- **THEN** every file in the commit is a complete, schema-valid file, and the rating is in the commit or still pending afterwards, never lost

#### Scenario: Rating while a push is slow
- **WHEN** a backup's push is still waiting for the remote and the user rates a posting
- **THEN** the rating is stored at once and shows as pending
