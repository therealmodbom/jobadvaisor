## MODIFIED Requirements

### Requirement: Note on handled mails below the pick list
Below the mailbox pick list, the view SHALL say that every mail of the pick list counts as handled once its entries are being added, that a mail from which nothing is added counts as handled at once, and that links that cannot be read are kept under „Offene Links“ instead of bringing their mail back.

#### Scenario: Note below the pick list
- **WHEN** a check ends with a pick list
- **THEN** the note below it says that its mails count as handled once their entries are being added, and that links that cannot be read are kept under „Offene Links“

## REMOVED Requirements

### Requirement: Mails offered again after a mailbox run
**Reason**: A mail of a mailbox run now counts as handled once its entries went into the run, so the next check no longer offers it again.
**Migration**: „Unsettled links named after a run“ points to „Offene Links“, where those links are kept.

## ADDED Requirements

### Requirement: Unsettled links named after a run
When a run, from a mailbox check or a pasted mail, ends with entries not read, not judgeable or not reached, ends crashed, or is no longer known to the server, its report SHALL say that those links are kept under „Offene Links“ and SHALL link there. The report of a mailbox run SHALL NOT say that the next check offers its mails again.

#### Scenario: Failed entries after a mailbox run
- **WHEN** a mailbox run ends with three entries failed
- **THEN** the report says that their links are kept under „Offene Links“, links there, and does not say that the next check offers their mails again

#### Scenario: Mailbox run no longer known
- **WHEN** the server restarted during a mailbox run
- **THEN** the view says the run is no longer known and that the links not added are kept under „Offene Links“

#### Scenario: Pasted run with a failed entry
- **WHEN** a run of a pasted mail ends with one entry failed
- **THEN** the report says that its link is kept under „Offene Links“

### Requirement: Unsettled links tab
„Anzeige hinzufügen“ SHALL offer the source „Offene Links“ next to „Postfach“. It SHALL list the unsettled links, each with its title, its link (opening in a new tab), its outcome („Wartet“, „Nicht gelesen“, „Nicht beurteilbar“ or „Nicht erreicht“), its source („Postfach“ or „Alert-Mail“), its number of tries, the date it entered the list and when it was last tried. The attempts of a row SHALL sit behind „Details“, like those of a run row.

#### Scenario: List after a run
- **WHEN** a mailbox run has ended with two entries not read and one not judgeable, and the user opens „Offene Links“
- **THEN** the tab lists the three links with title, outcome, source „Postfach“, one try and the time of that try

#### Scenario: Another device
- **WHEN** the user opens „Offene Links“ on another device after the run
- **THEN** it lists the same links

### Requirement: Unsettled links tab address and empty states
The tab „Offene Links“ SHALL have its own address, so a reload and the link of a run report open it. Without unsettled links, it SHALL say that no link is open. When the list cannot be read, it SHALL say so and name the file.

#### Scenario: Empty list
- **WHEN** no link is open and the user opens „Offene Links“
- **THEN** the tab says that no link is open

#### Scenario: Reload on the tab
- **WHEN** the user reloads the app while „Offene Links“ is open
- **THEN** „Offene Links“ is open again

#### Scenario: Unreadable list
- **WHEN** the list file in the data repository is invalid and the user opens „Offene Links“
- **THEN** the tab says that the list cannot be read and names the file, and no badge shows

### Requirement: Count of unsettled links
The source tab „Offene Links“ and the navigation item „Anzeige hinzufügen“ SHALL each show the number of unsettled links as a badge, and no badge while the list is empty. The number SHALL be part of the accessible name of the tab and the navigation item. It SHALL be read when the app loads and when the tab is opened, and again when a run starts, each time it ends an entry, when it ends, and after a link was removed.

#### Scenario: Open links after a run
- **WHEN** a run has ended with 12 links unsettled and the list was empty before
- **THEN** the navigation item „Anzeige hinzufügen“ and the tab „Offene Links“ show a badge with 12, and a screen reader announces the number with each name

#### Scenario: No open link
- **WHEN** the list of unsettled links is empty
- **THEN** neither the navigation item nor the tab shows a badge

#### Scenario: Reload
- **WHEN** the user reloads the app with five links open
- **THEN** both badges show 5

### Requirement: Remove an unsettled link
Each row of „Offene Links“ SHALL offer „Entfernen“, which removes the link at once and without a confirm step, since no posting or mail changes. The view SHALL announce the removal, update the count and move the focus to the next row, or to the list's heading after the last one. While the computing run has not yet ended a link, its row SHALL offer no „Entfernen“, and SHALL say why.

#### Scenario: Remove a link
- **WHEN** the user presses „Entfernen“ on one of three rows
- **THEN** that row disappears, the view announces the removal, both badges show 2, and the focus is on the next row

#### Scenario: Link still in the run
- **WHEN** a run computes and the user opens „Offene Links“
- **THEN** the rows of the links still waiting in that run offer no „Entfernen“ and say that the link is still in the run
