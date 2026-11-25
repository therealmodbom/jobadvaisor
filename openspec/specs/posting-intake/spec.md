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
- **THEN** the first and third are stored, and the answer gives the outcome of each URL: stored, duplicate of a stored posting, closed with its attempts, or failed with its attempts

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
The import SHALL skip an entry that is no longer available: the mapping gives its status as "überspringen", or its listed link is a closed page („Closed page at intake“), in which case the intake SHALL NOT look for the posting elsewhere. It SHALL store no posting content for a skipped entry. The report SHALL count the entries per outcome and SHALL list every entry it did not import (skipped by status, link gone or failed) with the text of its row, its link and the reason, so the user can follow it up.

#### Scenario: Status says skip
- **WHEN** an entry's status is mapped to "überspringen"
- **THEN** no posting is stored, the report counts it as skipped by status and lists it

#### Scenario: Link answers gone
- **WHEN** an entry's listed link answers "gone" (HTTP 404 or 410) to every request
- **THEN** the intake does not look for the posting at another source, no posting is stored, the report counts it as skipped, link gone, and lists it

#### Scenario: Link redirects to a closed marker
- **WHEN** an entry's listed link redirects to an address containing "trk=expired_jd_redirect"
- **THEN** no posting is stored, the report counts it as skipped, link gone, and lists it

#### Scenario: Temporary failure
- **WHEN** an entry's URL fails for a reason other than gone (for example a timeout)
- **THEN** the report counts it as failed, not as skipped, and lists it with the reason, so the user can retry

#### Scenario: Gone answer disputed
- **WHEN** an entry's listed link answers HTTP 404 once and HTTP 429 to the other requests
- **THEN** the intake looks for the posting at another source as for any failed link, and unless one yields it, the report counts the entry as failed, not as skipped, and lists it

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

### Requirement: Links a rule did not read are named
When a fixed rule reads a mail, the system SHALL name each host of the other links it kept and did not read, with the number of those links, so a paste of several senders' mails does not lose postings without notice.

#### Scenario: Two senders in one paste
- **WHEN** the user submits one paste holding a LinkedIn alert and the alert of a sender no rule reads
- **THEN** the LinkedIn postings are returned, no model is called, and the answer names the other sender's host as not read

#### Scenario: Unread link on a host a rule read
- **WHEN** a mail holds a career-site job link a rule reads and a link to a second posting on the same host under a path no rule reads
- **THEN** the first posting is returned, and the answer names that host with the number of links it did not read

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
Before a link from a mail is shown, fetched, stored or logged, the system SHALL remove its personal parameters. A link a fixed rule reads SHALL be rebuilt from the posting's ID, without a query. Any other link SHALL keep only the query parameters whose name identifies a posting, and a fragment only when it is a hash route holding no `=`. A redirect SHALL be followed only to an address with no query parameter beyond those, checked before it is requested, also when a fixed rule reads that address. A redirect to an address a closed rule's redirect marker matches SHALL end as a closed page before that check.

#### Scenario: Link with a login token
- **WHEN** a LinkedIn alert links a job through a tracking path with a one-time login token in its query
- **THEN** the entry's link is the plain address of that LinkedIn job page, without a query

#### Scenario: Other sender's link
- **WHEN** a link the model found carries a job ID parameter, a session token and a tracking parameter
- **THEN** the entry's link keeps the job ID parameter only

#### Scenario: Redirect target with a token
- **WHEN** an added entry's link redirects to an address that carries a token in its query
- **THEN** that address is never requested, and unless another source of the posting is found, the entry is reported as failed with the refused redirect among its attempts

#### Scenario: Redirect to a closed marker
- **WHEN** an added entry's link redirects to an address containing "trk=expired_jd_redirect"
- **THEN** that address is never requested, and unless another source of the posting is found, the entry is reported as closed

#### Scenario: Redirect to a known sender's link with a token
- **WHEN** an added entry's link redirects to a LinkedIn job page address that carries a login token in its query
- **THEN** that address is never requested

#### Scenario: Clean redirect
- **WHEN** an added entry's link redirects to the same path with a trailing slash
- **THEN** the redirect is followed and the posting is stored

