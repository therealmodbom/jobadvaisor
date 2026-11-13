# posting-intake Specification

## Purpose
Turns a job posting supplied as a link, pasted text or a PDF, or listed in a job alert mail, into a stored, schema-valid posting that triage can score.

## Requirements

### Requirement: Input forms
The system SHALL accept a posting as a URL, as pasted text, or as an uploaded PDF, and SHALL store the result as a posting in the data repository. It SHALL accept several URLs in one submission and process each on its own. It SHALL also accept a job alert mail, find the postings it lists, and add the ones the user chooses.

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

#### Scenario: Alert mail
- **WHEN** the user submits a job alert mail that lists three new postings and adds all three
- **THEN** three postings with source type "url" are stored, each with its entry's cleaned link

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
Posting text, the text of a job alert mail, and any other third-party text a tool returns, is untrusted content. The system SHALL treat it as data in every model call, SHALL NOT give any model-facing tool the ability to change user data beyond recording a screening result, and, when a screening classifier is configured, SHALL screen it for instructions addressed to an AI system and for dangerous content before it is stored or passed to any model, whichever role calls the tool. The user SHALL see whether screening is on.

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

#### Scenario: Injected instruction in an alert mail
- **WHEN** a classifier is configured, and an alert mail that no fixed rule reads contains an instruction addressed to an AI system
- **THEN** the mail's text does not reach the model, no posting is found in it, and the user is told that the content guard held the mail

#### Scenario: Unscreened stored posting read through a tool
- **WHEN** a tool returns the text of a stored posting the content guard never checked
- **THEN** with a classifier configured, the text is screened first and the result is recorded in the posting
- **AND** with no classifier configured, the text does not reach the model

#### Scenario: Screening not configured
- **WHEN** no screening classifier is configured
- **THEN** postings are stored unscreened, the structural defenses still apply, and the user is told that screening is off

### Requirement: Duplicate detection
The system SHALL detect a posting that is already stored, by URL or by near-identical text, and SHALL NOT store it twice. A LinkedIn job page SHALL count as the same URL by its job ID, in each of these forms: `/jobs/view/<id>`, `/comm/jobs/view/<id>`, `/jobs/view/<slug>-<id>` and a `currentJobId=<id>` parameter on a `/jobs/` path.

#### Scenario: Same URL again
- **WHEN** the user submits a URL that is already stored
- **THEN** the existing posting is returned and no new posting is created

#### Scenario: LinkedIn job by its ID
- **WHEN** a stored posting has the address `https://www.linkedin.com/jobs/view/<id>`, and a submitted link is `/comm/jobs/view/<id>/` with tracking parameters
- **THEN** the submitted link counts as that stored posting, before any page is fetched

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

### Requirement: Postings found in a job alert mail
Given a job alert mail as pasted HTML, or as plain text that prints its URLs, the system SHALL return the postings the mail lists, each as a title and a link, one entry per posting, in mail order, without fetching any page. It SHALL answer at most 100 entries and say when the mail held more. A title SHALL never be a URL. Each entry SHALL say whether a stored posting already has its link, and whether its host is a login-walled host.

#### Scenario: Several links per posting
- **WHEN** a mail lists six postings, each linked from its image, its title and its company line
- **THEN** six entries are returned, each with the posting's title

#### Scenario: Numbered list with buttons
- **WHEN** a mail lists postings as "1. <title>" with a "view job" button beside each
- **THEN** each posting is returned once, with its title without the list number

#### Scenario: Plain text with URLs
- **WHEN** the pasted mail holds no HTML, and its text prints each posting's URL on the line after its title
- **THEN** each posting is returned with that title and URL

#### Scenario: Posting already stored
- **WHEN** one of the postings a mail lists is already stored under its link
- **THEN** its entry names the stored posting

### Requirement: Only posting links from a mail
The system SHALL offer only absolute http(s) links on public hosts from a mail: no other scheme, relative link, `localhost`, single-label host or private or reserved IP address. Before the model reads a mail, links whose text or address names unsubscribing, settings, a search, a profile, help, privacy, an imprint or a browser version of the mail SHALL be removed. When no link is left, nothing SHALL be found, and neither the content guard nor the model SHALL be called.

#### Scenario: Mail without postings
- **WHEN** a mail from an unknown sender links only to its settings, a search page, an unsubscribe page and a browser version of itself
- **THEN** no entry is returned, and no classifier or model is called

#### Scenario: Private address
- **WHEN** a mail links to `http://localhost:8000/job/1` and to `http://192.168.1.10/job/2`
- **THEN** neither link is offered

### Requirement: Known senders read without a model
The system SHALL read three kinds of alert mail by fixed rules on the shape of their links, without a model call: LinkedIn job links, Bundesagentur für Arbeit job-detail links, and career-site links with the path `/job/<title>/<number>` and a `refid` parameter on any host. A mail with no link a rule reads SHALL be read by the intake model, unless the content guard holds it or no screening classifier is configured.

