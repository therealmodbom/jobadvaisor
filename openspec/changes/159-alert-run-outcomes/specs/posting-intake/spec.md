## MODIFIED Requirements

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

## ADDED Requirements

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
