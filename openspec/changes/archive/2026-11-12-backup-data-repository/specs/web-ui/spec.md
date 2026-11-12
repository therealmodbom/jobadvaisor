# Spec Delta

## ADDED Requirements

### Requirement: Backup button on every view
Every view SHALL show a backup button. It SHALL be highlighted while the backend reports something not backed up yet, and quiet otherwise.

#### Scenario: After a rating
- **WHEN** the user rates a posting after a successful backup
- **THEN** the button is highlighted

#### Scenario: Nothing pending
- **WHEN** the backend reports nothing pending
- **THEN** the button is shown without the highlight

### Requirement: Backup status kept current
The UI SHALL fetch the backup status when the page loads, when the tab becomes visible, every second while a backup runs, and every 15 seconds otherwise while the tab is visible. A failed fetch SHALL leave the last status shown.

#### Scenario: Change made outside the app
- **WHEN** a file in the data repository is changed by hand while the tab is open and visible
- **THEN** the button is highlighted within 15 seconds

### Requirement: Backup unavailable
When the backend reports the backup as unavailable, the button SHALL be disabled, with a visible, focusable info icon that gives the reason.

#### Scenario: Data directory without git
- **WHEN** the data repository is a plain copied directory
- **THEN** the button is disabled and its info icon says the data directory is not a git repository

### Requirement: Backup progress shown
While a backup runs, the UI SHALL show its current step, the number of files being committed and, during the push, the share git reports as done, so the user can see where it stands.

#### Scenario: Push under way
- **WHEN** a backup of 40 files is pushing and the backend reports 60 percent
- **THEN** the UI shows that it is pushing, the 40 files and 60 percent

### Requirement: Backup progress and result
A press SHALL start a backup and disable the button until it ends. Afterwards the UI SHALL show the result: success, committed without a remote, or the failure with its reason. A failure SHALL leave every view usable, and the button SHALL stay enabled for a retry.

#### Scenario: Successful backup
- **WHEN** the user presses the highlighted button and the backup succeeds
- **THEN** the button is quiet and the UI shows the time of this backup

#### Scenario: Push fails
- **WHEN** the user presses the button and the push fails
- **THEN** the UI shows the reason, the button stays highlighted and enabled, and the open view keeps working

#### Scenario: No remote
- **WHEN** the data repository has no remote and the user presses the button
- **THEN** the UI says the changes were committed and not pushed because no remote is set

### Requirement: Last successful backup shown
Next to the backup button, the UI SHALL show the time of the last successful backup, or that there has been none yet while changes are not backed up.

#### Scenario: No backup yet
- **WHEN** no backup has succeeded for this data repository and changes are not backed up
- **THEN** the UI says there has been no backup yet

#### Scenario: Nothing to back up and no backup yet
- **WHEN** no backup has succeeded for this data repository, it has a remote and nothing is waiting to be backed up
- **THEN** the UI says there is nothing to back up, not that there has been no backup, so the line does not contradict the quiet button

#### Scenario: No remote and no backup yet
- **WHEN** no backup has succeeded for this data repository, it has no remote and nothing is waiting to be backed up
- **THEN** the UI says that no remote is set and that there has been no backup yet, because nothing can have been pushed
