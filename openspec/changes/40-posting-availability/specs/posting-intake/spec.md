# Spec Delta

## ADDED Requirements

### Requirement: Closed page at intake
Intake of a link SHALL treat its page as closed when the link answers HTTP 404 or 410, redirects to an address a closed rule's redirect marker matches, or shows a page that a closed rule's page text marker matches and that holds no posting text. It SHALL store nothing from a closed page and SHALL NOT request an address a redirect marker matches.

#### Scenario: Expired LinkedIn link
- **WHEN** the user submits a LinkedIn link that redirects to an address containing "trk=expired_jd_redirect"
- **THEN** the search page behind the redirect is never requested, and nothing from it is stored

#### Scenario: Short closed notice
- **WHEN** a submitted link shows only a short notice that a closed rule's page text marker matches, and no posting text
- **THEN** nothing from the page is stored

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
- **THEN** the first and third are stored, and the answer gives the outcome of each URL: stored, duplicate of a stored posting, closed with its attempts, or failed with its attempts

#### Scenario: Alert mail
- **WHEN** the user submits a job alert mail that lists three new postings and adds all three
- **THEN** three postings with source type "url" are stored, each with its entry's cleaned link

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

### Requirement: Closed postings are not imported
The import SHALL skip an entry that is no longer available: the mapping gives its status as "überspringen", or its listed link is a closed page („Closed page at intake“), in which case the intake SHALL NOT look for the posting elsewhere. It SHALL store no posting content for a skipped entry. The report SHALL count the entries per outcome and SHALL list every entry it did not import (skipped by status, link gone or failed) with the text of its row, its link and the reason, so the user can follow it up.

#### Scenario: Status says skip
- **WHEN** an entry's status is mapped to "überspringen"
- **THEN** no posting is stored, the report counts it as skipped by status and lists it

#### Scenario: Link answers gone
- **WHEN** an entry's listed link answers "gone" (HTTP 404 or 410)
- **THEN** the intake does not look for the posting at another source, no posting is stored, the report counts it as skipped, link gone, and lists it

#### Scenario: Link redirects to a closed marker
- **WHEN** an entry's listed link redirects to an address containing "trk=expired_jd_redirect"
- **THEN** no posting is stored, the report counts it as skipped, link gone, and lists it

#### Scenario: Temporary failure
- **WHEN** an entry's URL fails for a reason other than gone (for example a timeout)
- **THEN** the report counts it as failed, not as skipped, and lists it with the reason, so the user can retry
