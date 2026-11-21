# Spec Delta

## ADDED Requirements

### Requirement: Delete button in a pool row
Each pool row SHALL hold a delete button right of „Bewerbungsstatus“. The button SHALL show a trash icon and no text, and SHALL be named „Anzeige löschen“ for screen readers. After a confirmed delete the row SHALL disappear without a page reload, and the counter, the pass button and the check button SHALL show the pool without the posting.

#### Scenario: Delete from the pool
- **WHEN** the user presses the trash button of a row and confirms
- **THEN** the row disappears and the view stays where it was, with its filters and sort kept, and the focus moves to the row selected next

### Requirement: Delete button on the posting page
The posting page SHALL hold the same delete button in the head row under the title, after „Verfügbarkeit“. On that row „Bearbeiten“, the „Bewerbungsstatus“ select, the „Verfügbarkeit“ select and the delete button SHALL be equally high. After a confirmed delete the app SHALL return to the pool.

#### Scenario: Delete from the posting page
- **WHEN** the user presses the trash button on a posting's page and confirms
- **THEN** the app shows the pool, which no longer lists the posting

### Requirement: Delete confirmation
Every delete SHALL ask first, in a modal dialog titled „Anzeige löschen?“. The dialog SHALL name the posting's title and company and say that it is deleted for good, with its score. For a rated posting it SHALL also name the rating level and say that the rating stops counting as an example for scoring. „Endgültig löschen“ SHALL delete.

#### Scenario: Unrated posting
- **WHEN** the user presses the trash button of an unrated posting
- **THEN** the dialog names its title and company and mentions no rating

#### Scenario: Rated posting
- **WHEN** the user presses the trash button of a posting rated „Ja, auf jeden Fall“
- **THEN** the dialog names that rating and says it stops counting as an example for scoring

### Requirement: Keys and focus in the delete dialog
„Abbrechen“ SHALL have the focus when the delete dialog opens. Escape and „Abbrechen“ SHALL close the dialog without a delete and return focus to the trash button. While the dialog is open, the pool view's keyboard shortcuts SHALL be off. „Endgültig löschen“ SHALL send one delete per confirmation, however often it is pressed.

#### Scenario: Cancel
- **WHEN** the user presses Escape or „Abbrechen“ in the dialog
- **THEN** the dialog closes, nothing is deleted, and focus returns to the trash button

#### Scenario: Shortcut keys in the dialog
- **WHEN** the dialog is open over the pool and the user presses „1“
- **THEN** no posting is rated

#### Scenario: Double press
- **WHEN** the user presses „Endgültig löschen“ twice in quick succession
- **THEN** the app sends one delete

### Requirement: Delete disabled while a pass or a check runs
In the pool view the delete buttons SHALL be disabled while the view's scoring pass runs or waits for its answer about unscreened postings, and while an availability check runs. On the posting page the button SHALL be disabled while a pass or a single score computes or a check runs, read as the page loads and again every second while the button is disabled.

#### Scenario: Pool during a pass
- **WHEN** a pass runs and the user looks at a pool row
- **THEN** its trash button is disabled, and the info icon beside it names the running pass

#### Scenario: Posting page during a check
- **WHEN** an availability check runs and the user opens a posting's page
- **THEN** its trash button is disabled, and the info icon beside it names the running check

#### Scenario: Posting page after the check
- **WHEN** the check ends while the user stays on a posting's page with a disabled trash button
- **THEN** the button becomes usable without a page reload

### Requirement: Reason beside a disabled delete button
A visible, focusable info icon beside each disabled delete button SHALL give the reason: „Gerade läuft ein Score-Durchlauf. Löschen geht wieder, wenn er fertig ist.“ or „Gerade läuft eine Verfügbarkeitsprüfung. Löschen geht wieder, wenn sie fertig ist.“ The reason SHALL show on hover and on keyboard focus and reach screen readers.

#### Scenario: Reason by keyboard
- **WHEN** a pass runs and the user tabs to the info icon beside a row's trash button
- **THEN** the reason about the running pass is shown and announced

### Requirement: Delete refused or failed
When the server refuses a delete because a pass, a score or a check started meanwhile, the dialog SHALL stay open and say why in words. When the delete fails for any other reason, the dialog SHALL say so and offer to try again. When the posting turns out to be gone already, the UI SHALL treat it as deleted.

#### Scenario: Pass started meanwhile
- **WHEN** the user confirms a delete on a posting page loaded before a pass started
- **THEN** the dialog says that a scoring run is in progress, and the posting stays

#### Scenario: Already gone
- **WHEN** the user confirms a delete of a posting another tab deleted already
- **THEN** the UI behaves as after its own delete
