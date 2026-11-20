# Spec Delta

## ADDED Requirements

### Requirement: Availability check button
The pool view SHALL offer „Verfügbarkeit prüfen“, naming how many postings the check will cover. When it covers none, the button SHALL be disabled, with a visible, focusable info icon that says why.

#### Scenario: Nothing to check
- **WHEN** every open posting is closed, set by hand or has no link
- **THEN** the button is disabled, and its info icon says there is nothing to check

### Requirement: Availability check progress and report
While a check runs, the pool view SHALL show how many of its postings are done and SHALL NOT offer a second start. When the check ends, the view SHALL load the pool again and show the report: the counts of available, closed and unknown postings, and each posting found closed with a link to its page.

#### Scenario: Check from the pool
- **WHEN** the user presses „Verfügbarkeit prüfen“ and the check finds 2 postings closed
- **THEN** the view shows the progress, then the report with 2 closed and both postings linked, and the two are no longer listed under „Offen“

#### Scenario: Unknown postings named in the report
- **WHEN** 4 postings of a check answer HTTP 429
- **THEN** the report counts 4 unknown, and those postings stay listed

### Requirement: Availability check refused or lost
When a check is refused because another one runs, the view SHALL show that check's progress. Switching to another view and back, and reloading the page, SHALL keep the check and its report while the server still knows the check. When the server no longer knows it, because it restarted, the view SHALL say so and offer „Verfügbarkeit prüfen“ again.

#### Scenario: Reload during a check
- **WHEN** the user reloads the pool view while a check runs
- **THEN** the view shows the running check's progress

#### Scenario: Server restarted
- **WHEN** the server restarted during a check
- **THEN** the view says the check is no longer known and offers to start a new one

### Requirement: Filter Geschlossen
The pool view SHALL offer the state filter „Geschlossen“, listing the closed postings with application status open. The filters „Offen“, „Noch nicht bewertet“ and „Bewertet“ SHALL NOT list closed postings.

#### Scenario: Closed posting moves to its filter
- **WHEN** a check closes an unrated posting
- **THEN** „Noch nicht bewertet“ no longer lists it, and „Geschlossen“ does

### Requirement: Closed mark on a row
Wherever the pool view lists a closed posting, its row SHALL mark it as closed, and the user SHALL be able to rate it from the row.

#### Scenario: Rate a closed posting from its filter
- **WHEN** the user picks „Geschlossen“ and rates a listed posting
- **THEN** the rating is stored and the row shows it, still marked as closed

#### Scenario: Closed posting under Herkunft
- **WHEN** an imported posting is closed and the user picks „Herkunft“
- **THEN** its row is listed and marked as closed

### Requirement: Availability on the posting page
The posting page SHALL show the posting's availability with the time it was set and whether a check or the user set it, or that it was never checked. It SHALL let the user set it to closed or to available by hand.

#### Scenario: Close by hand
- **WHEN** the user sets an open posting to closed on its page
- **THEN** the page shows it as closed, set by hand, and the pool lists it only under „Geschlossen“

#### Scenario: Reopen by hand
- **WHEN** the user sets a closed posting to available on its page
- **THEN** the page shows it as available, set by hand, and later checks leave it as it is

## MODIFIED Requirements

### Requirement: Intake view
The UI SHALL let the user submit a posting as a URL, pasted text, a PDF upload or a pasted job alert mail, and SHALL show the intake outcome, including the attempts made when intake fails or finds the posting closed. After a successful intake, it SHALL show the posting's title, company and location for correction. It SHALL show whether content screening is on, and for a flagged posting the flagged categories and a release action. It SHALL let the user view and edit the list of login-walled hosts, stored in the data repository.

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

### Requirement: Several links at once
The intake view SHALL accept several URLs at once, one per line, and SHALL show the outcome of each: stored, duplicate of a stored posting, closed with its attempts, or failed with its attempts. A failed or closed URL SHALL NOT stop the others.

#### Scenario: Three links
- **WHEN** the user submits three URLs and the second cannot be read
- **THEN** the first and third are stored, and the view lists the second with its attempts and the text and PDF options

#### Scenario: A closed link among several
- **WHEN** the user submits two URLs and the first ends closed
- **THEN** the view lists the first as „Stelle geschlossen“ with its attempts, and the second with its own outcome

### Requirement: Alert mail run progress and outcome
While the chosen entries are added, the view SHALL show for each entry whether it waits, is being added, was stored, is a duplicate, is closed or failed, and how many entries are done. A failed entry SHALL show its attempts or its reason, and SHALL offer the text and PDF options. A closed entry SHALL show „Stelle geschlossen“ with its attempts. Switching to another source or view and back, and reloading the page, SHALL keep the run and its report while the server still knows the run.

#### Scenario: Second of three fails
- **WHEN** the user adds three entries and the second cannot be read
- **THEN** the view shows the first and third as stored with a link to each posting, and the second with its attempts and the text and PDF options

#### Scenario: Switching away and reloading
- **WHEN** the user switches to the link source during a run, comes back, and then reloads the page
- **THEN** the view still shows the run's progress, or its report once the run ended

#### Scenario: Closed entry
- **WHEN** an added entry ends closed
- **THEN** the view shows it as „Stelle geschlossen“ with its attempts, and counts it as done
