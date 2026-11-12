# data-repository Specification

## Purpose
Defines the user data repository: a separate git repository in a documented, versioned format that holds every piece of user data and is the source of truth for all local stores.

## Requirements

### Requirement: Documented schema per entity
The system SHALL define one versioned JSON Schema per entity — profile, policy pack, posting, label, score, pool (settings and pass history) — and publish the schemas in this repository as the public contract for external writers such as a legacy exporter. A posting MAY carry an application status and an origin mark; a score belongs to a posting by its ID. The policy pack MAY hold the user's import mapping for job lists (status column, status values per application status and skip, assessment column), so the layout of the user's own list lives in the data repository and not in this repository.

#### Scenario: Schema carries a version
- **WHEN** a schema file is read
- **THEN** it declares a schema version that data files reference

#### Scenario: External writer targets the schema
- **WHEN** a file written by an external tool conforms to the published schema
- **THEN** the system loads it without any tool-specific import step

#### Scenario: Earlier version loads
- **WHEN** a posting file references the schema version before this change
- **THEN** it loads, with the status open and no origin mark

### Requirement: Location from configuration
The system SHALL read the data repository location from configuration and SHALL NOT assume a fixed path.

#### Scenario: Configured location
- **WHEN** the configured location points to a valid data repository
- **THEN** the system loads profile, policy pack, postings and labels from it

#### Scenario: Missing location
- **WHEN** no location is configured or the path does not exist
- **THEN** the system refuses to start a triage run and reports which setting is missing

### Requirement: Validation on load
The system SHALL validate every data file against its schema on load and SHALL reject invalid files with an error naming the file and the violated constraint.

#### Scenario: Invalid file
- **WHEN** a posting file lacks a required field
- **THEN** loading fails with an error naming that file and field
- **AND** no partial data from that file is used

#### Scenario: Unsupported schema version
- **WHEN** a file references a schema version the system does not support
- **THEN** loading fails with an error naming the file, its version and the supported versions

### Requirement: Labels written back
The system SHALL write each new label to the data repository in the label schema, so labels survive a rebuild of every local store.

#### Scenario: Label persisted
- **WHEN** the user rates a posting
- **THEN** a schema-valid label file for that posting exists in the data repository

#### Scenario: Local stores rebuilt
- **WHEN** the local checkpoint and vector stores are deleted and the system starts again
- **THEN** retrieval and scoring use the same labels as before the deletion

### Requirement: Demo persona fixture
This repository SHALL contain a fictional demo persona data repository in the same schema, and tests, CI and demos SHALL use only that fixture.

#### Scenario: Fixture validates
- **WHEN** the demo persona fixture is loaded
- **THEN** every file passes schema validation

#### Scenario: Demo run
- **WHEN** the data repository location points to the demo persona fixture
- **THEN** a complete triage and rating cycle runs without any other user data

### Requirement: Scores and pool settings written back
The system SHALL write each posting's latest score, reasoning and scoring time, each pass's quality measure and the pool settings (hint threshold and rate) to the data repository in their schemas, so they survive a rebuild of every local store.

#### Scenario: Score persisted
- **WHEN** a pass scores a posting
- **THEN** a schema-valid score file for that posting exists in the data repository

#### Scenario: Local stores rebuilt
- **WHEN** the local checkpoint and vector stores are deleted and the system starts again
- **THEN** the pool shows the same scores, statuses and settings as before the deletion

### Requirement: Extraction labels
The data repository MAY hold an extraction-labels file with hand-settled feature values per posting ID and feature ID, and an optional minimum accuracy between 0 and 1 for the extractor. The file SHALL have a published schema and a schema version, SHALL be validated on load, and SHALL be absent without error. A label SHALL name a posting that exists and a feature of the feature set.

#### Scenario: File absent
- **WHEN** the file does not exist
- **THEN** the repository loads as before and the benchmark reports no accuracy

#### Scenario: Valid file
- **WHEN** the file conforms to its schema
- **THEN** the repository loads and the benchmark reads the labels and the minimum accuracy from it

#### Scenario: Label for a missing posting
- **WHEN** a label names a posting ID without a posting file
- **THEN** loading fails with an error naming the file and the posting ID

#### Scenario: Label for an unknown feature
- **WHEN** a label names a feature that is not in the feature set
- **THEN** loading fails with an error naming the file, the posting ID and the feature

#### Scenario: Minimum accuracy out of range
- **WHEN** the minimum accuracy lies outside 0 to 1
- **THEN** loading fails with an error naming the file and the value

### Requirement: Company records
The data repository MAY hold one company record per company, with a published schema and a schema version, validated on load. A record SHALL hold the company's name as the postings carry it, the source of its facts (LinkedIn, the employer's website or an entry by hand) and the fetch or entry date, and MAY hold a size class and a founding year. A repository without company records SHALL load as before.

#### Scenario: Records absent
- **WHEN** the repository has no company records
- **THEN** it loads, and extraction runs without company facts

#### Scenario: Valid record
- **WHEN** a record conforms to its schema
- **THEN** the repository loads and extraction for a posting of that company receives its facts

#### Scenario: Invalid record
- **WHEN** a record holds a founding year that is not a four-digit year, or a size class that is not a number range
- **THEN** loading fails with an error naming the file and the violated constraint

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
