# Spec Delta

## ADDED Requirements

### Requirement: Availability check button
The pool view SHALL offer „Verfügbarkeit prüfen“ beside the pass button, naming how many postings the check will cover. When it covers none, the button SHALL be disabled, with a visible, focusable info icon that says why.

#### Scenario: Nothing to check
- **WHEN** no open posting has a link the check can fetch
- **THEN** the button is disabled, and its info icon says there is nothing to check

### Requirement: Availability check progress and report
While a check runs, the pool view SHALL show below its button how many of its postings are done, and SHALL NOT offer a second start. When the check ends, the view SHALL load the pool again and show the report in the same place: how many postings it found closed, available and unknown, and each posting it newly closed with a link to its page. The report SHALL list the first three closed postings and the rest behind a toggle, and the user SHALL be able to dismiss it.

#### Scenario: Check from the pool
- **WHEN** the user presses „Verfügbarkeit prüfen“ and the check finds 2 postings closed
- **THEN** the view shows the progress, then the report with 2 closed and both postings linked, and the two are no longer listed under „Offen“

#### Scenario: Unknown postings named in the report
- **WHEN** 4 postings of a check answer HTTP 429
- **THEN** the report counts 4 unknown, and those postings stay listed

#### Scenario: Many closed postings
- **WHEN** a check finds 5 postings closed
- **THEN** the report links the first three and offers the other two behind „2 weitere anzeigen“

### Requirement: Cancel button of a check
While a check runs, „Verfügbarkeit prüfen“ SHALL give way to „Prüfen abbrechen“, which cancels the check at once and without a confirm step. The view SHALL say that the check stops after the current posting and that what it already found stays stored. When the cancelled check has stopped, the view SHALL show its report with what it found so far, and say it was cancelled.

#### Scenario: Cancel a check
- **WHEN** the user presses „Prüfen abbrechen“ after the check found 2 of its postings closed
- **THEN** the check stops after the current posting, the 2 stay closed, and the report says the check was cancelled and lists the 2

### Requirement: Availability check refused or lost
When a check is refused because another one runs, the view SHALL show that check's progress. Switching to another view and back, and reloading the page, SHALL keep the check and its report while the server still knows the check. When the server no longer knows it, because it restarted, the view SHALL say so and offer „Verfügbarkeit prüfen“ again.

#### Scenario: Reload during a check
- **WHEN** the user reloads the pool view while a check runs
- **THEN** the view shows the running check's progress

#### Scenario: Server restarted
- **WHEN** the server restarted during a check
- **THEN** the view says the check is no longer known and offers to start a new one

### Requirement: Filter Stelle geschlossen
The pool view SHALL offer the state filter „Stelle geschlossen“, listing the closed postings with application status open. The filters „Offen“, „Noch nicht bewertet“ and „Bewertet“ SHALL NOT list closed postings.

#### Scenario: Closed posting moves to its filter
- **WHEN** a check closes an unrated posting
- **THEN** „Noch nicht bewertet“ no longer lists it, and „Stelle geschlossen“ does

### Requirement: Closed mark on a row
Wherever the pool view lists a closed posting, its row SHALL carry the mark „Stelle geschlossen“, and the user SHALL be able to rate it from the row.

#### Scenario: Rate a closed posting from its filter
- **WHEN** the user picks „Stelle geschlossen“ and rates a listed posting
- **THEN** the rating is stored and the row shows it, still marked as closed

#### Scenario: Closed posting under Herkunft
- **WHEN** an imported posting is closed and the user picks „Herkunft“
- **THEN** its row is listed and marked as closed

### Requirement: Posting without a link on its page
A posting without a link, added as pasted text or a PDF, is never checked. The note below its availability on the posting page SHALL say so and SHALL NOT promise a next check, also after a hand setting.

#### Scenario: Posting without a link
- **WHEN** the user opens a posting added as pasted text and sets it to closed
- **THEN** the note says it was set by hand and promises no check

