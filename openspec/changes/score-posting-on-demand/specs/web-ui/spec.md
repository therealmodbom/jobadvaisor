# Spec Delta

## MODIFIED Requirements

### Requirement: Posting page
The UI SHALL give each posting its own address (hash route `#/anzeigen/<id>`), and a posting the agent names in a chat answer SHALL link to it. The page SHALL show the full text, the original link, the score with its reasoning, the rating with chips and note, the application status and the import origin, and SHALL allow rating and setting the status. It SHALL also let the user correct the title, company and location behind "Bearbeiten", for postings whose fields intake read wrongly. A rated posting without a score SHALL say that it has no score because it was rated before a pass scored it, and SHALL NOT point to "Neue Anzeigen bewerten".

#### Scenario: Correct a posting's fields
- **WHEN** the user opens "Bearbeiten" on a posting page, changes the company and saves
- **THEN** the page shows the new company, and the pool lists the posting under it

#### Scenario: Link from the chat
- **WHEN** the agent names a stored posting in an answer
- **THEN** the chat shows a link to that posting's page

#### Scenario: Rated posting without a score
- **WHEN** the user opens the page of a posting rated before any pass scored it
- **THEN** the score section says it was rated before a pass scored it, and does not mention "Neue Anzeigen bewerten"

## ADDED Requirements

### Requirement: Score button
The posting page and every row of the pool view SHALL offer a button that scores this one posting now, naming its cost per click (one judge call). For a posting an exclusion rule matches, the content guard holds, or the content guard never checked while no classifier is configured, the button SHALL be disabled, with a visible info icon beside it that shows the reason on hover and on keyboard focus and gives it to screen readers.

#### Scenario: Cost named
- **WHEN** the user sees the button on a posting page or a pool row
- **THEN** it names one judge call and its approximate cost

#### Scenario: Excluded posting
- **WHEN** the user sees the button of a posting an exclusion rule matches
- **THEN** the button is disabled, and pointing at or focusing the info icon beside it says that the posting is excluded by its rules

#### Scenario: Unchecked posting without a classifier
- **WHEN** the user sees the button of a posting the content guard never checked and no classifier is configured
- **THEN** the button is disabled, and its info icon says the posting was never checked

### Requirement: Score button progress and result
While a score computes, its button SHALL show progress, and the posting page SHALL keep an earlier score visible, marked as being recomputed. When it ends, the page SHALL show the new score with its reasoning, and the row its new score with its other marks unchanged. A failure or refusal SHALL show its reason with a retry.

#### Scenario: Score from the posting page
- **WHEN** the user presses the button on the page of a posting without a score
- **THEN** the button shows progress, and then the page shows the score with its reasoning

#### Scenario: Re-score keeps the old score visible
- **WHEN** the user presses the button on a posting with score 7
- **THEN** the page shows the 7 marked as being recomputed until the new score replaces it

#### Scenario: Score from the pool
- **WHEN** the user presses the button on a row of the pool
- **THEN** the row shows the new score, and the counter is updated

#### Scenario: Pass running
- **WHEN** the user presses the button while a pass computes
- **THEN** the view says a scoring is computing, and stores no score
