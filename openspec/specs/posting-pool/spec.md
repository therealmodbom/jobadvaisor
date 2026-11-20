# posting-pool Specification

## Purpose
Keeps every stored posting in one pool with its latest score, the user's rating and an application status, so the user can see at any time which postings fit best and are worth applying to, and can tell when the ranking needs a new scoring pass.

## Requirements

### Requirement: Ranking by strength of a positive rating
Among the postings the user rated positive, the pool SHALL rank "ja, auf jeden Fall" above "ja, vielleicht", and a positive rating without a strength between the two; within one level the order SHALL be as before. A strength SHALL NOT move any posting between the groups of the ranking: the direction of the rating alone puts it among the rated-positive or the rated-negative postings. The correction counter and the postings listed as best open SHALL use the direction alone.

#### Scenario: Strong above weak
- **WHEN** a posting scored 3 is rated "ja, auf jeden Fall" and another scored 9 is rated "ja, vielleicht"
- **THEN** the pool lists the first above the second, and both above every unrated posting

#### Scenario: Rating without strength
- **WHEN** a posting is rated positive without a strength
- **THEN** it is listed below every "ja, auf jeden Fall" and above every "ja, vielleicht"

#### Scenario: Weak negative still last
- **WHEN** a posting is rated "nein, eher nicht"
- **THEN** it is listed with the postings rated negative, below every unrated scored posting, and the best-open list leaves it out

#### Scenario: Counter ignores strength
- **WHEN** a posting scored 8 is rated "nein, eher nicht"
- **THEN** it counts as one correction, as a plain negative would

### Requirement: One pool of all stored postings
The system SHALL list every stored posting in one pool, with title, company, location, its state, its latest score and the user's rating with chips and note. The state SHALL be one of: scored, not yet scored, excluded (naming the rule), or held by the content guard. Each posting SHALL have its own address and page that shows the full text, the link to the original, the score with its reasoning and the rating.

#### Scenario: Posting without a run
- **WHEN** a posting was scored in an earlier pass and the user opens the pool later
- **THEN** the pool shows it with its stored score and reasoning

#### Scenario: Page per posting
- **WHEN** the user opens a posting's address
- **THEN** the page shows its full text, its original link, its score, reasoning and rating

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

### Requirement: Application status
Every posting SHALL carry an application status the user sets: open (the default), "beworben" or "erledigt". Only the user sets it, and it SHALL be stored in the data repository.

#### Scenario: Mark as applied
- **WHEN** the user marks a posting "beworben"
- **THEN** the status is stored and survives a restart

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

### Requirement: Scoring one posting on request
The user SHALL be able to score one stored posting on request, rated or not, with or without a score. It SHALL be scored the way a pass scores it, with one judge call, and stored with the posting like a pass's score, replacing an earlier one. It SHALL NOT count as a pass: no pass is recorded, and the correction counter keeps its window.

#### Scenario: Rated posting without a score
- **WHEN** the user scores a posting rated before any pass scored it
- **THEN** it receives a score and reasoning, stored with the posting, and the posting itself is not among the examples the judge was given

#### Scenario: Score replaced
- **WHEN** the user scores a posting that already has a score
- **THEN** the new score and reasoning replace the old ones

#### Scenario: No pass recorded
- **WHEN** a single posting is scored after a pass
- **THEN** the pool's passes are unchanged, and the counter window stays where it was

### Requirement: Single score counts like any score
The correction counter SHALL treat a score computed on request like a pass's score: a rating that contradicts it, given before or after it, SHALL count as a correction within the counter's window.

#### Scenario: Probing a rated posting
- **WHEN** a posting rated positive within the counter window, without a score, is scored on request with 3
- **THEN** the counter rises by one

#### Scenario: Re-scoring a corrected posting
- **WHEN** a posting rated negative with a score of 8, which counts as a correction, is scored on request with 2
- **THEN** the counter falls by one, since a correction is measured against the latest score

### Requirement: Single score refuses held and excluded postings
A posting the content guard holds or an exclusion rule matches SHALL NOT be scored on request. The refusal SHALL name its reason: the matching rules, or that the content guard holds it; when both apply, it SHALL name the content guard.

#### Scenario: Excluded posting
- **WHEN** the user asks to score a posting an exclusion rule matches and the content guard does not hold
- **THEN** no score is computed, and the answer names the matching rules

#### Scenario: Held posting
- **WHEN** the user asks to score a posting the content guard flagged and nobody released
- **THEN** no score is computed, and the answer says the content guard holds it

