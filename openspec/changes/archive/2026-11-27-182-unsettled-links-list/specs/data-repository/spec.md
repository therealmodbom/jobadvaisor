## MODIFIED Requirements

### Requirement: Documented schema per entity
The system SHALL define one versioned JSON Schema per entity — profile, policy pack, posting, label, score, pool (settings and pass history), mailbox (account without password, folder choice, mails per check, start date and handled mails), unsettled links (the links alert runs could not settle) — and publish the schemas in this repository as the public contract for external writers such as a legacy exporter. A posting MAY carry an application status and an origin mark; a score belongs to a posting by its ID. The policy pack MAY hold the user's import mapping for job lists (status column, status values per application status and skip, assessment column), so the layout of the user's own list lives in the data repository and not in this repository.

#### Scenario: Schema carries a version
- **WHEN** a schema file is read
- **THEN** it declares a schema version that data files reference

#### Scenario: External writer targets the schema
- **WHEN** a file written by an external tool conforms to the published schema
- **THEN** the system loads it without any tool-specific import step

#### Scenario: Earlier version loads
- **WHEN** a posting file references the schema version before this change
- **THEN** it loads, with the status open and no origin mark

#### Scenario: No mailbox file
- **WHEN** the data repository holds no mailbox file
- **THEN** it loads, and no mailbox is configured

#### Scenario: No unsettled links file
- **WHEN** the data repository holds no unsettled links file
- **THEN** it loads, and the list of unsettled links is empty

## ADDED Requirements

### Requirement: Unsettled links stored in the data repository
The list of unsettled links SHALL be stored in the data repository, one row per link, compared as duplicate detection compares links. A row SHALL hold the link, the posting title its entry carried, its source (a mailbox check or a pasted mail), its state, the number of tries, when it first entered the list, when it was last tried, and the outcome of its last try (the attempts, or the reason when no attempt was made).

#### Scenario: File after a run
- **WHEN** a mailbox run ends with one link „Nicht gelesen“
- **THEN** the unsettled links file holds that link with its title, the source mailbox, one try and its attempts

#### Scenario: Same link from two mails
- **WHEN** two runs take the same link, and both report it as not read
- **THEN** the file holds one row for it, with two tries

### Requirement: Unsettled links stored without mail text
A row of the unsettled links SHALL NOT hold the sender, subject or text of any mail, nor any address but the link itself, such as a redirect hop or an address inside an error message.

#### Scenario: No mail text
- **WHEN** a mailbox run ends with one link „Nicht gelesen“
- **THEN** the unsettled links file holds no sender, subject or mail text

#### Scenario: Browser failure on a redirect
- **WHEN** a link fails in the browser after a redirect, and the browser's message names the redirect's address
- **THEN** the row's attempt says that the browser fetch failed, without that address or the message