### Requirement: Availability on the posting page
The posting page SHALL show the posting's availability under the title, beside „Bearbeiten“ and the application status, as a field the user can set to closed or to available. Below it the page SHALL say when the availability was set and whether a check or the user set it, or that it was never checked. For a hand setting, the note SHALL say that the next check replaces it.

#### Scenario: Close by hand
- **WHEN** the user sets an open posting to closed on its page
- **THEN** the page shows it as closed, set by hand, and the pool lists it only under „Stelle geschlossen“

#### Scenario: Reopen by hand
- **WHEN** the user sets a closed posting to available on its page
- **THEN** the page shows it as available, set by hand, with the note that the next check replaces it

### Requirement: Settings in the header
The app header SHALL offer a settings button with the accessible name „Einstellungen“. It SHALL open a panel with the two settings of the pool's hint (threshold and rate), which closes with Escape, and SHALL be reachable from every view.

#### Scenario: Settings from another view
- **WHEN** the user is on the intake view and opens „Einstellungen“ in the header
- **THEN** the panel shows the threshold and the rate, and saving them changes the pool's hint

### Requirement: Result of a finished pass
When a pass has finished, the pool view SHALL say below the pass button, where its progress was, that the pass is done and how many postings it scored, like the report of a finished check. The notice SHALL stay, also over a reload, until the user dismisses it or the next pass starts.

#### Scenario: Pass finished
- **WHEN** a pass finishes after scoring 12 postings
- **THEN** the view says the pass is done with 12 postings scored, and the notice goes once the user dismisses it

### Requirement: Counter line below the pass button
Directly below the pass button the pool view SHALL show one line with the correction counter, the hint of the pool, and the share of corrections or how many ratings the share still needs. How many postings each pass variant scores and at how many model calls SHALL be said only in the pass button's menu.

#### Scenario: Counter below the button
- **WHEN** the pool has 3 corrections and 7 ratings
- **THEN** the line below the pass button reads „3 Korrekturen · Ranking passt gut · Anteil ab 10 Bewertungen (bisher 7)“

### Requirement: Labels for application status and availability
Wherever the UI shows the application status, it SHALL label it „Bewerbungsstatus“, and a closed posting SHALL read „Stelle geschlossen“, so the two states are not mistaken for one another. On the posting page, „Bearbeiten“, the application status and the availability SHALL sit in one row under the title.

#### Scenario: Closed but status open
- **WHEN** a closed posting with application status open is listed
- **THEN** its row shows „Stelle geschlossen“ and the field „Bewerbungsstatus“ reading „offen“

## MODIFIED Requirements

### Requirement: Pool view
The UI SHALL show the pool ranked by fit, with the text filter and the state filters, each row showing title, company, score, the user's rating, application status and, where it applies, the exploration mark or the import origin. The user SHALL be able to rate a posting, change a rating and set the application status from the list. The view SHALL show the pass button, the correction counter, the share of corrections and the hint of the pool, and SHALL show a pass's progress. It SHALL name no run.

#### Scenario: Rate from the pool
- **WHEN** the user rates a posting in the list
- **THEN** the rating is stored and the posting shows as rated, with the counter updated

#### Scenario: Start a pass
- **WHEN** the user presses the main part of the pass button
- **THEN** the pass button turns into its cancel button, the pass's progress shows below it, and the new scores appear in the ranking when the pass ends

#### Scenario: Unscreened postings in a pass
- **WHEN** a pass pauses because it holds postings the content guard never checked
- **THEN** the view names those postings and offers to continue with them or abort the pass

#### Scenario: Change the hint settings
- **WHEN** the user opens „Einstellungen“ in the header, sets the threshold to 5 and saves
- **THEN** the hint appears from 5 corrections on

### Requirement: Pass progress below the pass button
While a pass computes, the pool view SHALL show its progress below the pass button and its counter line, in the column of the pass button; the check button and its progress or report sit in the column beside it. The progress SHALL name the phase, show a bar and, while the pass scores, the count as done out of total, moving after every posting. It SHALL keep its size from one phase to the next.