### Requirement: Links that do not tell postings apart
When two postings the model found have the same link after the removal of personal parameters, the system SHALL return both, mark them as not addable by their link, and SHALL NOT merge them or store either as the other's duplicate. Entries of one posting, with the same title and the same cleaned link, SHALL become one entry.

#### Scenario: Two postings behind one redirect address
- **WHEN** a mail links two different postings through one click-redirect address that differs only in its query
- **THEN** both are returned, marked as not addable by their link

### Requirement: Chosen entries added in the background
The system SHALL add the entries the user chooses from a mail in a background run, one after the other, each through the normal intake of a link, so the fetch ladder, the intake loop, duplicate detection, the content guard and field filling apply. While the run goes on, the system SHALL report the state of each entry. When an entry ends, it SHALL report its outcome: stored, duplicate of a stored posting, closed with its attempts, or failed with its attempts or its reason, and it SHALL count as done. A failed or closed entry SHALL NOT stop the others.

#### Scenario: One entry fails
- **WHEN** the user adds three entries and the second one cannot be read
- **THEN** the first and third are stored, and the second is reported as failed with its attempts

#### Scenario: Entry stored meanwhile
- **WHEN** a chosen entry was stored by another way after the mail was read
- **THEN** it is reported as a duplicate, and no second posting is stored

#### Scenario: Entry whose text is stored under another link
- **WHEN** a chosen entry's link is new, and the posting text its page yields matches a stored posting
- **THEN** it is reported as a duplicate by text, naming that posting, and nothing new is stored

#### Scenario: Closed entry counts as done
- **WHEN** the user adds two entries and the first is reported as closed
- **THEN** the run counts it as done, and the second is added

### Requirement: A text duplicate stored anyway on request
The system SHALL, when the user explicitly asks for it for an entry reported as a duplicate by text, store that entry as a new posting despite the matching text. It SHALL NOT do so for an entry whose link a stored posting has: such an entry is never stored again.

#### Scenario: Stored anyway
- **WHEN** an entry was reported as a duplicate by text, and the user asks to store it anyway
- **THEN** a new posting with that entry's link and text is stored, and the existing posting stays as it is

#### Scenario: Link duplicate cannot be forced
- **WHEN** a request asks to store an entry anyway whose link a stored posting has
- **THEN** the existing posting is reported as a duplicate by link, and nothing new is stored

### Requirement: One alert run at a time
The system SHALL compute one alert-mail run at a time, and SHALL refuse to start another while one computes, naming the run that computes so the client can follow it. A run's state SHALL live in memory only, so a restart forgets it.

#### Scenario: Second run
- **WHEN** the user starts a run while another alert-mail run computes
- **THEN** the second run is refused, and the answer names the run that computes

#### Scenario: Restart
- **WHEN** the application restarts during a run
- **THEN** the run's state is gone, and entries already stored count as duplicates when the mail is added again

### Requirement: Closed page at intake
Intake of a link SHALL treat its page as closed when the link redirects to an address a closed rule's redirect marker matches, shows a page that a closed rule's page text marker matches and that holds no posting text, or answers HTTP 404 or 410 and no other attempt on the link disputes that answer („Disputed gone answer“). It SHALL store nothing from a closed page and SHALL NOT request an address a redirect marker matches.

#### Scenario: Expired LinkedIn link
- **WHEN** the user submits a LinkedIn link that redirects to an address containing "trk=expired_jd_redirect"
- **THEN** the search page behind the redirect is never requested, and nothing from it is stored

#### Scenario: Short closed notice
- **WHEN** a submitted link shows only a short notice that a closed rule's page text marker matches, and no posting text
- **THEN** nothing from the page is stored

#### Scenario: Gone on every request
- **WHEN** a submitted link answers HTTP 404 to the plain and to the rendered fetch, no other source holds the posting, and the further pages the intake loop fetched hold no posting text
- **THEN** the outcome is closed

### Requirement: Closed when no other source holds the posting
After a closed page, intake of a single link, several links or an alert mail entry SHALL look for the posting at another source, as for any failed link. When no other source yields it, the outcome SHALL be closed, not failed, with its attempts.

#### Scenario: Gone link found elsewhere
- **WHEN** the user submits a link that answers HTTP 404, and the same posting is available at another URL
- **THEN** the stored posting uses the other URL's text and records both URLs

