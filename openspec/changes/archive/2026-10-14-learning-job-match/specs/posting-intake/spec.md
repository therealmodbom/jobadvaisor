# Spec Delta

## Purpose

Turns a job posting supplied as a link, pasted text or a PDF into a stored, schema-valid posting that triage can score.

## ADDED Requirements

### Requirement: Three input forms
The system SHALL accept a posting as a URL, as pasted text, or as an uploaded PDF, and SHALL store the result as a posting in the data repository.

#### Scenario: Pasted text
- **WHEN** the user submits pasted posting text
- **THEN** a posting with that text and source type "text" is stored

#### Scenario: PDF upload
- **WHEN** the user uploads a PDF of a posting
- **THEN** a posting with the extracted text and source type "pdf" is stored

#### Scenario: Link
- **WHEN** the user submits a URL to a posting page
- **THEN** a posting with the page's posting text, the URL and source type "url" is stored

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
