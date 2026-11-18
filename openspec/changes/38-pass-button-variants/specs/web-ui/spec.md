# Spec Delta

## MODIFIED Requirements

### Requirement: Pool view
The UI SHALL show the pool ranked by fit, with the text filter and the state filters, each row showing title, company, score, the user's rating, application status and, where it applies, the exploration mark or the import origin. The user SHALL be able to rate a posting, change a rating and set the application status from the list. The view SHALL show the pass button, the correction counter, the share of corrections, the hint of the pool and the two settings (threshold and rate), and SHALL show a pass's progress. It SHALL name no run.

#### Scenario: Rate from the pool
- **WHEN** the user rates a posting in the list
- **THEN** the rating is stored and the posting shows as rated, with the counter updated

#### Scenario: Start a pass
- **WHEN** the user presses the main part of the pass button
- **THEN** the view shows progress, and the new scores appear in the ranking when the pass ends

#### Scenario: Unscreened postings in a pass
- **WHEN** a pass pauses because it holds postings the content guard never checked
- **THEN** the view names those postings and offers to continue with them or abort the pass

#### Scenario: Change the hint settings
- **WHEN** the user sets the threshold to 5 and saves
- **THEN** the hint appears from 5 corrections on

### Requirement: Score button progress and result
While a score computes, its button SHALL show progress, and the posting page SHALL keep an earlier score visible, marked as being recomputed. When it ends, the page SHALL show the new score with its reasoning, the row its new score with its other marks unchanged, and the pool its updated counter and pass count. A failure or a busy refusal SHALL show its reason with a retry; a refusal a retry cannot change (excluded, held, never checked) SHALL instead disable the button with its info icon.

#### Scenario: Score from the posting page
- **WHEN** the user presses the button on the page of a posting without a score
- **THEN** the button shows progress, and then the page shows the score with its reasoning

#### Scenario: Re-score keeps the old score visible
- **WHEN** the user presses the button on a posting with score 7
- **THEN** the page shows the 7 marked as being recomputed until the new score replaces it

#### Scenario: Score from the pool
- **WHEN** the user presses the button on a row of the pool
- **THEN** the row shows the new score, and the counter and the count on the pass button are updated

#### Scenario: Flagged on the click
- **WHEN** the user presses the button on a posting never checked, and the check it triggers flags the posting
- **THEN** no score is stored, and the button turns disabled with its info icon saying the content guard holds it

#### Scenario: Pass running
- **WHEN** the user presses the button while a pass computes
- **THEN** the view says another scoring is computing, and stores no score

## ADDED Requirements

### Requirement: Pass button
The pass button SHALL be a split button. Its main part SHALL name the shown variant and its count, for example „Anzeigen ohne Score scoren (3)“, and start that variant. Below it the view SHALL say how many postings the shown variant scores, at two model calls each, and whether it replaces scores. When the shown variant has nothing to score, the main part SHALL be disabled with the reason shown beside it, and the menu SHALL stay usable. While a pass computes, both parts SHALL be disabled.

#### Scenario: Cost before the start
- **WHEN** the shown variant is „Alle Anzeigen neu scoren“ with 40 postings
- **THEN** the main part reads „Alle Anzeigen neu scoren (40)“, and the line below says 40 postings at two model calls each, replacing existing scores

#### Scenario: Nothing without a score
- **WHEN** every posting neither excluded nor held has a score and the shown variant is „Anzeigen ohne Score scoren“
- **THEN** the main part is disabled with its reason shown, and the menu still offers „Alle Anzeigen neu scoren“

### Requirement: Pass variant menu
The menu beside the main part SHALL list both variants, each with its count and its cost, and mark the shown one. Choosing an entry SHALL make it the shown variant and SHALL NOT start a pass. A variant chosen by hand SHALL stay shown until the pool loads again (a page reload, or the reload after a pass) or the default variant changes. The menu SHALL be operable by keyboard, and its trigger SHALL have an accessible name.

#### Scenario: Choosing does not start
- **WHEN** the user opens the menu and chooses „Alle Anzeigen neu scoren“
- **THEN** the main part reads „Alle Anzeigen neu scoren (N)“, and no pass starts

#### Scenario: Default change replaces the choice
- **WHEN** the user chose „Anzeigen ohne Score scoren“ while the default was „Alle Anzeigen neu scoren“, and a rating moves the hint to „Ranking passt gut“ and back to „neu scoren sinnvoll“
- **THEN** the main part shows „Alle Anzeigen neu scoren“

#### Scenario: Reload drops the choice
- **WHEN** the user chose „Alle Anzeigen neu scoren“ below the thresholds and reloads the page
- **THEN** the main part shows „Anzeigen ohne Score scoren“

#### Scenario: Pass end drops the choice
- **WHEN** the user chose „Alle Anzeigen neu scoren“ below the thresholds and that pass ends
- **THEN** the main part shows „Anzeigen ohne Score scoren“ again

### Requirement: Scoring wording
UI texts SHALL say „scoren“ or „Score“ for the AI's scoring, and „bewerten“ or „Bewertung“ only for the user's own rating.

#### Scenario: Pass progress
- **WHEN** a pass computes
- **THEN** its progress says „Scoren läuft“ with the counts, and no text about the pass says „Bewertung“

#### Scenario: Rating texts unchanged
- **WHEN** the user filters the pool to „Noch nicht bewertet“
- **THEN** the filter keeps that name, because it is about the user's own rating
