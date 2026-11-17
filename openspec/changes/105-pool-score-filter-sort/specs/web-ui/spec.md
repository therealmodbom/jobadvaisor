# Spec Delta

## ADDED Requirements

### Requirement: Score range and sort controls
The pool view SHALL show the score range and the sort choice in one row with the text filter, above the state filters, stacked at a phone's width. Both SHALL be operable by keyboard alone and usable at a phone's width without scrolling sideways.

#### Scenario: Keyboard only
- **WHEN** the user sets the range and the sort using only the keyboard
- **THEN** the list follows each choice, and focus stays on the control that changed

#### Scenario: Phone width
- **WHEN** the pool view is shown 390 pixels wide
- **THEN** the range and the sort are fully visible and usable, and the page does not scroll sideways

### Requirement: Keyboard follows the shown order
J and K SHALL move to the next and the previous posting in the order the pool shows, and Enter to the next unrated posting in that order.

#### Scenario: Sorted by added date
- **WHEN** the pool is sorted by added date, ascending, and the user presses J on the first posting
- **THEN** the selection moves to the posting added second earliest
