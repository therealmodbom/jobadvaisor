# Spec Delta

## MODIFIED Requirements

### Requirement: Three input forms
The system SHALL accept a posting as a URL, as pasted text, or as an uploaded PDF, and SHALL store the result as a posting in the data repository. It SHALL accept several URLs in one submission and process each on its own.

#### Scenario: Pasted text
- **WHEN** the user submits pasted posting text
- **THEN** a posting with that text and source type "text" is stored

#### Scenario: PDF upload
- **WHEN** the user uploads a PDF of a posting
- **THEN** a posting with the extracted text and source type "pdf" is stored

#### Scenario: Link
- **WHEN** the user submits a URL to a posting page
- **THEN** a posting with the page's posting text, the URL and source type "url" is stored

#### Scenario: Several links
- **WHEN** the user submits three URLs in one submission and the second one fails
- **THEN** the first and third are stored, and the answer gives the outcome of each URL: stored, duplicate of a stored posting, or failed with its attempts

## ADDED Requirements

### Requirement: Import from a job list
The system SHALL import postings, on request, from a job list the user keeps elsewhere. The user uploads the list, a Markdown file, in the web UI; no terminal command or script is needed, and the upload is not stored. The system SHALL know no particular list layout: every table in the file that has a column of http(s) links is an entry table, one entry per row, and all other text and tables are ignored. Before an import starts, the user confirms an import mapping: which column holds an entry's status, which of that column's values mean "beworben", "erledigt" or "überspringen", and, optionally, which column holds the user's own assessment of the entry. The mapping SHALL be stored in the data repository and offered prefilled for the next import. Every entry's table (the heading above it), assessment and status SHALL be stored with the posting as an origin mark, and SHALL NOT count as a rating, as a label or as a training example. The application status SHALL be derived from the entry's status through the mapping, not from its table; a value the mapping does not name gives open. Each entry's URL SHALL go through the normal intake, so duplicates, field filling and the content guard apply.

#### Scenario: Mapping proposed
- **WHEN** the user uploads a list
- **THEN** the system names the entry tables it found, their columns and the distinct values of the status column, with the stored mapping filled in where it applies

#### Scenario: Origin mark kept
- **WHEN** an entry under the heading "Abgeschlossen" with the status "Absage", which the mapping gives as "erledigt", is imported
- **THEN** the stored posting carries the table, the assessment and the status as its origin mark, has the application status "erledigt" and has no label

#### Scenario: Value without mapping
- **WHEN** an entry has a status the mapping does not name
- **THEN** its application status is open

#### Scenario: Duplicate
- **WHEN** an entry's URL matches a stored posting
- **THEN** the existing posting gains the origin mark, no second posting is stored, and its application status stays as it is

#### Scenario: Posting found through another link
- **WHEN** the intake leads an entry to a stored posting that already has an origin mark, and the entry's listed link is not one of that posting's URLs (for example the intake found another page for a link it could not read)
- **THEN** the posting keeps its origin mark, and the import names no status discrepancy for it

#### Scenario: Status differs from the list
- **WHEN** an entry matches a stored posting by its listed link or by the same posting text (a merely similar text is no match here, since it may be another posting), the entry has a status, and that status gives an application status other than the posting's
- **THEN** the posting keeps its application status, and the import names it as a status discrepancy with both statuses, so the user decides which one applies

#### Scenario: Other content ignored
- **WHEN** the file holds text, or tables without a link column, such as notes or a log
- **THEN** the import reads no entries from them

### Requirement: Closed postings are not imported
The import SHALL skip an entry that is no longer available: the mapping gives its status as "überspringen", or its listed link answers that the page is gone (HTTP 404 or 410) in the fetch ladder, in which case the intake SHALL NOT look for the posting elsewhere. It SHALL store no posting content for a skipped entry. The report SHALL count the entries per outcome and SHALL list every entry it did not import (skipped by status, link gone or failed) with the text of its row, its link and the reason, so the user can follow it up.

#### Scenario: Status says skip
- **WHEN** an entry's status is mapped to "überspringen"
- **THEN** no posting is stored, the report counts it as skipped by status and lists it

#### Scenario: Link answers gone
- **WHEN** an entry's listed link answers "gone" (HTTP 404 or 410)
- **THEN** the intake does not look for the posting at another source, no posting is stored, the report counts it as skipped, link gone, and lists it

#### Scenario: Temporary failure
- **WHEN** an entry's URL fails for a reason other than gone (for example a timeout)
- **THEN** the report counts it as failed, not as skipped, and lists it with the reason, so the user can retry