#### Scenario: Known sender
- **WHEN** the user submits a LinkedIn job alert mail
- **THEN** its postings are returned and no model is called

#### Scenario: Other sender
- **WHEN** a classifier is configured, and the user submits an alert mail whose links no fixed rule reads
- **THEN** the intake model finds its postings

#### Scenario: Other sender with screening off
- **WHEN** no classifier is configured, and the user submits an alert mail whose links no fixed rule reads
- **THEN** no model is called, no posting is found, and the user is told that only known senders can be read while screening is off

#### Scenario: Classifier fails
- **WHEN** the classifier fails while screening a mail whose links no fixed rule reads
- **THEN** no model is called, and the user is told that the screening failed and can retry

### Requirement: Record of how each mail was read
Per mail, the system SHALL record which rule read it, or that the model did, or why no model read it, with the hosts of its links and the number of entries, outside the data repository. The record SHALL NOT hold a link's path or query, a title, or the mail's text.

#### Scenario: Record per mail
- **WHEN** a mail has been read
- **THEN** the record names the rule or the model and the hosts of the mail's links, and holds no path, query, title or mail text

### Requirement: The model sees no link targets
When the model reads a mail, it SHALL receive the mail's visible text with each link marked by a number, its text, and its host and path, and SHALL answer with link numbers and titles. The model SHALL NOT receive any query, whether in a link, in a URL printed in the text, or in a link's text. A path segment that looks like a token SHALL be masked. A number the mail does not hold SHALL be dropped, and no URL the model writes SHALL be used.

#### Scenario: Invented link
- **WHEN** the model's answer names a link number the mail does not hold, or writes out a URL
- **THEN** no entry is returned for it

#### Scenario: Tokens kept from the model
- **WHEN** a link in the mail carries a login token in its query, and the mail prints the same URL in its text and in a link's text
- **THEN** the model's input does not contain the token

### Requirement: Links from a mail carry no personal parameters
Before a link from a mail is shown, fetched, stored or logged, the system SHALL remove its personal parameters. A link a fixed rule reads SHALL be rebuilt from the posting's ID, without a query. Any other link SHALL keep only the query parameters whose name identifies a posting, and a fragment only when it is a hash route holding no `=`. A redirect SHALL be followed only to an address this removal leaves unchanged or a fixed rule reads, checked before it is requested.

#### Scenario: Link with a login token
- **WHEN** a LinkedIn alert links a job through a tracking path with a one-time login token in its query
- **THEN** the entry's link is the plain address of that LinkedIn job page, without a query

#### Scenario: Other sender's link
- **WHEN** a link the model found carries a job ID parameter, a session token and a tracking parameter
- **THEN** the entry's link keeps the job ID parameter only

#### Scenario: Redirect target with a token
- **WHEN** an added entry's link redirects to an address that carries a token in its query
- **THEN** that address is never requested, and unless another source of the posting is found, the entry is reported as failed with the refused redirect among its attempts

#### Scenario: Clean redirect
- **WHEN** an added entry's link redirects to the same path with a trailing slash
- **THEN** the redirect is followed and the posting is stored

### Requirement: Links that do not tell postings apart
When two postings the model found have the same link after the removal of personal parameters, the system SHALL return both, mark them as not addable by their link, and SHALL NOT merge them or store either as the other's duplicate. Entries of one posting, with the same title and the same cleaned link, SHALL become one entry.

#### Scenario: Two postings behind one redirect address
- **WHEN** a mail links two different postings through one click-redirect address that differs only in its query
- **THEN** both are returned, marked as not addable by their link

### Requirement: Chosen entries added in the background
The system SHALL add the entries the user chooses from a mail in a background run, one after the other, each through the normal intake of a link, so the fetch ladder, the intake loop, duplicate detection, the content guard and field filling apply. While the run goes on, the system SHALL report the state of each entry. When an entry ends, it SHALL report its outcome: stored, duplicate of a stored posting, or failed with its attempts or its reason. A failed entry SHALL NOT stop the others.

#### Scenario: One entry fails
- **WHEN** the user adds three entries and the second one cannot be read
- **THEN** the first and third are stored, and the second is reported as failed with its attempts

#### Scenario: Entry stored meanwhile
- **WHEN** a chosen entry was stored by another way after the mail was read
- **THEN** it is reported as a duplicate, and no second posting is stored

### Requirement: One alert run at a time
The system SHALL compute one alert-mail run at a time, and SHALL refuse to start another while one computes, naming the run that computes so the client can follow it. A run's state SHALL live in memory only, so a restart forgets it.

#### Scenario: Second run
- **WHEN** the user starts a run while another alert-mail run computes
- **THEN** the second run is refused, and the answer names the run that computes

#### Scenario: Restart
- **WHEN** the application restarts during a run
- **THEN** the run's state is gone, and entries already stored count as duplicates when the mail is added again
