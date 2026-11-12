# Spec Delta

## ADDED Requirements

### Requirement: Date a posting was added
Each pool row and the posting page SHALL show, above the title, when the posting was added: „Hinzugefügt“ followed by date and time to the minute in German form („Hinzugefügt 12.11.2026, 14:05“), in the browser's time zone. The line SHALL be set smaller and with lower contrast than company and place, and SHALL meet the contrast the requirement "Accessible and consistent presentation" sets. It SHALL change neither the ranking nor the filters.

#### Scenario: Two postings added on one day
- **WHEN** the pool holds two postings added on 12 November 2026 at 09:41 and at 14:05 local time
- **THEN** their rows show „Hinzugefügt 12.11.2026, 09:41“ and „Hinzugefügt 12.11.2026, 14:05“

#### Scenario: Same date on the posting page
- **WHEN** the user opens the posting page of a posting from the pool
- **THEN** the page shows the same „Hinzugefügt …“ line as the posting's pool row

#### Scenario: Local time zone
- **WHEN** a posting was added at 23:30 UTC on 11 November 2026 and the browser's time zone is Europe/Berlin
- **THEN** the line shows „Hinzugefügt 12.11.2026, 00:30“
