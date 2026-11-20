# Spec Delta

## ADDED Requirements

### Requirement: Availability of a posting
A posting SHALL have an availability apart from its application status: available (the employer still shows it), closed (it is no longer open for applications) or unknown (the last check could not tell). The availability SHALL record when it was set and whether a check or the user set it. A posting without one has never been checked and SHALL count as not closed.

#### Scenario: Never checked
- **WHEN** a posting was stored before any check ran
- **THEN** the pool lists it like an available posting, and its page says it was never checked

#### Scenario: Status and availability apart
- **WHEN** the user sets a posting with application status "beworben" to closed
- **THEN** its application status stays "beworben"

### Requirement: Availability check on request
The pool SHALL offer a check of availability that the user starts. No check SHALL start without the user's action. A check SHALL fetch the postings' pages without any model call.

#### Scenario: Nothing starts by itself
- **WHEN** postings are added by intake or import, or the application starts
- **THEN** no check runs until the user starts one

### Requirement: Report of a check
While a check runs, the system SHALL report how many of its postings are done. At its end it SHALL report how many postings it found available, closed and unknown, and SHALL list each posting it closed that was not closed before the check.

#### Scenario: Check finds closed postings
- **WHEN** the user starts a check and 3 of the 20 postings it covers answer HTTP 404
- **THEN** those 3 are stored as closed, the report counts 3 closed, and it lists them

#### Scenario: Already closed postings not listed again
- **WHEN** a check covers 2 postings that were already closed and 1 newly closed one, and all 3 links answer HTTP 404
- **THEN** the report counts 3 closed and lists only the newly closed one

### Requirement: One check at a time
The system SHALL run one check at a time. A request to start a check while one runs SHALL be refused, naming the running check. A check SHALL NOT wait for a scoring pass, and a pass SHALL NOT wait for a check.

#### Scenario: Second start refused
- **WHEN** a check runs and the user asks to start another
- **THEN** no second check starts, and the answer names the running one

### Requirement: Cancel a check
The user SHALL be able to cancel a running check. The check SHALL stop after the posting it works on, keep the availability it already stored, and end as cancelled with the report of what it found so far.

#### Scenario: Cancelled after some postings
- **WHEN** a check covering 20 postings has stored 8 results, 2 of them closed, and the user cancels it
- **THEN** it fetches no further posting, the 2 stay closed, the other 12 keep their earlier availability, and the check ends as cancelled reporting the 8

### Requirement: What a check covers
A check SHALL cover every posting whose application status is open and that has at least one stored link on a public host that is not login-walled, whatever its availability and whoever set it. It SHALL leave every other posting as it is.

#### Scenario: Applied posting not checked
- **WHEN** a posting has the application status "beworben" and the user starts a check
- **THEN** the check does not fetch it and its availability stays as it was

#### Scenario: Closed posting checked again
- **WHEN** a posting is closed, its link now shows the posting again, and the user starts a check
- **THEN** the check finds it available, and the pool lists it as open again

#### Scenario: Pasted posting not checked
- **WHEN** a posting was added as pasted text or a PDF and has no link
- **THEN** the check does not cover it, and it stays never checked

#### Scenario: Login-walled link
- **WHEN** a posting's only link is on a login-walled host
- **THEN** the check does not cover it, and its availability stays as it was

### Requirement: Closed by a gone link or a closed rule
A check SHALL find a posting closed when each of its links it fetches answers HTTP 404 or 410, redirects to an address a closed rule's redirect marker matches, or shows a page a closed rule's page text marker matches. It SHALL find it available when one of those links shows a page that no closed rule matches. A login-walled link SHALL be neither fetched nor counted.

#### Scenario: LinkedIn redirect to a search page
- **WHEN** a posting's LinkedIn link redirects to an address containing "trk=expired_jd_redirect"
- **THEN** the check finds the posting closed, and the address behind the redirect is never requested

#### Scenario: Page still shows the posting
- **WHEN** a posting's link answers with its page and no closed rule matches
- **THEN** the check finds the posting available

#### Scenario: One link still live
- **WHEN** a posting has two links, one answering HTTP 404 and the other showing the posting
- **THEN** the check finds the posting available

### Requirement: Unknown never closes a posting
A check SHALL find a posting unknown when none of its fetched links shows an available page and not every one answers closed, for example after a rate limit (HTTP 429), a timeout, a failed connection, a refused redirect or another HTTP error. An unknown result SHALL NOT close a posting, and the next check SHALL try it again.

#### Scenario: Rate limited
- **WHEN** a posting's link answers HTTP 429 during a check
- **THEN** the posting is stored as unknown, the report counts it as unknown, and the pool still lists it

#### Scenario: Gone and unreachable
- **WHEN** a posting has two links, one answering HTTP 404 and the other timing out
- **THEN** the check finds the posting unknown

### Requirement: Unknown never reopens a closed posting
When a check finds a closed posting unknown, the posting SHALL stay closed, with the record of who closed it and when. Only a link that shows an available page SHALL reopen a closed posting. The report SHALL count the posting as unknown.

