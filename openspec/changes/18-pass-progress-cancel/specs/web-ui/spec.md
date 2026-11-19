# Spec Delta

## ADDED Requirements

### Requirement: Pass progress beside the pass button
While a pass computes, the pool view SHALL show its progress in the row of the pass button, between the button and the correction counter. The progress SHALL name the phase, show a bar and, while the pass scores, the count as done out of total, moving after every posting. It SHALL keep its size from one phase to the next.

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
- **THEN** the button keeps its width, and the progress and the correction counter keep their place in the row

#### Scenario: Pass waits for an answer
- **WHEN** a pass asks about unscreened postings
- **THEN** the view shows the question with its abort, and no cancel button

### Requirement: No double press on the pass button
For about one second after the pass button turns into the cancel button, and after the cancel button turns back, the button that appeared SHALL ignore presses.

#### Scenario: Double press on start
- **WHEN** the user presses the pass button twice in quick succession
- **THEN** the pass starts and is not cancelled

#### Scenario: Cancel as the pass ends
- **WHEN** the user presses the cancel button just as the pass ends
- **THEN** no new pass starts

### Requirement: No cancel while storing
While a pass stores its scores, the pool view SHALL NOT let the user cancel it, since storing always finishes, and SHALL say so beside the button.

#### Scenario: Pass stores
- **WHEN** a pass reaches the storing phase
- **THEN** the view says the scores are being stored and that this cannot be cancelled, and a press on the button does nothing

### Requirement: Result of a cancelled pass
When a cancelled pass has stopped, the pool view SHALL say that the pass was cancelled and how many postings it scored, and the ranking SHALL show the scores it stored.

#### Scenario: Cancelled after some scores
- **WHEN** a pass is cancelled after it scored 30 postings
- **THEN** the view says it was cancelled with 30 postings scored, and those 30 show their new scores in the ranking

#### Scenario: Cancelled before any score
- **WHEN** a pass is cancelled while it checks
- **THEN** the view says it was cancelled with no posting scored, and the ranking is unchanged

## MODIFIED Requirements

### Requirement: Pool view
The UI SHALL show the pool ranked by fit, with the text filter and the state filters, each row showing title, company, score, the user's rating, application status and, where it applies, the exploration mark or the import origin. The user SHALL be able to rate a posting, change a rating and set the application status from the list. The view SHALL show the pass button, the correction counter, the share of corrections, the hint of the pool and the two settings (threshold and rate), and SHALL show a pass's progress. It SHALL name no run.

#### Scenario: Rate from the pool
- **WHEN** the user rates a posting in the list
- **THEN** the rating is stored and the posting shows as rated, with the counter updated

#### Scenario: Start a pass
- **WHEN** the user presses the main part of the pass button
- **THEN** the pass button turns into its cancel button, the pass's progress shows beside it, and the new scores appear in the ranking when the pass ends

#### Scenario: Unscreened postings in a pass
- **WHEN** a pass pauses because it holds postings the content guard never checked
- **THEN** the view names those postings and offers to continue with them or abort the pass

#### Scenario: Change the hint settings
- **WHEN** the user sets the threshold to 5 and saves
- **THEN** the hint appears from 5 corrections on