#### Scenario: Expired link, no other source
- **WHEN** the user submits a LinkedIn link that redirects to an address containing "trk=expired_jd_redirect", and no other source holds the posting
- **THEN** no posting is stored, and the outcome is closed with its attempts

#### Scenario: Expired link from an alert mail
- **WHEN** an alert mail entry the user adds redirects to an address containing "trk=expired_jd_redirect", and no other source holds the posting
- **THEN** the run reports the entry as closed, not as failed

### Requirement: Closed page text stored as closed
When the page of a submitted link holds the posting text and a closed rule's page text marker matches it, intake SHALL store the posting with the availability closed, set by a check at the time of intake.

#### Scenario: Posting already filled
- **WHEN** the user submits a link whose page holds the posting text and a phrase a closed rule's page text marker names for that host
- **THEN** the posting is stored, closed, and the pool lists it only under „geschlossen“

### Requirement: Posting read from a link stored as available
When intake of a link stores the posting text it read from a page, and no closed rule's page text marker matches it, intake SHALL store the posting with the availability available, set by a check at the time of intake. This SHALL hold for a single link, several links, an alert mail entry and a list import, also when the text came from another source than the submitted link. A posting added as pasted text or a PDF SHALL be stored never checked.

#### Scenario: Link stored as available
- **WHEN** the user adds a link from an alert mail and its page holds the posting
- **THEN** the posting is stored as available, set by a check at the time it was added

#### Scenario: Pasted text never checked
- **WHEN** the user adds a posting as pasted text
- **THEN** it is stored never checked

### Requirement: A deleted posting is no duplicate
After a posting is deleted, its links and its text SHALL no longer count as stored. Submitting the same link again SHALL store a fresh posting.

#### Scenario: Same link after a delete
- **WHEN** the user deletes a posting and then submits its link again
- **THEN** a new posting is stored, unrated and without a score, and no duplicate is reported

### Requirement: Mailbox over IMAP with TLS
The system SHALL read job alert mails from one IMAP mailbox given by host, port and user, with the stored password. Every connection SHALL use TLS with the server certificate verified, and the system SHALL never send the password over a connection without TLS. A connection attempt SHALL give up after 30 seconds.

#### Scenario: Certificate not trusted
- **WHEN** the configured server presents a certificate that does not verify for its host
- **THEN** no login is attempted, and the answer says that the server's certificate is not trusted

#### Scenario: Server does not answer
- **WHEN** the configured server does not answer within 30 seconds
- **THEN** the attempt ends, and the answer says that the server is not reachable

#### Scenario: Port without TLS
- **WHEN** the configured port answers without TLS
- **THEN** no login is attempted, and the answer names a connection problem without any text from the server

### Requirement: Mailbox folders listed
After a successful login, the system SHALL list the account's folders that can hold mails, by their readable names, and leave out folders the server marks as not selectable. It SHALL mark each folder the server flags as trash, junk, sent, drafts, all mails, flagged or important as a system folder.

#### Scenario: Folders of an account
- **WHEN** the user connects to an account with the folders „Posteingang“, „Jobs“ and a trash folder the server flags as trash
- **THEN** the answer lists all three, and only the trash folder is marked as a system folder

#### Scenario: Folder name outside ASCII
- **WHEN** an account holds a folder named „Entwürfe“
- **THEN** the list shows it as „Entwürfe“

#### Scenario: Parent folder that holds no mails
- **WHEN** the server lists a folder marked as not selectable
- **THEN** the list leaves it out, and no check tries to open it

### Requirement: Folders a check searches
A check SHALL search every listed folder that exists at the time of the check except system folders when the user chose all folders, or exactly the folders the user chose otherwise. A chosen folder that no longer exists SHALL be skipped and named in the check's result.

#### Scenario: Folder created later
- **WHEN** the user chose all folders and later creates the folder „Jobs 2027“
- **THEN** the next check searches „Jobs 2027“ too

#### Scenario: Server without folder flags
- **WHEN** the server flags no folder as a system folder and the user chose all folders
- **THEN** every listed folder is searched

#### Scenario: Chosen folder deleted
- **WHEN** a chosen folder was deleted on the server
- **THEN** the check searches the other chosen folders and names the missing one

### Requirement: One mail read once per check
A mail that appears in several searched folders SHALL be read once per check, recognised by its message ID.

