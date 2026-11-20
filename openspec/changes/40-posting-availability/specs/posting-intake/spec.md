# Spec Delta

## ADDED Requirements

### Requirement: Closed page at intake
Intake of a link SHALL treat its page as closed when the link answers HTTP 404 or 410 or redirects to an address a closed rule's redirect marker matches. It SHALL then store no posting and SHALL NOT look for the posting at another source. The answer SHALL say the posting is closed and list the attempts. This SHALL hold for a single link, several links, an import entry and an alert mail entry alike.

#### Scenario: Expired LinkedIn link
- **WHEN** the user submits a LinkedIn link that redirects to an address containing "trk=expired_jd_redirect"
- **THEN** no posting is stored, no other source is searched, and the answer says the posting is closed

#### Scenario: Expired link from an alert mail
- **WHEN** an alert mail entry the user adds redirects to an address containing "trk=expired_jd_redirect"
- **THEN** the run reports the entry as closed, not as failed, and no request is sent to the redirect target

#### Scenario: Gone single link
- **WHEN** the user submits a link that answers HTTP 404
- **THEN** no posting is stored, no other source is searched, and the answer says the posting is closed

### Requirement: Closed page text stored as closed
When the page of a submitted link shows the posting and a closed rule's page text marker matches it, intake SHALL store the posting with the availability closed, set by a check at the time of intake.

#### Scenario: Posting already filled
- **WHEN** the user submits a link whose page holds the posting text and a phrase a closed rule's page text marker names for that host
- **THEN** the posting is stored, closed, and the pool lists it only under „geschlossen“

## MODIFIED Requirements

### Requirement: Closed postings are not imported
The import SHALL skip an entry that is no longer available: the mapping gives its status as "überspringen", or its listed link answers that the page is gone (HTTP 404 or 410) or redirects to an address a closed rule's redirect marker matches, in which case the intake SHALL NOT look for the posting elsewhere. It SHALL store no posting content for a skipped entry. The report SHALL count the entries per outcome and SHALL list every entry it did not import (skipped by status, link gone or failed) with the text of its row, its link and the reason, so the user can follow it up.

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
