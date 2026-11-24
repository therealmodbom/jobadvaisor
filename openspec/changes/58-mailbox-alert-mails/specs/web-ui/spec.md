## MODIFIED Requirements

### Requirement: Intake view
The UI SHALL let the user submit a posting as a URL, pasted text, a PDF upload or a pasted job alert mail, or take postings from a check of the configured mailbox, and SHALL show the intake outcome, including the attempts made when intake fails or finds the posting closed. After a successful intake, it SHALL show the posting's title, company and location for correction. It SHALL show whether content screening is on, and for a flagged posting the flagged categories and a release action. It SHALL let the user view and edit the list of login-walled hosts, stored in the data repository.

#### Scenario: Edit the login-walled hosts
- **WHEN** the user adds a host to the login-walled list and saves
- **THEN** later intake of a URL on that host does not fetch it

#### Scenario: Release a flagged posting
- **WHEN** intake stores a posting flagged by the content guard and the user releases it
- **THEN** the stored posting is no longer excluded by the content guard

#### Scenario: Correct a field
- **WHEN** the user changes the company shown after intake and saves
- **THEN** the stored posting carries the corrected company

#### Scenario: Failed link
- **WHEN** intake of a URL fails after all attempts
- **THEN** the view lists the attempts and offers the text and PDF options

#### Scenario: Closed link
- **WHEN** intake of a URL ends with the posting closed
- **THEN** the view shows „Stelle geschlossen“ with the attempts, and offers no text or PDF option

#### Scenario: Mailbox source
- **WHEN** the user chooses the source „Postfach“
- **THEN** the view offers the mailbox check instead of an input field

## ADDED Requirements

### Requirement: Settings page
The header's settings button „Einstellungen“ SHALL open the settings page, reachable from every view. The page SHALL list its sections beside the content, and above it at a phone's width: „Scoren“ with the two settings of the pool's hint (threshold and rate), and „Postfach“ with the mailbox account and folders. Each section SHALL have its own address.

#### Scenario: Hint settings on the page
- **WHEN** the user opens „Einstellungen“ from the intake view, chooses „Scoren“, sets the threshold to 5 and saves
- **THEN** the pool's hint appears from 5 corrections on

#### Scenario: Section by address
- **WHEN** the user opens the address of the section „Postfach“
- **THEN** the settings page shows that section

#### Scenario: Phone width
- **WHEN** the settings page is shown 390 pixels wide
- **THEN** the sections are listed above the content, and the page does not scroll sideways

#### Scenario: Pool keys off
- **WHEN** the settings page is open and the user presses a rating key of the pool view
- **THEN** no posting is rated

### Requirement: Mailbox settings form
The section „Postfach“ SHALL offer the fields server, port (993 when empty), user name and password, and the action „Verbinden und Ordner laden“. That action SHALL store the account and, after a successful login, show the folder choice. A failed login SHALL show its reason beside the form.

#### Scenario: First connection
- **WHEN** the user enters server, user name and password and presses „Verbinden und Ordner laden“
- **THEN** the view says it is connected, names the number of folders and shows the folder choice

#### Scenario: Login refused
- **WHEN** the server refuses the login
- **THEN** the view says that the login was refused, and the fields keep their values except the password

### Requirement: Password field
The password field SHALL mask its text, and a button with an eye icon SHALL show and hide the typed text. A stored password SHALL show as eight dots, labelled as stored, and SHALL never be filled in; an empty field SHALL keep the stored password on save while server, port and user name stay the same. The section SHALL recommend an app password that the provider can revoke on its own.

#### Scenario: Show the typed password
- **WHEN** the user types a password and presses the eye button
- **THEN** the typed text is readable, and a second press masks it again

#### Scenario: Stored password kept
- **WHEN** a password is stored and the user changes only the folder choice and saves
- **THEN** the stored password stays, and the field still shows eight dots

#### Scenario: Server changed
- **WHEN** a password is stored and the user changes the server without entering a password and saves
- **THEN** the field is empty, no longer labelled as stored, and asks for the password