#### Scenario: Mail in two folders
- **WHEN** the same mail is in „Posteingang“ and in a chosen folder „Alle Nachrichten“
- **THEN** the check reads it once, and its entries appear once

### Requirement: The mailbox is read only
A check SHALL open each folder read-only and SHALL fetch mails without setting any flag. It SHALL never move, copy, delete or flag a mail.

#### Scenario: Unread mail stays unread
- **WHEN** a check reads a mail that was unread on the server
- **THEN** the mail is still unread on the server after the check

### Requirement: Mails from the start date on
A check SHALL consider only mails received on or after the start date set before the first check. The start date SHALL be stored when a check first logs in successfully, and SHALL change only when the account changes.

#### Scenario: Older mail
- **WHEN** the start date is 24 October and a searched folder holds a mail received on 20 October
- **THEN** no check reads that mail

#### Scenario: Start date after several checks
- **WHEN** the user has run three checks on the same account
- **THEN** the start date is still the one set before the first check

#### Scenario: First check fails at login
- **WHEN** the first check fails because the server refuses the login
- **THEN** no start date is stored, and the next check asks for one again

### Requirement: Handled mails
A mail SHALL count as handled as soon as the finder has read it and returned no entry. A mail in a pick list SHALL count as handled once the pick list is finished and every link of its entries that went into the alert run has ended stored, as a duplicate or closed; with no link in the run, once the pick list is finished. A mail whose reading failed, that no model could read because screening is off, or with a link that ended failed or was not reached SHALL NOT count as handled.

#### Scenario: Pick list not finished
- **WHEN** a check offers postings from three mails and the user leaves without finishing the pick list
- **THEN** none of the three counts as handled

#### Scenario: Mail without postings
- **WHEN** the finder reads a mail and returns no entry
- **THEN** that mail counts as handled at once

#### Scenario: Reading failed
- **WHEN** the model call fails while a check reads a mail
- **THEN** that mail does not count as handled

#### Scenario: Every entry stored
- **WHEN** the user adds both entries of a mail, and the run stores one and reports the other as closed
- **THEN** the mail counts as handled once the run has ended

#### Scenario: One entry failed
- **WHEN** the user adds both entries of a mail, and the run stores one and reports the other as failed
- **THEN** the mail does not count as handled, the next check offers it again, and its stored entry appears there as already stored

#### Scenario: Failing entry left out
- **WHEN** a mail came back because one of its entries failed, and the user finishes the next pick list without selecting that entry
- **THEN** the mail counts as handled

#### Scenario: Restart during the run
- **WHEN** the application restarts while the run of a finished pick list computes
- **THEN** no mail of that pick list that had a link in the run counts as handled, and the next check offers them again

### Requirement: Mails waiting for screening
A mail that no model read because screening is off SHALL be named in the check's result as not read. Later checks SHALL skip it while screening stays off, and the first check after screening is turned on SHALL read it.

#### Scenario: Screening off
- **WHEN** no classifier is configured and a check reads a mail from a sender without a fixed rule
- **THEN** the result names it as not read while screening is off, and the next check does not read it again

#### Scenario: Screening turned on
- **WHEN** a classifier is configured after such a check
- **THEN** the next check reads that mail

### Requirement: Handled mails are skipped
A check SHALL skip every handled mail. A handled mail that carries a message ID SHALL stay handled after the server renumbered its folder, and when it was moved to another searched folder.

#### Scenario: Next check
- **WHEN** the user finished the pick list of a check, the run stored every chosen entry, and the user runs another check
- **THEN** the mails of the first check are not read again

#### Scenario: Mail moved
- **WHEN** a handled mail with a message ID is moved from „Posteingang“ to „Jobs“ and both are searched
- **THEN** the next check does not read it

#### Scenario: Folder renumbered
- **WHEN** the server renumbers a searched folder
- **THEN** the handled mails in it that carry a message ID are not read again

### Requirement: Each mail through the finder
A check SHALL pass each unhandled mail to the same finder as a pasted mail, with the mail's HTML part, or its plain-text part when the HTML part is missing or blank. The fixed rules, the content guard, the model and the record of how each mail was read SHALL apply unchanged.

#### Scenario: Known sender
- **WHEN** a check reads a LinkedIn job alert mail
- **THEN** its postings are found and no model is called