#### Scenario: Held and excluded posting
- **WHEN** the user asks to score a posting the content guard holds and an exclusion rule matches
- **THEN** no score is computed, and the answer says the content guard holds it

### Requirement: Single score checks an unchecked posting first
A posting the content guard never checked SHALL be checked before it is scored on request, when a classifier is configured, and SHALL NOT be scored when that check flags it. Without a classifier it SHALL NOT be scored on request, and the refusal SHALL say it was never checked. A posting already checked SHALL keep its stored guard result and SHALL NOT be checked again.

#### Scenario: Unchecked posting with a classifier
- **WHEN** the user asks to score a posting the guard never checked and no exclusion rule matches, a classifier is configured, and the check does not flag it
- **THEN** the result is stored with it, and the posting is scored

#### Scenario: Unchecked posting flagged by that check
- **WHEN** the user asks to score a posting the guard never checked and no exclusion rule matches, and the check flags it
- **THEN** the result is stored with it, no score is computed, and the answer says the content guard holds it

#### Scenario: Unchecked posting without a classifier
- **WHEN** the user asks to score a posting the guard never checked and no exclusion rule matches, and no classifier is configured
- **THEN** no score is computed, and the answer says the posting was never checked

#### Scenario: Checked posting
- **WHEN** the user asks to score a posting the guard already checked and did not flag, and no exclusion rule matches
- **THEN** the guard is not called again, and the posting is scored

### Requirement: One scoring at a time
No scoring SHALL start while another computes: neither a pass nor a single score while a pass or a single score computes. Each refusal SHALL say that another scoring is computing.

#### Scenario: Pass running
- **WHEN** the user asks to score a posting while a pass computes
- **THEN** no score is computed, and the answer says another scoring is computing

#### Scenario: Single score running
- **WHEN** the user starts a pass while a single score computes
- **THEN** the pass does not start, and the answer says another scoring is computing

#### Scenario: Second single score
- **WHEN** the user asks to score a second posting while the score of a first one computes
- **THEN** no score is computed for the second, and the answer says another scoring is computing

### Requirement: Correction counter and hints
A correction SHALL be a rating whose verdict contradicts the posting's latest score: positive on a score below 6, or negative on a score of 6 or more. Within the counter window the pool SHALL show the number of corrections and their share of rated postings; a posting corrected several times counts once. The hint SHALL read „neu scoren sinnvoll“ when the number reaches the user's threshold (default 10) or the share the user's rate (default 30 %, from 10 rated postings on), else „Ranking passt gut“. Both settings SHALL be changeable in the app and stored in the data repository.

#### Scenario: Correction counted
- **WHEN** a posting with score 8 is rated negative
- **THEN** the counter rises by one

#### Scenario: Agreement is no correction
- **WHEN** a posting with score 8 is rated positive with an added chip
- **THEN** the counter stays as it was

#### Scenario: Threshold reached
- **WHEN** the counter reaches the threshold
- **THEN** the pool shows the hint „neu scoren sinnvoll“, and both pass variants stay usable below the threshold too

#### Scenario: Pass resets the counter
- **WHEN** a pass „Alle Anzeigen neu scoren“ finishes without being cancelled, and no rating was given while it computed
- **THEN** the counter and the share start again at zero

#### Scenario: Correction during a pass
- **WHEN** the user rates a posting while a pass computes its score
- **THEN** the pass stores its new score, and the rating counts after this pass against that score, as a correction only if it contradicts it

#### Scenario: Few ratings
- **WHEN** fewer than 10 postings were rated within the counter window
- **THEN** the share alone triggers no hint

### Requirement: Quality measure per pass
Each pass SHALL store, with its time and its variant, the share of corrections among the ratings counted within the counter window and the number of postings it scored, so the user and the evals can see whether the ranking improves. The share SHALL be measured against the scores from before the pass, not against the scores it writes.

#### Scenario: Two passes compared
- **WHEN** two passes finished
- **THEN** both stored shares are available for comparison

#### Scenario: Rescored rated posting
- **WHEN** a posting with score 8 was rated negative within the counter window, and the pass rescores it with 2
- **THEN** the share the pass stores counts that rating as a correction

#### Scenario: Variant recorded
- **WHEN** a pass „Anzeigen ohne Score scoren“ finishes and scored at least one posting
- **THEN** its stored record names that variant

### Requirement: Exploration mark
The filter "noch nicht bewertet" SHALL list the unrated postings by score and place about every fifth posting from the lower half of the scores into that list, marked "Stichprobe", so the system does not only confirm its own ranking. When too few low-scored postings exist, the remaining places SHALL go to the next highest-scored postings. Under a sort other than the ranking, these postings SHALL keep their mark and SHALL be ordered like every other posting.

