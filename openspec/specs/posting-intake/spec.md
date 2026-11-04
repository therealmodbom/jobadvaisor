# posting-intake Specification

## Purpose
Turns a job posting supplied as a link, pasted text or a PDF into a stored, schema-valid posting that triage can score.

## Requirements

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

### Requirement: Posting fields filled
Every stored posting SHALL carry a title, a company and a location, each either a value or an explicit "unknown". The user SHALL be able to correct them, and a correction SHALL be stored on the posting.

#### Scenario: Fields from pasted text
- **WHEN** the user submits pasted posting text that names the role, the employer and the place of work
- **THEN** the stored posting carries those three values

#### Scenario: Partial structured data
- **WHEN** a source supplies the title and location but no company
- **THEN** the stored posting keeps the supplied title and location and carries a company determined from the posting text, or "unknown"

#### Scenario: Correction
- **WHEN** the user corrects the company of a stored posting
- **THEN** the posting carries the corrected company, and later triage runs use it

### Requirement: Bundesagentur für Arbeit job postings
The system SHALL retrieve a posting linked from the Bundesagentur für Arbeit job board through the job board's job-detail interface, including title, company, locations and the full description. When that retrieval fails, it SHALL continue with the general fetch.

#### Scenario: Job board link
- **WHEN** the user submits a job detail URL from the Bundesagentur für Arbeit job board
- **THEN** the stored posting carries the description, title, company and locations from the job-detail interface

#### Scenario: Interface unavailable
- **WHEN** the job-detail interface does not return the posting
- **THEN** the system fetches the URL like any other link

### Requirement: Script-rendered pages captured
The system SHALL capture postings whose text appears only after client-side scripts run.

#### Scenario: Script-rendered posting
- **WHEN** a posting page renders its text only after scripts run
- **THEN** the stored posting contains that rendered text

### Requirement: Retry, fallback and alternative source
When a fetch fails or yields no posting text, the system SHALL retry, then try fallback strategies, then look for an alternative source of the same posting, within a bounded number of attempts.

#### Scenario: Alternative source found
- **WHEN** the original URL is unreachable and the same posting is available at another URL
- **THEN** the stored posting uses the alternative URL's text and records both URLs

#### Scenario: Login-walled host
- **WHEN** the URL belongs to a host in the configured login-wall list
- **THEN** the system does not fetch that URL and looks for an alternative source directly

#### Scenario: Attempts exhausted
- **WHEN** all attempts fail
- **THEN** no posting is stored
- **AND** the user sees which attempts were made and is offered pasted text or PDF instead

### Requirement: Untrusted content screened
Posting text, and any other third-party text a tool returns, is untrusted content. The system SHALL treat it as data in every model call, SHALL NOT give any model-facing tool the ability to change user data beyond recording a screening result, and, when a screening classifier is configured, SHALL screen it for instructions addressed to an AI system and for dangerous content before it is stored or passed to any model, whichever role calls the tool. The user SHALL see whether screening is on.

#### Scenario: Injected instruction in a posting
- **WHEN** a submitted posting contains an instruction addressed to an AI system
- **THEN** the posting is stored flagged, with the categories that fired
- **AND** the user sees the flag and can release the posting

#### Scenario: Injected instruction in a fetched page during the intake loop
- **WHEN** a page the intake loop fetches contains an instruction addressed to an AI system
- **THEN** that page's text does not reach the loop's model
- **AND** the loop continues with its remaining options

#### Scenario: Injected instruction in text the conversational agent retrieves
- **WHEN** the conversational agent fetches a page or researches a company and the returned text contains an instruction addressed to an AI system
- **THEN** that text does not reach the agent's model

#### Scenario: Unscreened stored posting read through a tool
- **WHEN** a tool returns the text of a stored posting the content guard never checked
- **THEN** with a classifier configured, the text is screened first and the result is recorded in the posting
- **AND** with no classifier configured, the text does not reach the model

#### Scenario: Screening not configured
- **WHEN** no screening classifier is configured
- **THEN** postings are stored unscreened, the structural defenses still apply, and the user is told that screening is off

### Requirement: Duplicate detection
The system SHALL detect a posting that is already stored, by URL or by near-identical text, and SHALL NOT store it twice.

#### Scenario: Same URL again
- **WHEN** the user submits a URL that is already stored
- **THEN** the existing posting is returned and no new posting is created

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

### Requirement: LinkedIn page cut to the posting body
For a posting fetched from a LinkedIn page, the system SHALL store as the posting text only the posting's description, its criteria block (such as seniority level and employment type) and, when the page shows one, the pay range the employer provides, and SHALL NOT store the sign-in and "join" prompts, the lists of similar jobs and job titles, or the page footer. The title, company and location shown in the page's header SHALL be supplied as the posting's fields, since they are no longer part of the stored text. A description found on the page SHALL be stored whatever its length. When the page has no recognisable description, the system SHALL treat it like any other page and store its visible text.

#### Scenario: LinkedIn guest page
- **WHEN** the user submits the URL of a LinkedIn job page whose guest view holds a header, a description, a criteria block, a "Similar jobs" list and a sign-in footer
- **THEN** the stored text contains the description and the criteria block
- **AND** it contains no sign-in prompt, no similar-job title and no footer text

#### Scenario: Pay range provided by the employer
- **WHEN** the page also shows a pay range box that names the employer as its source
- **THEN** the stored text contains that box's wording and figures
- **AND** a page without such a box stores no pay range

#### Scenario: Fields from the page header
- **WHEN** the same page is stored
- **THEN** the posting carries the header's title, company and location as its fields
- **AND** a correction by the user still replaces them

#### Scenario: Short description
- **WHEN** a LinkedIn page holds a description of only a few sentences
- **THEN** the stored text is that description and the criteria block, without similar-job or sign-in text

#### Scenario: LinkedIn page without a recognisable description
- **WHEN** a LinkedIn page yields no description
- **THEN** the stored text is the page's visible text, as for any other page

#### Scenario: Stored postings from before the cut
- **WHEN** the user runs the one-off repair on a data repository that holds LinkedIn postings stored whole
- **THEN** each text with the known whole-page layout is reduced to the description and the criteria block, without fetching the page again, and its title, company and location are unchanged
- **AND** each text that does not have that layout is left unchanged and listed in the repair's report
- **AND** scores and extracted features computed on the longer text are recomputed only on the user's request
