# Spec Delta

## ADDED Requirements

### Requirement: Availability of a posting
Every posting SHALL carry an availability apart from its application status: available (the employer still shows it), closed (it is no longer open for applications) or unknown (the last check could not tell). The availability SHALL record when it was set and whether a check or the user set it. A posting never checked and never set by hand SHALL count as not closed.

#### Scenario: Never checked
- **WHEN** a posting was stored before any check ran
- **THEN** the pool lists it like an available posting, and its page says it was never checked

#### Scenario: Status and availability apart
- **WHEN** the user sets a posting with application status "beworben" to closed
- **THEN** its application status stays "beworben"

### Requirement: Availability check on request
The pool SHALL offer a check of availability that the user starts. No check SHALL start without the user's action. The check SHALL fetch the posting pages without any model call, SHALL report its progress while it runs, and SHALL report at its end how many postings it found available, closed and unknown, listing each posting it found closed.

#### Scenario: Check finds closed postings
- **WHEN** the user starts a check and 3 of the 20 postings it covers answer HTTP 404
- **THEN** those 3 are stored as closed, the report counts 3 closed, and it lists them

#### Scenario: Nothing starts by itself
- **WHEN** postings are added by intake or import, or the application starts
- **THEN** no check runs until the user starts one

### Requirement: One check at a time
The system SHALL run one check at a time. A request to start a check while one runs SHALL be refused, naming the running check. A check SHALL NOT wait for a scoring pass, and a pass SHALL NOT wait for a check.

#### Scenario: Second start refused
- **WHEN** a check runs and the user asks to start another
- **THEN** no second check starts, and the answer names the running one

### Requirement: What a check covers
A check SHALL cover every posting whose application status is open, whose availability is not closed, and whose availability the user did not set by hand. It SHALL leave every other posting as it is.

#### Scenario: Applied posting not checked
- **WHEN** a posting has the application status "beworben" and the user starts a check
- **THEN** the check does not fetch it and its availability stays as it was

#### Scenario: Closed posting not checked again
- **WHEN** a posting is closed and the user starts a check
- **THEN** the check does not fetch it

### Requirement: Closed by a gone link or a closed rule
A check SHALL find a posting closed when each of its stored links answers HTTP 404 or 410, redirects to an address a closed rule's redirect marker matches, or shows a page a closed rule's page text marker matches. It SHALL find it available when one of its links shows a page that no closed rule matches.

#### Scenario: LinkedIn redirect to a search page
- **WHEN** a posting's LinkedIn link redirects to an address containing "trk=expired_jd_redirect"
- **THEN** the check finds the posting closed

#### Scenario: Page still shows the posting
- **WHEN** a posting's link answers with its page and no closed rule matches
- **THEN** the check finds the posting available

### Requirement: Unknown never closes a posting
A check SHALL find a posting unknown when none of its links shows an available page and not every link answers closed: a rate limit (HTTP 429), a timeout, a refused or failed connection, any other HTTP error, or a link on a login-walled host, which the check does not fetch. An unknown result SHALL NOT close a posting, and the next check SHALL try it again.

#### Scenario: Rate limited
- **WHEN** a posting's link answers HTTP 429 during a check
- **THEN** the posting is stored as unknown, the report counts it as unknown, and the pool still lists it

#### Scenario: Login-walled link
- **WHEN** a posting's only link is on a login-walled host
- **THEN** the check does not fetch it and finds the posting unknown

### Requirement: Closed rules from code and policy pack
The system SHALL ship default closed rules, each naming a host and either a redirect marker or a page text marker, starting with LinkedIn's redirect marker "trk=expired_jd_redirect". The policy pack MAY hold further closed rules. They SHALL add to the defaults, never replace them. A rule's host SHALL match itself and its subdomains.

#### Scenario: Own rule adds to the defaults
- **WHEN** the policy pack holds a page text marker rule for one host
- **THEN** a check applies that rule to that host and still applies LinkedIn's default redirect marker

### Requirement: Hand setting of availability
The user SHALL be able to set a posting's availability to available or closed by hand. A check SHALL NOT change an availability the user set by hand.

#### Scenario: Wrongly closed posting reopened
- **WHEN** a check closed a posting the employer still lists, the user sets it to available, and the user starts another check
- **THEN** the posting stays available and the check does not fetch it

### Requirement: Closed postings leave the ranking
A closed posting SHALL NOT be listed by the pool's default view or by the states „noch nicht bewertet“ and „bewertet“. A scoring pass SHALL NOT score it, and the number a pass announces SHALL NOT count it. The exploration mark SHALL NOT pick it. The filter „geschlossen“ SHALL list every closed posting with application status open, and its page SHALL stay reachable.

#### Scenario: Pass skips a closed posting
- **WHEN** a closed posting has no score and the user starts „Anzeigen ohne Score scoren“
- **THEN** the pass does not score it, and the count the pass announced leaves it out

#### Scenario: Closed posting under its filter
- **WHEN** the user picks the filter „geschlossen“
- **THEN** the pool lists the closed postings with application status open, each in its rank order

### Requirement: Ratings of closed postings still count
A rating of a closed posting SHALL count like any rating: for the correction counter and as a rated example for scoring. The user SHALL be able to rate a closed posting and change its rating.

#### Scenario: Rating a closed posting
- **WHEN** the user rates a closed posting positive
- **THEN** the rating is stored, and a later pass can give it to the judge as a rated example