#### Scenario: Mail held by the content guard
- **WHEN** the content guard flags a mail a check reads
- **THEN** no model reads it, and the check's result names it as held with no entry

#### Scenario: Blank HTML part
- **WHEN** a mail has an empty HTML part and a plain-text part with posting URLs
- **THEN** the finder reads the plain-text part

### Requirement: Oversized mails offered unread
A mail whose HTML and plain-text parts together hold more than 2,000,000 characters SHALL NOT be read by the check; attachments SHALL NOT count. The check SHALL offer it in the pick list unread and not selected.

#### Scenario: Oversized mail
- **WHEN** a mail's HTML part holds more than 2,000,000 characters
- **THEN** the check does not read it and offers it in the pick list as too large, not selected

#### Scenario: Large attachment
- **WHEN** a mail carries a 10 MB attachment and an HTML part of 80,000 characters
- **THEN** the check reads it like any other mail

### Requirement: Oversized mail read on request
When the user selects an oversized mail, the system SHALL read it like any other mail and offer its entries. Finishing the pick list SHALL count an oversized mail that was not read as handled whether or not the user selected it, unless reading it on request failed; one that was read SHALL count as handled like any other mail („Handled mails“). While it is being read, the pick list SHALL NOT be finished, and no new check SHALL replace it.

#### Scenario: Oversized mail read on request
- **WHEN** the user selects an oversized mail in the pick list
- **THEN** the system reads it, and its entries appear in the pick list like those of any other mail

#### Scenario: Oversized mail left out
- **WHEN** the user finishes the pick list without selecting an oversized mail
- **THEN** that mail counts as handled, and no later check offers it

#### Scenario: Reading on request failed
- **WHEN** reading an oversized mail on request fails
- **THEN** the pick list names the failure, and the mail does not count as handled when the pick list is finished

#### Scenario: Finish during a read
- **WHEN** an oversized mail is being read on request and the pick list is finished from another tab
- **THEN** the finish is refused, and no mail counts as handled until the read has ended

### Requirement: Mails per check limited
A check SHALL read at most the number of mails set for the mailbox, oldest first, and SHALL say how many unhandled mails remain for the next check. The number SHALL be a whole number from 1 to 1000, 200 when the user has not set one. The limit bounds the model cost and the duration of one check; it is no technical limit.

#### Scenario: Large first check
- **WHEN** the limit is 200 and the searched folders hold 260 unhandled mails since the start date
- **THEN** the check reads the 200 oldest and says that 60 remain

#### Scenario: Limit changed
- **WHEN** the user sets the limit to 50 and starts a check over 260 unhandled mails
- **THEN** the check reads the 50 oldest and says that 210 remain

### Requirement: One mailbox check at a time
The system SHALL run a check in the background and SHALL report how many mails it will read and how many it has read. It SHALL refuse to start a check while another one runs, naming the running check. A check's state SHALL live in memory only. The system SHALL name the running check, or the last check whose pick list is not finished, to every client.

#### Scenario: Second check
- **WHEN** the user starts a check while another check runs
- **THEN** the start is refused, and the answer names the running check

#### Scenario: Restart during a check
- **WHEN** the application restarts before the user finished the pick list of a check
- **THEN** the check's state is gone, and the mails of its pick list are offered again by the next check

#### Scenario: Another browser tab
- **WHEN** a check ended with a pick list and the user opens the mailbox source in a new tab
- **THEN** the new tab shows that pick list

### Requirement: A failed check names its reason
When the key is missing, the password is missing or unreadable, the server cannot be reached, its certificate is not trusted, it refuses the login, or the connection fails otherwise before any mail was read, the check SHALL end with that reason, and no mail SHALL count as handled. A reason SHALL never contain text from the server.

#### Scenario: Login refused
- **WHEN** the server refuses the user name or the password
- **THEN** the check ends with the reason that the login was refused, and no mail counts as handled

### Requirement: An interrupted check keeps what it read
When the connection fails after a check has read mails, the check SHALL end with the mails read so far and name the interruption, and the mails it did not read SHALL stay unhandled.

#### Scenario: Connection lost
- **WHEN** the connection drops after a check has read 5 of 12 mails
- **THEN** the pick list holds the entries of those 5 mails, the result names the interruption, and the next check reads the other 7