#### Scenario: Closed posting rate limited
- **WHEN** a closed posting's link answers HTTP 429 during a check
- **THEN** the posting stays closed with its earlier record, the report counts it as unknown, and the pool still lists it only under „Stelle geschlossen“

### Requirement: Closed rules from code and policy pack
The system SHALL ship default closed rules, each naming a host and either a redirect marker or a page text marker, starting with LinkedIn's redirect marker "trk=expired_jd_redirect". The policy pack MAY hold further closed rules. They SHALL add to the defaults, never replace them. A rule's host SHALL match itself and its subdomains.

#### Scenario: Own rule adds to the defaults
- **WHEN** the policy pack holds a page text marker rule for one host
- **THEN** a check applies that rule to that host and still applies LinkedIn's default redirect marker

### Requirement: Page text marker reads the visible page
A page text marker SHALL match, ignoring case, against the text a reader sees on the page, and SHALL NOT match text that only appears in scripts or styles.

#### Scenario: Marker only in a script
- **WHEN** a page shows the posting and holds a page text marker's phrase only inside a script
- **THEN** the rule does not match

### Requirement: Hand setting of availability
The user SHALL be able to set a posting's availability to available or closed by hand, and change it by hand again at any time.

#### Scenario: Close by hand
- **WHEN** the user sets an available posting to closed
- **THEN** it is stored as closed, set by the user, and passes leave it out

### Requirement: A hand setting lasts until the next check
A hand setting SHALL NOT take a posting out of later checks. The next check that reaches the posting SHALL replace the hand setting with its own result, as for any other posting, except that an unknown result keeps a closed posting closed. A check SHALL NOT replace an availability the user set after that check started.

#### Scenario: Wrongly closed posting reopened
- **WHEN** a check closed a posting the employer still lists, the user sets it to available, and the user starts another check whose fetch of the link answers HTTP 404 again
- **THEN** the check fetches the posting and stores it as closed again

#### Scenario: Hand-closed posting still online
- **WHEN** the user closes a posting by hand whose page still shows it, and later starts a check
- **THEN** the check finds it available, stores it as set by the check, and the pool lists it as open again

#### Scenario: Set by hand during a check
- **WHEN** a check runs, the user sets a posting it covers to available before the check reaches it, and the posting's link answers HTTP 404
- **THEN** the posting stays available, set by the user, and the next check covers it again

### Requirement: Single score of a closed posting
The user SHALL be able to score a closed posting on request, like any posting that is neither excluded nor held.

#### Scenario: Closed posting scored on request
- **WHEN** the user scores a closed posting from its page
- **THEN** it receives a score and reasoning, stored with the posting, and it stays closed

### Requirement: A pass leaves closed postings out
A scoring pass of either variant SHALL NOT score a closed posting, and the number a pass announces SHALL NOT count it. A posting closed while the pass runs, before the pass reaches it, SHALL NOT be scored either.

#### Scenario: Unscored closed posting
- **WHEN** a closed posting has no score and the user starts „Anzeigen ohne Score scoren“
- **THEN** the pass does not score it, and the count the pass announced leaves it out

#### Scenario: Rescore everything
- **WHEN** a closed posting has a score and the user starts „Alle Anzeigen neu scoren“
- **THEN** the pass does not score it, and its stored score stays as it was

#### Scenario: Closed during a pass
- **WHEN** a pass runs, and a check or the user closes a posting in the pass's batch before the pass reaches it
- **THEN** the pass does not score that posting, counts it as done, and goes on with the next

### Requirement: No exploration mark on a closed posting
The exploration mark SHALL NOT pick a closed posting.

#### Scenario: Low-scored closed posting
- **WHEN** a closed, unrated posting has the lowest score in the pool
- **THEN** it carries no exploration mark

### Requirement: Ratings of closed postings still count
A rating of a closed posting SHALL count like any rating: for the correction counter and as a rated example for scoring. The user SHALL be able to rate a closed posting and change its rating.

#### Scenario: Rating a closed posting
- **WHEN** the user rates a closed posting positive
- **THEN** the rating is stored, the counter counts it, and a later pass can give it to the judge as a rated example

## MODIFIED Requirements

### Requirement: Ranking by fit
The pool SHALL rank postings by fit: postings the user rated positive first, then unrated postings by latest score, highest first; postings rated negative, excluded postings and postings held by the content guard last. Postings with application status "beworben" or "erledigt", and closed postings, SHALL be left out by default.

#### Scenario: Rated positive on top
- **WHEN** a posting scored 4 is rated positive and another scored 9 is unrated
- **THEN** the rated posting is listed above the unrated one

#### Scenario: Applied postings leave the ranking
- **WHEN** the user sets a posting to "beworben"
- **THEN** the default view no longer lists it, and a filter still shows it

