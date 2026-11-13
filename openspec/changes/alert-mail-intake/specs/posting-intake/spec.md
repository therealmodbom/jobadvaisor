# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: Three input forms`
- TO: `### Requirement: Input forms`

## MODIFIED Requirements

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

## ADDED Requirements

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
