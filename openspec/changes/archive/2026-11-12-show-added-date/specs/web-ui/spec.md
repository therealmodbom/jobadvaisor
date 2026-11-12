# Spec Delta

## ADDED Requirements

### Requirement: Date a posting was added
Each pool row and the posting page SHALL show, above the title, a line with „Hinzugefügt“ followed by the date and time to the minute at which the posting was added.

#### Scenario: Two postings added on one day
- **WHEN** the pool holds two postings added on 12 November 2026 at 09:41 and at 14:05 local time
- **THEN** their rows show „Hinzugefügt 12.11.2026, 09:41“ and „Hinzugefügt 12.11.2026, 14:05“

#### Scenario: Same date on the posting page
- **WHEN** the user opens the posting page of a posting from the pool
- **THEN** the page shows the same „Hinzugefügt …“ line as the posting's pool row

### Requirement: Added date in German form
The added date SHALL be written as day, month and four-digit year separated by dots, then a comma and the time as hours and minutes, each two digits.

#### Scenario: Single-digit day, month and hour
- **WHEN** a posting was added on 5 January 2026 at 09:03 local time
- **THEN** the line shows „Hinzugefügt 05.01.2026, 09:03“

### Requirement: Added date in the browser's time zone
The added date SHALL be shown in the browser's time zone.

#### Scenario: Date across midnight
- **WHEN** a posting was added at 23:30 UTC on 11 November 2026 and the browser's time zone is Europe/Berlin
- **THEN** the line shows „Hinzugefügt 12.11.2026, 00:30“

### Requirement: Added date as secondary information
The added-date line SHALL be set smaller and with lower contrast than company and place, and SHALL still meet the contrast the requirement "Accessible and consistent presentation" sets, in both themes.

#### Scenario: Contrast in both themes
- **WHEN** the contrast check runs on the line's colour in the light and the dark theme
- **THEN** it reaches 4.5:1 on the page background and on a card, and stays below the contrast of company and place