### Requirement: Mailbox settings without a key
When no key for the password is configured, the password field and „Verbinden und Ordner laden“ SHALL be disabled. A visible info icon that keyboard users can reach SHALL say that no key is configured and that the README explains how to set one up.

#### Scenario: No key
- **WHEN** the backend has no key configured and the user opens the section „Postfach“
- **THEN** the password field is disabled, and the info icon beside it gives the reason

### Requirement: Folder choice
After connecting, the section SHALL offer „Alle Ordner“, which includes folders created later and leaves out system folders, or „Nur diese Ordner“ with a checkbox per folder, system folders marked and unticked at first. Above the choice, the hint „Wähle nur Ordner, in denen ausschließlich Job-Alert-Mails liegen.“ SHALL stand. Saving SHALL store the choice.

#### Scenario: Selection
- **WHEN** the user chooses „Nur diese Ordner“, ticks „Posteingang“ and „Jobs“ and saves
- **THEN** checks search those two folders only

#### Scenario: Folder hint
- **WHEN** the section shows the folder choice
- **THEN** the hint to choose only folders holding job alert mails stands above it

### Requirement: Mails per check setting
The section „Postfach“ SHALL offer „Höchstens Mails pro Prüfung“, a whole number from 1 to 1000, preset to 200. Saving SHALL store it, and the next check SHALL use it. A value outside that range SHALL be refused with a message beside the field.

#### Scenario: Limit set
- **WHEN** the user sets „Höchstens Mails pro Prüfung“ to 50 and saves
- **THEN** the next check reads at most 50 mails

#### Scenario: Limit out of range
- **WHEN** the user enters 5000 and saves
- **THEN** nothing is stored, and the field says that the number must be from 1 to 1000

### Requirement: Mailbox source
The intake source „Postfach“ SHALL point to the section „Postfach“ while no mailbox is configured. Once one is, it SHALL show the account, the folder choice and the time of the last check, and „Postfach prüfen“. Before the first check it SHALL show „Mails ab“, a date preset to 30 days back, with a hint that older mails are never read and that each mail from a sender without a fixed rule costs a model call.

#### Scenario: Not configured
- **WHEN** no mailbox is configured and the user chooses the source „Postfach“
- **THEN** the view says so and links to the section „Postfach“ of the settings page

#### Scenario: First check
- **WHEN** a mailbox is configured but never checked
- **THEN** the view shows „Mails ab“ preset to 30 days back with the cost hint, and „Postfach prüfen“

#### Scenario: Later checks
- **WHEN** the mailbox was checked before
- **THEN** the view shows no „Mails ab“ field, only the time of the last check and „Postfach prüfen“

### Requirement: Mailbox check progress and outcome
While a check runs, the view SHALL show how many new mails it found and how many it has read, and „Postfach prüfen“ SHALL be disabled. A check without new mails SHALL say so. A failed check SHALL show its reason with „Erneut versuchen“ and a link to the settings. A stored password the key cannot decrypt SHALL be named, with a link to enter it again. Switching away and reloading the page SHALL keep a running check's progress.

#### Scenario: Progress
- **WHEN** a check found 12 new mails and has read 5
- **THEN** the view shows 12 found and 5 read, and „Postfach prüfen“ is disabled

#### Scenario: Nothing new
- **WHEN** a check finds no unhandled mail
- **THEN** the view says that there are no new mails since the start date

#### Scenario: Server not reachable
- **WHEN** a check ends because the server did not answer
- **THEN** the view says the server is not reachable, and offers „Erneut versuchen“ and the settings

### Requirement: Cancel button of a mailbox check
While a check runs, the view SHALL offer „Prüfen abbrechen“, which cancels the check at once and without a confirm step. The view SHALL say that the check stops after the current mail and that the mails read so far stay in the pick list. When the cancelled check has stopped, the view SHALL show its pick list and report, with a note that it was cancelled after N of M mails.