### Requirement: Cancel a mailbox check
The user SHALL be able to cancel a running check. The check SHALL stop after the mail it reads, end with the mails read so far and name the cancel, and the mails it did not read SHALL stay unhandled. A cancel SHALL be refused for a check that is not running.

#### Scenario: Cancelled after some mails
- **WHEN** a check covering 200 mails has read 37 and the user cancels it
- **THEN** it reads no further mail, the pick list holds the entries of those 37 mails, the result says it was cancelled after 37 of 200, and the next check reads the other 163

#### Scenario: Cancel a check that has ended
- **WHEN** the user cancels a check that is done or has failed
- **THEN** the cancel is refused, and the answer says the check is not running

### Requirement: Mailbox password stored encrypted
The system SHALL store the mailbox password only encrypted, in the state directory on the machine the backend runs on. The key SHALL come from the application's secret configuration, never from a file in the state directory or the data repository. Without a valid key, the system SHALL refuse to store a password.

#### Scenario: Copy of the state directory
- **WHEN** someone holds a copy of the state directory but not the key
- **THEN** the stored password cannot be read from it

#### Scenario: No key configured
- **WHEN** no key is configured, or the configured key is malformed, and the user saves a password
- **THEN** the password is not stored, and the answer says that no key is configured

### Requirement: The mailbox password is never revealed
The mailbox password SHALL NOT appear in an API answer, a log line, a trace, an error message or a file of the data repository. The API SHALL answer only whether a password is stored.

#### Scenario: Settings read back
- **WHEN** a client reads the mailbox settings after a password was stored
- **THEN** the answer says that a password is stored and does not contain it

#### Scenario: Login fails
- **WHEN** a login with the stored password fails
- **THEN** neither the answer nor the log contains the password

### Requirement: The password stays with its account
Changing the server, the port or the user name without entering a new password SHALL remove the stored password, so it is never sent to another server or account.

#### Scenario: Server changed
- **WHEN** a password is stored and the user changes the server without entering a password
- **THEN** the stored password is removed, and no login is attempted until a new one is entered

### Requirement: A new account starts fresh
Changing the server or the user name SHALL clear the start date, the time of the last check and the record of handled mails, and SHALL drop an unfinished pick list. While a check runs, the account SHALL NOT be changed.

#### Scenario: Other account
- **WHEN** the user changes the user name to another account
- **THEN** the next check asks for a start date and offers every mail since then

#### Scenario: Change during a check
- **WHEN** the user saves another server while a check runs
- **THEN** the change is refused, and the answer names the running check

### Requirement: Unreadable stored password
When the stored password cannot be decrypted with the configured key, the system SHALL NOT attempt a login, and SHALL say that the password must be entered again.

#### Scenario: Key changed
- **WHEN** the key was changed after a password was stored, and the user starts a check
- **THEN** no login is attempted, and the answer says that the password must be entered again

### Requirement: Mailbox entries added like alert entries
Finishing a check's pick list SHALL accept only links the check offered, compared as duplicate detection compares links, from none up to all of them. Chosen entries SHALL be added through the same background run as entries from a pasted mail. When the run cannot start, no mail SHALL count as handled. A finished pick list SHALL NOT be finished again.

#### Scenario: Entries added
- **WHEN** the user finishes a check's pick list with four chosen entries from two mails
- **THEN** an alert run adds the four entries, and once it has stored them, both mails count as handled

#### Scenario: More than 100 entries
- **WHEN** a check's pick list holds 140 selected entries and the user adds them
- **THEN** one alert run adds all 140

#### Scenario: Another run computes
- **WHEN** the user finishes a check's pick list while another alert run computes
- **THEN** no run starts, the answer names the running run, and no mail of the check counts as handled

#### Scenario: Entry the check did not offer
- **WHEN** a request finishes a check with a link the check did not offer
- **THEN** it is refused, and nothing is added or marked

### Requirement: Disputed gone answer
An HTTP 404 or 410 answer SHALL NOT make a link closed when another attempt on the same link was disputed: answered by the server with an HTTP status other than 200, 404 or 410, or ended in a connection or browser failure. Intake SHALL then treat the link as failed, and look for the posting at another source as for any failed link. An alert run SHALL report such an entry as failed with its attempts, and say that the link could not be judged.

