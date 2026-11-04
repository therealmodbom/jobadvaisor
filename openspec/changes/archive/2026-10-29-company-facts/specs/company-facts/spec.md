# Spec Delta

## Purpose

Gives feature extraction facts about the hiring employer, its size class and founding year, looked up once per company when a posting is added, so the extractor does not decide a company's stage from the posting text and the model's memory alone.

## ADDED Requirements

### Requirement: Company facts looked up at intake
When a posting is added from a URL and its company has no stored company record, the system SHALL look up the company's size class and founding year once and store them as that company's record, with the source and the fetch date. The company is identified by its name as the posting carries it; a posting whose company is "unknown" triggers no lookup. A posting added as pasted text or as a PDF triggers no lookup. A company that already has a record, whether or not it holds facts, SHALL NOT be looked up again.

#### Scenario: First posting of a company
- **WHEN** a posting is added from a URL and its company has no record
- **THEN** a record for that company exists afterwards with the size class and founding year the source gave, the source and the fetch date

#### Scenario: Second posting of the same company
- **WHEN** a second posting of a company that has a record is added
- **THEN** no request for company facts is made

#### Scenario: Posting without a link
- **WHEN** a posting is added as pasted text
- **THEN** no company lookup is made and no record is written

### Requirement: Source order
The system SHALL read the company's facts first from its LinkedIn company page, found through the company link on the LinkedIn job page the posting came from, and, when that page gives no facts or no such link exists, from the employer's website, read only as schema.org `Organization` data. Both facts of a record SHALL come from the one source that gave any fact, so the record's source is exact; a founding year missing on LinkedIn stays missing and is not filled from the website. The record SHALL name that source.

#### Scenario: LinkedIn page gives both facts
- **WHEN** the company page states a size class and a founding year
- **THEN** the record holds both and names LinkedIn as the source

#### Scenario: LinkedIn page gives no founding year
- **WHEN** the company page states a size class but no founding year
- **THEN** the record holds the size class without a founding year, names LinkedIn as the source, and the employer's website is not requested

#### Scenario: Posting from another site
- **WHEN** a posting is added from a URL on an employer's own site and carries no LinkedIn company link
- **THEN** the lookup reads the employer's website and stores what its `Organization` data states, or a record without facts

### Requirement: A failed lookup changes nothing
A lookup that fails, is blocked, answers with something unreadable or finds no facts SHALL NOT fail the intake, SHALL NOT change a stored posting or a stored record, and SHALL leave the posting without company facts. A lookup that completed and found no facts SHALL store a record without facts, so it is not repeated for each posting of that company. A lookup that did not complete (transport error, rate limit or server error answer) SHALL store nothing and SHALL NOT fall back to the next source, so the next posting of the company tries again from the first source.

#### Scenario: Page blocked
- **WHEN** the company page answers HTTP 429
- **THEN** the posting is stored as usual, the employer's website is not requested, no record is written, and the next posting of that company looks the facts up again

#### Scenario: Page without the facts
- **WHEN** the company page and the employer's website state no size class and no founding year
- **THEN** the posting is stored as usual and a record without facts is written

### Requirement: Fetching is limited and local
The system SHALL keep a minimum interval between requests to the same host for company lookups, and SHALL send nothing to any service but the company page or website being read and the configured model. The posting text SHALL NOT leave the machine through a lookup. A lookup SHALL make at most two requests, one for the LinkedIn company page and one for the employer's website, each bounded by the intake fetch timeout, and the second only when the first gave no facts.

#### Scenario: Several new companies in one submission
- **WHEN** a submission of many links adds postings of several new companies
- **THEN** requests for company facts to the same host are spaced by at least the minimum interval

### Requirement: Facts stored for earlier postings
The system SHALL offer a one-off command that looks up company facts for every stored posting whose company has no record, by fetching the posting's job page again to find the company link. It SHALL be a dry run unless told to apply, SHALL report the companies it would look up or looked up, and SHALL change no posting.

#### Scenario: Dry run
- **WHEN** the command runs without the apply flag on a repository whose postings have no company records
- **THEN** it lists the companies it would look up and writes nothing

#### Scenario: Apply
- **WHEN** the command runs with the apply flag
- **THEN** each company with a readable page gets a record and no posting file changes
