# Spec Delta

## ADDED Requirements

### Requirement: Score button
The posting page and every row of the pool view SHALL offer a button that scores this one posting now, naming its cost per click (one judge call). For a posting an exclusion rule matches, the content guard holds, or the content guard never checked while no classifier is configured, the button SHALL be disabled, with a visible info icon beside it that shows the reason on hover and on keyboard focus and gives it to screen readers.

#### Scenario: Cost named
- **WHEN** the user sees the button on a posting page or a pool row
- **THEN** it names one judge call and its approximate cost

#### Scenario: Excluded posting
- **WHEN** the user sees the button of a posting an exclusion rule matches
- **THEN** the button is disabled, and pointing at or focusing the info icon beside it says that the posting is excluded by its rules

#### Scenario: Held posting
- **WHEN** the user sees the button of a posting the content guard holds
- **THEN** the button is disabled, and its info icon says the content guard holds it

#### Scenario: Unchecked posting without a classifier
- **WHEN** the user sees the button of a posting the content guard never checked and no classifier is configured
- **THEN** the button is disabled, and its info icon says the posting was never checked

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
- **THEN** the row shows the new score, and the counter and the count on "Neue Anzeigen bewerten" are updated

#### Scenario: Flagged on the click
- **WHEN** the user presses the button on a posting never checked, and the check it triggers flags the posting
- **THEN** no score is stored, and the button turns disabled with its info icon saying the content guard holds it

#### Scenario: Pass running
- **WHEN** the user presses the button while a pass computes
- **THEN** the view says another scoring is computing, and stores no score
