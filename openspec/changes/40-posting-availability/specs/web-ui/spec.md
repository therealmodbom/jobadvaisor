# Spec Delta

## ADDED Requirements

### Requirement: Availability check in the pool view
The pool view SHALL offer „Verfügbarkeit prüfen“, naming how many postings the check will fetch. While a check runs, the view SHALL show how many of them are done and SHALL NOT offer a second start. When the check ends, the view SHALL load the pool again and show the report: the counts of available, closed and unknown postings, and each posting found closed with a link to its page.

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
The pool view SHALL offer the state filter „Geschlossen“, listing the closed postings with application status open. The filters „Offen“, „Noch nicht bewertet“ and „Bewertet“ SHALL NOT list closed postings. Wherever the view lists a closed posting, its row SHALL mark it as closed, and the user SHALL be able to rate it from the row.

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

### Requirement: Closed outcome at intake
The intake view and the alert mail run SHALL show a submitted link whose page is closed as „Stelle geschlossen“, apart from a failed link, with its attempts. They SHALL NOT offer the text and PDF options for it.

#### Scenario: Expired link submitted
- **WHEN** the user submits a link whose page is closed
- **THEN** the view shows „Stelle geschlossen“ with the attempts, and no text or PDF option