#### Scenario: Same size in every phase
- **WHEN** a pass moves from checking to scoring and to storing, and the user asks to cancel on the way
- **THEN** the progress keeps its size, and only its texts and its bar change

#### Scenario: Scoring
- **WHEN** a pass has scored 12 of 80 postings
- **THEN** the view shows 12 of 80 with a bar filled to that share

#### Scenario: Checking
- **WHEN** a pass is still checking which postings it takes
- **THEN** the view says the pass is checking, without a count

### Requirement: Cancel button of a pass
While a pass computes, the pass button SHALL give way to a button of the same width that cancels the pass, at once and without a confirm step. After the press, the view SHALL say the pass stops after the current posting, until it has stopped. A pass that waits for the answer about unscreened postings SHALL offer no cancel button, since the question offers its own abort.

#### Scenario: Cancel a pass
- **WHEN** the user presses the cancel button of a running pass
- **THEN** the view says the pass stops after the current posting, and no dialog asks to confirm

#### Scenario: Nothing moves sideways
- **WHEN** a pass starts or ends
- **THEN** the button keeps its width, and the check button and its progress keep their place

#### Scenario: Pass waits for an answer
- **WHEN** a pass asks about unscreened postings
- **THEN** the view shows the question with its abort, and no cancel button

### Requirement: No cancel while storing
While a pass stores its scores, the pool view SHALL NOT let the user cancel it, since storing always finishes, and SHALL say so below the button.

#### Scenario: Pass stores
- **WHEN** a pass reaches the storing phase
- **THEN** the view says the scores are being stored and that this cannot be cancelled, and a press on the button does nothing

### Requirement: Result of a cancelled pass
When a cancelled pass has stopped, the pool view SHALL say below the pass button, where its progress was, that the pass was cancelled and how many postings it scored, and the ranking SHALL show the scores it stored. Like the report of a check, this notice SHALL stay, also over a reload, until the user dismisses it or the next pass starts.

#### Scenario: Notice kept until dismissed
- **WHEN** a pass was cancelled after 4 scores and the user reloads the page
- **THEN** the notice still says so, and it goes once the user dismisses it

#### Scenario: Cancelled after some scores
- **WHEN** a pass is cancelled after it scored 30 postings
- **THEN** the view says it was cancelled with 30 postings scored, and those 30 show their new scores in the ranking

#### Scenario: Cancelled before any score
- **WHEN** a pass is cancelled while it checks
- **THEN** the view says it was cancelled with no posting scored, and the ranking is unchanged

### Requirement: Pass button
The pass button SHALL be a split button. Its main part SHALL name the shown variant and its count, for example „Anzeigen ohne Score scoren (3)“, and start that variant. When the shown variant has nothing to score, the main part SHALL be inert, with a visible, focusable info icon beside the button that gives the reason, and the menu SHALL stay usable. While a pass computes, the split button SHALL give way to the cancel button.

#### Scenario: Cost before the start
- **WHEN** the shown variant is „Alle Anzeigen neu scoren“ with 40 postings and the user opens the menu
- **THEN** the main part reads „Alle Anzeigen neu scoren (40)“, and the menu says 40 postings at one model call each, replacing existing scores

#### Scenario: Size stays when the variant changes
- **WHEN** the user switches the shown variant
- **THEN** the main part keeps its width, and the counter line below stays in its place

#### Scenario: Nothing without a score
- **WHEN** every posting neither excluded nor held has a score and the shown variant is „Anzeigen ohne Score scoren“
- **THEN** the main part is inert, its info icon gives the reason, and the menu still offers „Alle Anzeigen neu scoren“

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

## RENAMED Requirements

- FROM: `### Requirement: Pass progress beside the pass button`
- TO: `### Requirement: Pass progress below the pass button`
