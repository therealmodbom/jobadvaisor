# Spec Delta

## ADDED Requirements

### Requirement: Backup button on every view
Every view SHALL show a backup button. It SHALL be highlighted while the backend reports something not backed up yet, and quiet otherwise. The UI SHALL fetch the backup status when the page loads, when the tab becomes visible, after each backup, and every 15 seconds while the tab is visible.

#### Scenario: After a rating
- **WHEN** the user rates a posting after a successful backup
- **THEN** the button is highlighted within 15 seconds

#### Scenario: Change made outside the app
- **WHEN** a file in the data repository is changed by hand while the tab is open
- **THEN** the button is highlighted within 15 seconds

#### Scenario: Nothing pending
- **WHEN** the backend reports nothing pending
- **THEN** the button is shown without the highlight

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
Next to the backup button, the UI SHALL show the time of the last successful backup, or that there has been none yet.

#### Scenario: No backup yet
- **WHEN** no backup has succeeded on this installation
- **THEN** the UI says there has been no backup yet