#### Scenario: One 404 among rate-limited answers
- **WHEN** an alert run adds an entry whose link answers HTTP 404 to the plain fetch and HTTP 429 to the rendered fetch and to the intake loop's fetches of it, and no other source holds the posting
- **THEN** the entry is reported as failed with its attempts, not as closed, and the report says that the link could not be judged

#### Scenario: A page without posting text does not dispute
- **WHEN** a link answers HTTP 404 to the plain fetch, and the rendered fetch shows a page without posting text
- **THEN** the gone answer stands, and unless another source holds the posting, the outcome is closed

#### Scenario: Another address does not dispute
- **WHEN** a link answers HTTP 404 to every request, and a page the intake loop fetches on another host answers HTTP 429
- **THEN** the gone answer stands

#### Scenario: A retried request disputes
- **WHEN** the plain fetch of a link is answered with HTTP 429, or fails to connect, and its retry is answered with HTTP 404
- **THEN** both answers are among the entry's attempts, and the 404 does not make the link closed

### Requirement: Requests in an alert run spaced per host
During an alert run, the system SHALL send a request to a host only when its last request to that host lies at least 3 seconds back. This SHALL count every request of the run's intake: each fetch, its retry and each redirect it follows, the intake loop's fetches and the lookup of a company's facts. A page rendered in the browser SHALL count as one request.

#### Scenario: Two entries on one host
- **WHEN** an alert run adds two entries on the same host
- **THEN** no two of its requests to that host lie less than 3 seconds apart

#### Scenario: Retry after a rate limit
- **WHEN** a request in an alert run is answered with HTTP 429
- **THEN** its retry is sent no sooner than 3 seconds later

#### Scenario: Redirect on the same host
- **WHEN** a link in an alert run redirects to another address on its host
- **THEN** the redirect's request is sent no sooner than 3 seconds after the first one

### Requirement: One link offered once per check
When several mails of one check hold the same link, compared as duplicate detection compares links, the check SHALL offer it in the first mail of the pick list that holds it. Each later mail SHALL list it, marked with the mail that offers it, as not selectable. A mail read on request SHALL offer a link only when no other mail of the check offers it.

#### Scenario: Same posting in three mails
- **WHEN** a check reads three mails that each hold the same LinkedIn job, two of them under a tracking form of its address
- **THEN** the first mail offers the entry, and the other two list it as offered in the first mail, not selectable

### Requirement: One fetch per link in a run
An alert run SHALL put each link through intake at most once, compared as duplicate detection compares links. A later entry with the same link SHALL end with the outcome of the first entry, without a fetch of its own, and SHALL name that entry.

#### Scenario: Same link twice in a run
- **WHEN** a run is started with two entries whose links differ only in a tracking parameter
- **THEN** the link is fetched once, both entries end with the same outcome, and the second names the first

### Requirement: Cancel an alert run
The user SHALL be able to cancel a running alert run. The run SHALL stop after the entry it works on and end cancelled when an entry was left out. The entries stored before SHALL stay stored, and the entries it did not reach SHALL stay not started. A cancel SHALL be refused for a run that has ended.

#### Scenario: Cancelled after some entries
- **WHEN** a run over 120 entries has ended 50 and the user cancels it
- **THEN** it adds no further entry after the current one, ends cancelled, and its report says how many entries it ended

#### Scenario: Cancel during the last entry
- **WHEN** the user cancels a run while it works on its last entry
- **THEN** that entry ends, and the run ends done, not cancelled, since no entry was left out

#### Scenario: Mails of a cancelled mailbox run
- **WHEN** a mailbox run is cancelled before it reached the entries of some mails
- **THEN** those mails do not count as handled and the next check offers them again, and the mails whose entries all ended stored, as duplicates or closed count as handled

#### Scenario: Cancel a run that has ended
- **WHEN** the user cancels a run that is done, cancelled or has failed
- **THEN** the cancel is refused, and the answer says the run is not running

### Requirement: No mailbox check while an alert run computes
The system SHALL refuse to start a mailbox check while an alert run computes, and SHALL name that run, so the client can follow it.

#### Scenario: Check during a run
- **WHEN** the user starts a mailbox check while the run of the last pick list still computes
- **THEN** the check does not start, and the answer names the run
