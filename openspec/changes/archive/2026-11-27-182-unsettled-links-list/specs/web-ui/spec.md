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
„Anzeige hinzufügen“ SHALL offer the source „Offene Links“ next to „Postfach“. It SHALL list the unsettled links in rows of neutral colour, with only the outcome word in colour, unlike the red rows of failed entries in the run view.

#### Scenario: List after a run
- **WHEN** a mailbox run has ended with two entries not read and one not judgeable, and the user opens „Offene Links“
- **THEN** the tab lists the three links with outcome, title, source „Postfach“, „in 1 Lauf abgerufen“ and the time of that try, in rows without a red background

#### Scenario: Another device
- **WHEN** the user opens „Offene Links“ on another device after the run
- **THEN** it lists the same links

### Requirement: Row of an unsettled link
A row SHALL show its outcome („Wartet“, „Nicht gelesen“, „Nicht beurteilbar“ or „Nicht gestartet“, the run view's word for a link a run did not reach), its title, its link (opening in a new tab), its source („Postfach“ or „Alert-Mail“), in how many runs it was fetched („in 2 Läufen abgerufen“), the date it entered the list and when it was last tried. The attempts of its last try SHALL sit behind „Details: n Versuche“, like those of a run row.

#### Scenario: Link not reached
- **WHEN** a run was cancelled before it reached a link that was not in the list before
- **THEN** its row shows „Nicht gestartet“, „noch in keinem Lauf abgerufen“ and that the run ended before it reached the link

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
The source tab „Offene Links“ and the navigation item „Anzeige hinzufügen“ SHALL each show, as a badge, the number of unsettled links that need attention: every link of the list except those a computing run still has to fetch. At 0 there SHALL be no badge. The number SHALL be part of the accessible name of both. It SHALL be read when the app loads and when the tab is opened, and again when a run starts, each time it ends an entry, when it ends, after a link was removed, and every few seconds while an alert run computes.

#### Scenario: Open links after a run
- **WHEN** a run has ended with 12 links unsettled and the list was empty before
- **THEN** the navigation item „Anzeige hinzufügen“ and the tab „Offene Links“ show a badge with 12, and a screen reader announces the number with each name

#### Scenario: Waiting links not counted
- **WHEN** a mailbox run over 100 links starts and the list was empty before
- **THEN** no badge shows, and each link that ends not read or not judgeable raises both badges by one

#### Scenario: No open link
- **WHEN** the list of unsettled links is empty
- **THEN** neither the navigation item nor the tab shows a badge

#### Scenario: Reload
- **WHEN** the user reloads the app with five links open
- **THEN** both badges show 5

#### Scenario: Run of another device ends
- **WHEN** the user opens „Offene Links“ while a run started on another device computes, and that run ends
- **THEN** within a few seconds the retry buttons and „Entfernen“ are enabled again and both badges count the links that need attention, without a reload

### Requirement: Remove an unsettled link
Each row of „Offene Links“ SHALL offer „Entfernen“, which removes the link at once and without a confirm step, since no posting or mail changes. The view SHALL announce the removal, update the count and move the focus to the next row, or to the list's heading after the last one. While the computing run has not yet ended a link, its „Entfernen“ SHALL be disabled, with an info icon beside it that says why.

#### Scenario: Remove a link
- **WHEN** the user presses „Entfernen“ on one of three rows
- **THEN** that row disappears, the view announces the removal, both badges show 2, and the focus is on the next row

#### Scenario: Link still in the run
- **WHEN** a run computes and the user opens „Offene Links“
- **THEN** the rows of the links still waiting in that run show „Entfernen“ disabled, and their info icon says that the run still has to fetch the link

### Requirement: Try unsettled links again
„Offene Links“ SHALL offer „Alle erneut versuchen (n)“ in its head, the only filled button of the view, and „Erneut versuchen“ in each row. Either SHALL start one alert run with those links at once, without a confirm step, and the tab SHALL then show that run in the run view, with „Zurück zu den offenen Links“ once it has ended. While an alert run computes, both SHALL be disabled, each with an info icon that says why.

#### Scenario: Try all again
- **WHEN** the list holds five links and the user presses „Alle erneut versuchen (5)“
- **THEN** a run of the five links starts, and the tab shows its progress with „Lauf abbrechen“

#### Scenario: Back to the list
- **WHEN** that run has stored one link and the user presses „Zurück zu den offenen Links“
- **THEN** the tab lists the four others, each with one more run in „in n Läufen abgerufen“

#### Scenario: Retry refused
- **WHEN** another run started on another device after the list was read, and the user presses „Erneut versuchen“
- **THEN** no run starts, and the tab shows the computing run's progress

#### Scenario: Retry while a run computes
- **WHEN** a mailbox run computes and the user opens „Offene Links“
- **THEN** „Alle erneut versuchen“ and every „Erneut versuchen“ are disabled, and their info icon says that a run is computing

#### Scenario: Phone
- **WHEN** the user opens „Offene Links“ at a phone's width
- **THEN** „Alle erneut versuchen“ spans the width below the head text, and each row's „Erneut versuchen“ and „Entfernen“ stack below its text at full width
