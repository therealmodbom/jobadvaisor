# Spec Delta

## MODIFIED Requirements

### Requirement: Local single-user access
The UI SHALL be served on localhost for a single user, without accounts or login.

#### Scenario: Open the app
- **WHEN** the user opens the local address in a browser
- **THEN** the intake and pool views are available without a login

### Requirement: Fast rating from the keyboard
Rating SHALL be the quickest path in the UI. The user SHALL be able to give a verdict, toggle reason chips and move to the next posting from the keyboard, and the shortcuts SHALL be shown in the view. A chip's shortcut SHALL give the verdict when none was given, and SHALL NOT change a verdict already given.

#### Scenario: Rate a batch without the mouse
- **WHEN** the user rates every listed unrated posting using only the keyboard
- **THEN** each rating is stored, the posting stays open with its reasons in focus after the verdict, and Enter moves focus to the next unrated posting

#### Scenario: Typing a note
- **WHEN** the user types text containing shortcut keys into a note or any other text field
- **THEN** the text is entered as typed and no rating, chip toggle or navigation happens

#### Scenario: Chip gives the verdict
- **WHEN** the user toggles a positive chip on a posting without a verdict, by mouse or by keyboard
- **THEN** the verdict is positive, and chips of both polarities remain selectable

#### Scenario: Explicit verdict wins
- **WHEN** the user rated a posting negative and then toggles a positive chip
- **THEN** the verdict stays negative

### Requirement: Visible state at every step
Every action that waits on the backend SHALL show that it is in progress. Every failure SHALL show a plain-language message with a way to retry. Every empty view SHALL say what to do next.

#### Scenario: Waiting on intake
- **WHEN** an intake is running
- **THEN** the view shows progress and does not accept a second submission of the same input

#### Scenario: Backend error
- **WHEN** a request to the backend fails
- **THEN** the view shows what failed and offers a retry, and no input is lost

#### Scenario: No run yet
- **WHEN** the user opens the pool before any posting is stored
- **THEN** the view explains how to add postings

## REMOVED Requirements

### Requirement: Feedback list
**Reason**: The pool replaces the list of one run's postings, and the run leaves the UI.
**Migration**: See "Pool view" and "Posting page" here.

## ADDED Requirements

### Requirement: Pool view
The UI SHALL show the pool ranked by fit, with the text filter and the state filters, each row showing title, company, score, the user's rating, application status and, where it applies, the exploration mark or the import origin. The user SHALL be able to rate a posting, change a rating and set the application status from the list. The view SHALL show the button "Neue Anzeigen bewerten" with the number of postings it will score, the correction counter, the share of corrections, the hint of the pool and the two settings (threshold and rate), and SHALL show a pass's progress. It SHALL name no run.

#### Scenario: Rate from the pool
- **WHEN** the user rates a posting in the list
- **THEN** the rating is stored and the posting shows as rated, with the counter updated

#### Scenario: Start a pass
- **WHEN** the user presses "Neue Anzeigen bewerten"
- **THEN** the view shows progress, and the new scores appear in the ranking when the pass ends

#### Scenario: Unscreened postings in a pass
- **WHEN** a pass pauses because it holds postings the content guard never checked
- **THEN** the view names those postings and offers to continue with them or abort the pass

#### Scenario: Change the hint settings
- **WHEN** the user sets the threshold to 5 and saves
- **THEN** the hint appears from 5 corrections on

### Requirement: Posting page
The UI SHALL give each posting its own address (hash route `#/anzeigen/<id>`), and a posting the agent names in a chat answer SHALL link to it. The page SHALL show the full text, the original link, the score with its reasoning, the rating with chips and note, the application status and the import origin, and SHALL allow rating and setting the status. It SHALL also let the user correct the title, company and location behind "Bearbeiten", for postings whose fields intake read wrongly.

#### Scenario: Correct a posting's fields
- **WHEN** the user opens "Bearbeiten" on a posting page, changes the company and saves
- **THEN** the page shows the new company, and the pool lists the posting under it

#### Scenario: Link from the chat
- **WHEN** the agent names a stored posting in an answer
- **THEN** the chat shows a link to that posting's page

### Requirement: Import view
The UI SHALL offer the import as the source "Liste" of the view for adding postings, next to link, text and PDF, not as a separate entry of the main navigation, and SHALL keep a running import and its report when the user switches to another source or view. It SHALL let the user upload a job list file and SHALL then show the entry tables found and the import mapping as a form: the status column, a choice of "offen", "beworben", "erledigt" or "überspringen" for each of its values, and an optional assessment column, prefilled from the stored mapping. The form SHALL mark each table that lacks the chosen status column as not imported, SHALL mark each status value the stored mapping does not name as new, and SHALL warn when no status column is chosen although the stored mapping names one, since every table with links is then imported with every entry open. Confirming the form stores the mapping and starts the import. The UI SHALL show the import's progress while it runs and, when it ends, the report: the counts (imported, duplicate, skipped by status, skipped as link gone, failed), every entry not imported with its row text, link and reason, each table left out for lacking the status column with its number of entries, and each already stored posting whose application status differs from the list's, with its title, company and both statuses, letting the user take the list's status or keep the app's. The import SHALL NOT be started or inspected by any means other than the UI.

#### Scenario: Upload a list
- **WHEN** the user uploads a list with 20 entries and confirms the mapping
- **THEN** the view shows progress, and at the end the counts per outcome, which add up to 20, and lists the entries that were not imported

#### Scenario: Mapping remembered
- **WHEN** the user uploads a list again after an earlier import
- **THEN** the form shows the mapping stored by the earlier import

#### Scenario: New status value
- **WHEN** the list holds a status value the stored mapping does not name
- **THEN** the form marks that value as new, with "offen" chosen until the user picks another

#### Scenario: Table without the status column
- **WHEN** one table of the list lacks the chosen status column
- **THEN** the form marks it as not imported, and the report names it with its number of entries

#### Scenario: Upload again after an interruption
- **WHEN** the application restarted during an import and the user uploads the same file again
- **THEN** entries already stored count as duplicates and the rest is imported

#### Scenario: Status differs from the list
- **WHEN** the list says "beworben" for a stored posting whose status in the app is open
- **THEN** the report lists that posting with "App: offen · Liste: beworben", and taking the list's status stores "beworben" while keeping the app's changes nothing

### Requirement: Several links at once
The intake view SHALL accept several URLs at once, one per line, and SHALL show the outcome of each: stored, duplicate of a stored posting, or failed with its attempts. A failed URL SHALL NOT stop the others.

#### Scenario: Three links
- **WHEN** the user submits three URLs and the second cannot be read
- **THEN** the first and third are stored, and the view lists the second with its attempts and the text and PDF options