#### Scenario: Exploration share
- **WHEN** the filter lists 10 unrated postings and enough low-scored ones exist
- **THEN** 2 of them are marked "Stichprobe"

#### Scenario: Sorted by score
- **WHEN** the filter "noch nicht bewertet" is sorted by score, descending
- **THEN** a "Stichprobe" posting scored 3 is listed below every posting scored higher, and still carries its mark

### Requirement: Score range
The pool SHALL offer a score range with the steps "ohne Score", then 0 to 10. A range from one score to another SHALL list the postings whose score lies between both, inclusive. A range that starts at 0 or higher SHALL hide every posting without a score. An excluded or held posting SHALL count as having no score, even when a score is stored for it.

#### Scenario: Score band
- **WHEN** the user sets the range from 7 to 9
- **THEN** postings scored 7, 8 and 9 are listed, and postings scored 6 or 10 or without a score are not

#### Scenario: Zero is a score
- **WHEN** the user sets the range from 0 to 0
- **THEN** postings scored 0 are listed, and postings without a score are not

#### Scenario: Excluded with a stored score
- **WHEN** a posting was scored 8 before an exclusion rule matched it, and the user sets the range from 7 to 9
- **THEN** that posting is not listed

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

### Requirement: Full range hides nothing
The range SHALL be at its full extent, from "ohne Score" to 10, by default and after a reload. At its full extent it SHALL hide no posting, excluded and held postings included.

#### Scenario: Default range
- **WHEN** the user opens the pool
- **THEN** the range spans "ohne Score" to 10, and the pool lists every posting the state and text filters let through

### Requirement: Sort choice
The pool SHALL offer a sort by the ranking (the default), by score, by the user's own rating and by the date a posting was added, each but the ranking ascending and descending. The sort SHALL apply to every state filter and SHALL return to the ranking after a reload. The requirements on the ranking describe the order under the sort by the ranking.

#### Scenario: Newest first
- **WHEN** the user sorts by added date, descending
- **THEN** the posting added last is listed first

#### Scenario: Back to the ranking
- **WHEN** the user picks the ranking again after another sort
- **THEN** the pool lists the postings in the server's rank order

### Requirement: Order of the own rating
Sorted by the user's own rating, descending, the order SHALL be "Ja, auf jeden Fall", "Ja" without a strength, "Ja, vielleicht", "Nein, eher nicht", "Nein" without a strength, "Nein, auf keinen Fall". Ascending SHALL reverse it.

#### Scenario: Rating descending
- **WHEN** postings rated "Nein, eher nicht", "Ja, auf jeden Fall" and "Ja" without a strength are sorted by rating, descending
- **THEN** they are listed as "Ja, auf jeden Fall", "Ja", "Nein, eher nicht"

### Requirement: Postings without a value come last
Under a sort by score or by rating, postings without a value for that key SHALL be listed after all others, in both directions. An excluded or held posting SHALL count as having no score, and a posting whose label holds no verdict SHALL count as unrated.

#### Scenario: Unscored last, ascending
- **WHEN** the pool is sorted by score, ascending
- **THEN** the lowest-scored posting is listed first, and every posting without a score after every scored one

#### Scenario: Unrated last, descending
- **WHEN** the pool is sorted by rating, descending
- **THEN** every unrated posting is listed after every rated one

### Requirement: Ties keep the ranking
Postings with the same value for the sort key SHALL keep their order from the ranking, in both directions.

#### Scenario: Equal scores
- **WHEN** two postings scored 7 are sorted by score, ascending and then descending
- **THEN** both times they are listed in the order the ranking gives them

### Requirement: Changed postings keep their place
A posting the user rates or scores in the pool SHALL keep its place in the shown order until the user changes the sort, the state filter or the score range, or the pool loads again. It SHALL stay listed until the user changes the state filter or the score range, even when it no longer matches them. The text filter SHALL still apply to it, and a change of its application status SHALL still remove it from a list it no longer fits.

#### Scenario: Rated while sorted by rating
- **WHEN** the pool is sorted by rating and the user rates an unrated posting "Ja, auf jeden Fall"
- **THEN** the posting stays where it was listed until the user changes the sort, the state filter or the range, or the pool loads again

#### Scenario: Scored under "ohne Score"
- **WHEN** the range is "ohne Score" to "ohne Score" and the user scores one posting with its score button
- **THEN** the posting stays listed with its new score until the user changes the state filter or the range

