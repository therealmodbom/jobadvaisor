## MODIFIED Requirements

### Requirement: Documented schema per entity
The system SHALL define one versioned JSON Schema per entity — profile, policy pack, posting, label, score, pool (settings and pass history), mailbox (account without password, folder choice, start date and handled mails) — and publish the schemas in this repository as the public contract for external writers such as a legacy exporter. A posting MAY carry an application status and an origin mark; a score belongs to a posting by its ID. The policy pack MAY hold the user's import mapping for job lists (status column, status values per application status and skip, assessment column), so the layout of the user's own list lives in the data repository and not in this repository.

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

## ADDED Requirements

### Requirement: Mailbox settings stored without the password
The mailbox's server, port, user name, folder choice, start date and handled mails SHALL be stored in the data repository; the password SHALL never be. A handled mail SHALL be recorded by its folder's validity value and number and by a hash of its message ID, never by its sender, subject or text.

#### Scenario: File after a check
- **WHEN** the user finished the pick list of a check
- **THEN** the mailbox file in the data repository holds the handled mails as numbers and hashes, and no password, sender, subject or mail text
