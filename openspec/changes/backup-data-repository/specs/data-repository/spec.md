# Spec Delta

## ADDED Requirements

### Requirement: Backup on request
On request, the system SHALL commit every pending change in the data repository, also changes made outside the app, as one commit on `main`, and then push `main` to its upstream. With nothing pending it SHALL make no commit and still push commits the upstream lacks.

#### Scenario: Pending changes
- **WHEN** the user has rated a posting and a file was edited by hand, and a backup runs
- **THEN** one new commit on `main` holds both changes, and the upstream has it afterwards

#### Scenario: Nothing pending
- **WHEN** the working tree is clean, the upstream lacks one earlier commit, and a backup runs
- **THEN** no commit is made and the upstream has the earlier commit afterwards

### Requirement: A backup never rewrites history
A backup SHALL NOT force-push and SHALL NOT rewrite or drop an existing commit, locally or on the remote.

#### Scenario: Upstream ahead
- **WHEN** the upstream has a commit the data repository lacks and a backup pushes
- **THEN** the push is rejected, and the local commits and the remote's commits are all unchanged

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

### Requirement: Backup only in the data repository's own git repository
A backup SHALL run only when the data repository's directory is the top level of its own git repository. Otherwise backup and status SHALL report the backup as unavailable and SHALL change nothing, also in an enclosing repository.

#### Scenario: Plain directory
- **WHEN** the data repository is a copied directory without git and the status is requested
- **THEN** the backup is reported unavailable, with the reason

#### Scenario: Directory inside another repository
- **WHEN** the data repository is a subdirectory of another git repository and a backup is requested
- **THEN** nothing is committed in that other repository, and the backup is reported unavailable

### Requirement: Backup only on main
When the data repository is not on branch `main`, or a merge, rebase or other git operation is in progress in it, a backup SHALL change nothing and SHALL report why.

#### Scenario: Another branch checked out
- **WHEN** the data repository is on another branch and a backup runs
- **THEN** no commit is made, nothing is pushed, and the result names the branch

#### Scenario: Operation in progress
- **WHEN** a merge stopped on a conflict in the data repository and a backup runs
- **THEN** no commit is made, nothing is pushed, and the result names the operation

### Requirement: One backup at a time
A backup requested while another runs SHALL be refused and SHALL NOT be queued.

#### Scenario: Second request
- **WHEN** a backup is pushing and a second backup is requested
- **THEN** the second is refused as already running, and the first finishes unaffected

### Requirement: A failed backup keeps every change
A failed commit or push SHALL leave every change on disk and every commit made in the repository, SHALL be reported with its reason, and SHALL NOT stop the app. A later backup SHALL retry what is still missing. A push that does not finish within a time limit SHALL count as failed.

#### Scenario: Remote unreachable
- **WHEN** a backup commits and the push cannot reach the remote
- **THEN** the commit stays, the result reports the push failure with git's reason, the app keeps serving, and the next backup with the remote reachable pushes that commit

#### Scenario: Commit fails
- **WHEN** git refuses the commit
- **THEN** every change stays on disk and pending, the result reports the commit failure with git's reason, and the app keeps serving

### Requirement: Backup status reports what is pending
The system SHALL report whether anything is not backed up yet: uncommitted changes, or commits the upstream lacks as git last saw the upstream. Temporary files the app writes while storing a file SHALL NOT count.

#### Scenario: Change outside the app
- **WHEN** a file in the data repository is changed by hand after a successful backup
- **THEN** the status reports that something is not backed up

#### Scenario: Leftover temporary file
- **WHEN** a crashed write left a temporary file behind and a backup succeeded since
- **THEN** the status reports nothing pending, and the temporary file is in no commit

### Requirement: Backup status reports the last result
The system SHALL report the time of the last successful backup of this data repository and the last failure since then, with the step that failed and its reason. A backup succeeds when everything is committed and, with an upstream, pushed.

#### Scenario: After a successful backup
- **WHEN** a backup has committed and pushed everything
- **THEN** the status reports nothing pending, the time of that backup and no failure

#### Scenario: After a failed push
- **WHEN** the last backup's push failed
- **THEN** the status reports the earlier successful backup's time and the push failure with its reason

### Requirement: Writes and backups never interleave
No write of the app to the data repository SHALL run while a backup stages and commits. A write that arrives during that time SHALL wait and then run, so every write is either wholly in the commit or wholly outside it, and none is lost. The push SHALL NOT hold back writes.

#### Scenario: Rating during a backup
- **WHEN** a scoring pass writes scores, the user rates a posting, and a backup commits at the same time
- **THEN** every file in the commit is a complete, schema-valid file, and the rating is in the commit or still pending afterwards, never lost

#### Scenario: Rating while a push is slow
- **WHEN** a backup's push is still waiting for the remote and the user rates a posting
- **THEN** the rating is stored at once and shows as pending