#### Scenario: Cancel a check
- **WHEN** the user presses „Prüfen abbrechen“ after the check has read 37 of 200 mails
- **THEN** the check stops after the current mail, and the view shows the pick list of the mails read with the note that the check was cancelled after 37 of 200 mails

### Requirement: Mailbox pick list grouped by mail
A finished check SHALL show the entries of all its mails in one list, grouped by mail, with the rules of the alert mail pick list for each entry. Each mail head SHALL show the sender, and the subject, date and folder in one line below it, stacked at a phone's width. „N Anzeigen hinzufügen“ SHALL add all selected entries, and „Nichts hinzufügen“ none; the view SHALL say that the mails count as handled afterwards.

#### Scenario: Three mails
- **WHEN** a check read three mails with seven entries, one already stored
- **THEN** the list shows three mail heads with their entries, six of them selected, and „6 Anzeigen hinzufügen“

#### Scenario: Nothing added
- **WHEN** the user presses „Nichts hinzufügen“
- **THEN** no entry is added, and the mails of the check are not offered again

### Requirement: Oversized mail in the pick list
A mail the check did not read because it is too large SHALL appear in the pick list as its own mail head with sender, subject, date and folder, the note „Zu groß, nicht gelesen“ and a checkbox that is not ticked. Ticking it SHALL read the mail, show that it is being read, and then show its entries below the head like those of any other mail. A failed reading SHALL show its reason at the head and leave the checkbox unticked.

#### Scenario: Oversized mail ticked
- **WHEN** the user ticks the checkbox of an oversized mail
- **THEN** the view shows that the mail is being read, and then its entries appear below the head

#### Scenario: Oversized mail not ticked
- **WHEN** the user presses „N Anzeigen hinzufügen“ without ticking an oversized mail
- **THEN** no entry of that mail is added, and the mail is not offered again

### Requirement: Mailbox check report
Above the pick list, the view SHALL name, each as a short note: the number of mails left for the next check, chosen folders that no longer exist, mails whose reading failed, mails held by the content guard, mails not read while screening is off, and an interrupted connection. A mail head SHALL carry the notes of the pasted alert mail for that mail (hosts not read, more than 100 entries).

#### Scenario: Mails left
- **WHEN** a check read 200 mails and 60 remain
- **THEN** a note says that 60 mails are left for the next check

#### Scenario: Failed and held mails
- **WHEN** a check could not read one mail and the content guard held another
- **THEN** a note names each with its sender and subject, and neither appears in the pick list

### Requirement: Mailbox pick list kept when adding is refused
When finishing a check's pick list is refused because another alert run computes, the view SHALL show that run's progress and keep the pick list, so it can be finished afterwards.

#### Scenario: Alert run busy
- **WHEN** the user adds entries while another alert run computes
- **THEN** the view shows the computing run's progress, and the pick list can be finished afterwards

### Requirement: Select a mail's entries at once
Each mail head SHALL have a checkbox that selects all selectable entries of that mail when not all are selected, and clears them otherwise. It SHALL show a dash while only some are selected. The head SHALL show „n von m ausgewählt“ for its mail.

#### Scenario: Clear a mail
- **WHEN** all three selectable entries of a mail are selected and the user clears the mail's checkbox
- **THEN** none of them is selected, the head shows „0 von 3 ausgewählt“, and the add button counts three fewer

#### Scenario: Some selected
- **WHEN** one of a mail's two entries is selected
- **THEN** the mail's checkbox shows a dash

### Requirement: Collapse a mail
Each mail head SHALL have a button that collapses and expands the mail's entries. A collapsed mail SHALL keep its selection and keep showing its head with „n von m ausgewählt“.

#### Scenario: Collapse
- **WHEN** the user collapses a mail with two of three entries selected
- **THEN** its entries are hidden, its head shows „2 von 3 ausgewählt“, and the add button still counts them

## REMOVED Requirements

### Requirement: Settings in the header
**Reason**: The settings button now opens the settings page instead of a panel.
**Migration**: The two settings of the pool's hint are in the section „Scoren“ of the settings page (requirement „Settings page“).