#### Scenario: Closed postings leave the ranking
- **WHEN** a check finds an open posting closed
- **THEN** the default view no longer lists it, and the filter „geschlossen“ shows it in its rank order

### Requirement: Filters
The pool SHALL be filterable by text in title or company and by state, including "noch nicht bewertet" (no rating from the user), "bewertet", "beworben", "erledigt" and "geschlossen" (closed postings with application status open), and by origin ("Herkunft": imported postings of every status and availability). The states "noch nicht bewertet" and "bewertet" SHALL NOT list closed postings. The text filter, the state filter and the score range SHALL combine: a posting is listed only when it passes all three, except as "Changed postings keep their place" states. "Filter zurücksetzen" SHALL reset all three and SHALL leave the sort as it is.

#### Scenario: Text filter
- **WHEN** the user types a company name into the text filter
- **THEN** only postings whose title or company contains it are listed

#### Scenario: Filters combine
- **WHEN** the state filter is "noch nicht bewertet", the score range is 7 to 9 and the text filter holds a company name
- **THEN** only unrated postings of that company with a score from 7 to 9 are listed

#### Scenario: Reset keeps the sort
- **WHEN** the pool is sorted by score and the user presses "Filter zurücksetzen"
- **THEN** the state filter, the text filter and the score range return to their defaults, and the pool stays sorted by score

#### Scenario: Closed posting not unrated
- **WHEN** an unrated posting is closed and the user picks "noch nicht bewertet"
- **THEN** it is not listed, and "geschlossen" lists it

### Requirement: Scoring pass on request
The pool SHALL offer a pass that the user starts, in one of two variants. „Anzeigen ohne Score scoren“ scores every posting without a score, rated or not. „Alle Anzeigen neu scoren“ scores every posting, rated or not, with or without a score. Neither variant SHALL score a posting an exclusion rule matches, the content guard holds, or that is closed. No pass SHALL start without the user's action. A pass SHALL announce how many postings it will score before it starts.

#### Scenario: New postings scored
- **WHEN** 12 postings, neither excluded nor held nor closed, are stored without a score and the user starts „Anzeigen ohne Score scoren“
- **THEN** each receives a score and reasoning, stored with the posting

#### Scenario: Rated posting without a score
- **WHEN** a posting the user rated before any pass scored it, neither excluded nor held nor closed, is stored without a score, and the user starts a pass
- **THEN** it receives a score, and the posting itself is not among the examples its judge was given

#### Scenario: Rescore everything on request
- **WHEN** no correction was counted and the user starts „Alle Anzeigen neu scoren“
- **THEN** every posting neither excluded nor held nor closed receives a new score, the rated ones included

#### Scenario: Rescore after corrections
- **WHEN** the corrections reached the threshold and the user starts the default variant
- **THEN** every posting neither excluded nor held nor closed receives a new score, the rated ones included

#### Scenario: Corrections do not widen a pass
- **WHEN** corrections were counted, the hint says „Ranking passt gut“, and the user starts „Anzeigen ohne Score scoren“
- **THEN** only the postings without a score receive one, and every stored score stays as it was

#### Scenario: Rating during a pass
- **WHEN** the user rates a posting while a pass computes its score
- **THEN** the pass stores that score, and the rating counts toward the counter after this pass

#### Scenario: Nothing starts by itself
- **WHEN** a posting is added by intake or import
- **THEN** it stays unscored until the user starts a pass or scores it

### Requirement: Postings without a score in the range
The step "ohne Score" SHALL select the postings that have no readable score, whether or not the user rated them, including those whose stored score cannot be read. It SHALL NOT select excluded postings or postings the content guard holds. A range from "ohne Score" to a score below 10 SHALL list those postings and the postings scored up to that score.

#### Scenario: Only the unscored
- **WHEN** the user sets the range from "ohne Score" to "ohne Score"
- **THEN** every posting not yet scored is listed, rated ones included, and no excluded, held or scored posting is

#### Scenario: Unscored and low scores
- **WHEN** the user sets the range from "ohne Score" to 5
- **THEN** every posting not yet scored and every posting scored 0 to 5 is listed

#### Scenario: Closed and unscored
- **WHEN** the state filter is "geschlossen" and the range is "ohne Score" to "ohne Score"
- **THEN** the closed postings without a score are listed

### Requirement: Default pass variant
The default pass variant SHALL be „Alle Anzeigen neu scoren“ while the pool shows the hint „neu scoren sinnvoll“, and „Anzeigen ohne Score scoren“ otherwise. Corrections SHALL change the default only through the hint.

#### Scenario: One correction below the threshold
- **WHEN** the threshold is 10, one correction is counted, and 3 of 40 postings, neither excluded nor held nor closed, have no score
- **THEN** the default is „Anzeigen ohne Score scoren“, announced with 3 postings

#### Scenario: Threshold reached
- **WHEN** the counter reaches the threshold and 40 postings are neither excluded nor held nor closed
- **THEN** the default is „Alle Anzeigen neu scoren“, announced with 40 postings