#### Scenario: Text filter still applies
- **WHEN** a posting stays listed under "ohne Score" after the user scored it, and the user types a text that neither its title nor its company contains
- **THEN** the posting is no longer listed

#### Scenario: Pass finishes under "ohne Score"
- **WHEN** the range is "ohne Score" to "ohne Score" and a scoring pass finishes
- **THEN** the pool loads again, and the postings the pass scored are no longer listed, except those rated or scored by the user since the filter or the range last changed

### Requirement: Range ends stay in order
The score range SHALL never end below its start: moving one end past the other SHALL move the other end with it.

#### Scenario: Start moved past the end
- **WHEN** the range is 3 to 5 and the user moves its start to 8
- **THEN** the range becomes 8 to 8

### Requirement: Default pass variant
The default pass variant SHALL be „Alle Anzeigen neu scoren“ while the pool shows the hint „neu scoren sinnvoll“, and „Anzeigen ohne Score scoren“ otherwise. Corrections SHALL change the default only through the hint.

#### Scenario: One correction below the threshold
- **WHEN** the threshold is 10, one correction is counted, and 3 of 40 postings, neither excluded nor held nor closed, have no score
- **THEN** the default is „Anzeigen ohne Score scoren“, announced with 3 postings

#### Scenario: Threshold reached
- **WHEN** the counter reaches the threshold and 40 postings are neither excluded nor held nor closed
- **THEN** the default is „Alle Anzeigen neu scoren“, announced with 40 postings

### Requirement: Counter window
The counter window SHALL start at the start of the last pass „Alle Anzeigen neu scoren“ that finished without being cancelled, and without one it SHALL hold every rating. A pass „Anzeigen ohne Score scoren“ and a cancelled pass of either variant SHALL leave the window as it is. A stored pass record without a variant SHALL count as a pass over all postings.

#### Scenario: Pass over postings without a score keeps the counter
- **WHEN** 4 corrections are counted and a pass „Anzeigen ohne Score scoren“ finishes that scored no rated posting
- **THEN** the counter still shows 4 corrections

#### Scenario: Pass record from before variants
- **WHEN** the last stored pass record names no variant
- **THEN** the window starts at that pass's start

#### Scenario: Cancelled pass over all postings keeps the window
- **WHEN** the window starts at a pass that finished on Monday, and a pass „Alle Anzeigen neu scoren“ is cancelled on Tuesday after it scored 30 postings
- **THEN** the window still starts at Monday's pass, and the counter measures its ratings against the latest scores, the 30 new ones included

### Requirement: Pass progress per posting
While a pass runs, the pool SHALL report its phase: checking, scoring or storing. While it scores it SHALL also report how many postings are done out of how many, updated after every posting, not only when the phase ends.

#### Scenario: Progress moves per posting
- **WHEN** a pass scores 80 postings and has finished 12
- **THEN** the pool reports the phase as scoring, with 12 of 80 done

#### Scenario: Restart during a pass
- **WHEN** the server restarts while a pass runs
- **THEN** the pool reports the pass as failed, without progress

### Requirement: Progress counts only postings a model sees
Postings an exclusion rule matches or the content guard holds SHALL NOT count in the progress. A posting whose scoring failed SHALL count as done.

#### Scenario: Excluded postings not counted
- **WHEN** a pass takes 100 postings, of which 15 are excluded and 5 held
- **THEN** the count runs up to 80

#### Scenario: Flagged while the pass waited
- **WHEN** a pass that waited for the answer about unscreened postings goes on with 80 postings, and one of them was flagged meanwhile
- **THEN** that posting gets no model call, and the count runs up to 79

#### Scenario: Failed scoring
- **WHEN** scoring one of 80 postings fails
- **THEN** the count ends at 80 of 80, and that posting gets no new score

### Requirement: Cancel a running pass
The user SHALL be able to cancel a running pass. It SHALL stop after the posting it is working on, in any phase, and SHALL store every score computed until then. Postings it did not reach SHALL keep their earlier score, or stay without one. Until it has stopped, the pool SHALL report that a cancel was requested.

#### Scenario: Cancel during scoring
- **WHEN** a pass has scored 30 of 80 postings, and the user cancels it while it scores the 31st
- **THEN** the pass stops once the 31st is scored, those 31 scores are stored, and the other 49 postings keep the score they had before the pass

#### Scenario: Cancel during checking
- **WHEN** the user cancels a pass while it checks
- **THEN** the pass stops after the current posting, and no score is stored

#### Scenario: Cancel requested
- **WHEN** the user cancels a pass while a model call for a posting is still open
- **THEN** the pool reports the pass as running with a cancel requested, until that call has ended and the pass has stopped

#### Scenario: Cancel while storing
- **WHEN** the user cancels a pass that has reached the storing phase
- **THEN** the pass stores every score and ends as a complete pass

#### Scenario: Cancel during the last posting
- **WHEN** the user cancels a pass while it scores its last posting
- **THEN** the pass stores every score and ends as a complete pass

#### Scenario: Cancel before the unscreened question
- **WHEN** the user cancels a pass while it checks, and the pass holds postings the content guard never checked
- **THEN** the pass ends as cancelled without asking about them, and no score is stored

### Requirement: Cancel only a running pass
A cancel SHALL be refused for a pass that is not running: one that waits for the answer about unscreened postings or has ended. The refusal SHALL say that the pass is not running. A cancel for an unknown pass, or for a single score, SHALL be refused as unknown.

#### Scenario: Pass waiting for an answer
- **WHEN** the user cancels a pass that asks about unscreened postings
- **THEN** the pass is not cancelled, and the answer says it is not running

#### Scenario: Pass already ended
- **WHEN** the user cancels a pass that has ended
- **THEN** nothing changes, and the answer says it is not running

#### Scenario: Single score
- **WHEN** a cancel names a single score that is computing
- **THEN** the score goes on, and the answer says the pass is unknown

### Requirement: Record of a cancelled pass
A cancelled pass that scored at least one posting SHALL be recorded like a finished pass, with its variant, the number of postings it scored and its share of corrections, and SHALL be marked as cancelled. A cancelled pass that scored no posting SHALL NOT be recorded.

#### Scenario: Cancelled after some scores
- **WHEN** a pass „Alle Anzeigen neu scoren“ is cancelled after it scored 30 postings
- **THEN** the pool's passes hold a record of it with 30 scored, marked as cancelled

#### Scenario: Cancelled before any score
- **WHEN** a pass is cancelled while it checks
- **THEN** the pool's passes are unchanged

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
While a check runs, the system SHALL report how many of its postings are done. At its end it SHALL report how many postings it found available, closed and unknown, and SHALL list each posting it found closed.

#### Scenario: Check finds closed postings
- **WHEN** the user starts a check and 3 of the 20 postings it covers answer HTTP 404
- **THEN** those 3 are stored as closed, the report counts 3 closed, and it lists them

### Requirement: One check at a time
The system SHALL run one check at a time. A request to start a check while one runs SHALL be refused, naming the running check. A check SHALL NOT wait for a scoring pass, and a pass SHALL NOT wait for a check.

#### Scenario: Second start refused
- **WHEN** a check runs and the user asks to start another
- **THEN** no second check starts, and the answer names the running one

### Requirement: What a check covers
A check SHALL cover every posting whose application status is open, whose availability is not closed and not set by the user, and that has at least one stored link on a host that is not login-walled. It SHALL leave every other posting as it is.

#### Scenario: Applied posting not checked
- **WHEN** a posting has the application status "beworben" and the user starts a check
- **THEN** the check does not fetch it and its availability stays as it was

#### Scenario: Closed posting not checked again
- **WHEN** a posting is closed and the user starts a check
- **THEN** the check does not fetch it

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
The user SHALL be able to set a posting's availability to available or closed by hand, and change a hand setting by hand again. A check SHALL NOT change an availability the user set by hand, also when the user set it while the check ran.

#### Scenario: Wrongly closed posting reopened
- **WHEN** a check closed a posting the employer still lists, the user sets it to available, and the user starts another check
- **THEN** the posting stays available and the check does not fetch it

#### Scenario: Set by hand during a check
- **WHEN** a check runs, the user sets a posting it covers to available before the check reaches it, and the posting's link answers HTTP 404
- **THEN** the posting stays available, set by the user

### Requirement: Hand setting returned to the check
The user SHALL be able to remove a hand setting. The posting then counts as never checked, and the next check SHALL cover it again.

#### Scenario: Reopened posting checked again
- **WHEN** the user set a posting to available by hand, later removes the hand setting, and starts a check whose fetch of the posting's link answers HTTP 404
- **THEN** the check finds the posting closed

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

### Requirement: Cancel a check
The user SHALL be able to cancel a running check. The check SHALL stop after the posting it works on, keep the availability it already stored, and end as cancelled with the report of what it found so far.

#### Scenario: Cancelled after some postings
- **WHEN** a check covering 20 postings has stored 8 results, 2 of them closed, and the user cancels it
- **THEN** it fetches no further posting, the 2 stay closed, the other 12 keep their earlier availability, and the check ends as cancelled reporting the 8
