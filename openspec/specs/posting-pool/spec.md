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
The pool SHALL rank postings by fit: postings the user rated positive first, then unrated postings by latest score, highest first; postings rated negative, excluded postings and postings held by the content guard last. Postings with application status "beworben" or "erledigt" SHALL be left out by default.

#### Scenario: Rated positive on top
- **WHEN** a posting scored 4 is rated positive and another scored 9 is unrated
- **THEN** the rated posting is listed above the unrated one

#### Scenario: Applied postings leave the ranking
- **WHEN** the user sets a posting to "beworben"
- **THEN** the default view no longer lists it, and a filter still shows it

### Requirement: Filters
The pool SHALL be filterable by text in title or company and by state, including "noch nicht bewertet" (no rating from the user), "bewertet", "beworben" and "erledigt", and by origin ("Herkunft": imported postings of every status).

#### Scenario: Text filter
- **WHEN** the user types a company name into the text filter
- **THEN** only postings whose title or company contains it are listed

### Requirement: Application status
Every posting SHALL carry an application status the user sets: open (the default), "beworben" or "erledigt". Only the user sets it, and it SHALL be stored in the data repository.

#### Scenario: Mark as applied
- **WHEN** the user marks a posting "beworben"
- **THEN** the status is stored and survives a restart

### Requirement: Scoring pass on request
The pool SHALL offer a pass "Neue Anzeigen bewerten" that the user starts. It scores every unrated posting without a score, and rescores every unrated posting when corrections were counted since the last pass. No pass SHALL start without the user's action. A pass SHALL announce how many postings it will score before it starts.

#### Scenario: New postings scored
- **WHEN** 12 postings are stored without a score and the user starts a pass
- **THEN** each receives a score and reasoning, stored with the posting

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
- **THEN** the pool's passes are unchanged, and the counter still counts from the start of that pass

### Requirement: Single score counts like any score
The correction counter SHALL treat a score computed on request like a pass's score: a rating that contradicts it, given before or after it, SHALL count as a correction within the counter's window.

#### Scenario: Probing a rated posting
- **WHEN** a posting rated positive since the last pass, without a score, is scored on request with 3
- **THEN** the counter rises by one

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
A correction SHALL be a rating whose verdict contradicts the posting's latest score: positive on a score below 6, or negative on a score of 6 or more. The pool SHALL show, since the start of the last finished pass, the number of corrections and the share of rated postings that were corrections. It SHALL show a hint "neue Bewertung sinnvoll" when the number reaches the user's threshold (default 10) or the share reaches the user's rate (default 30 %, counted from 10 rated postings on), and "Ranking passt gut" when neither does. A posting corrected several times counts once. Both settings SHALL be changeable in the app and stored in the data repository.

#### Scenario: Correction counted
- **WHEN** a posting with score 8 is rated negative
- **THEN** the counter rises by one

#### Scenario: Agreement is no correction
- **WHEN** a posting with score 8 is rated positive with an added chip
- **THEN** the counter stays as it was

#### Scenario: Threshold reached
- **WHEN** the counter reaches the threshold
- **THEN** the pool shows the hint "neue Bewertung sinnvoll", and the pass button stays usable below the threshold too

#### Scenario: Pass resets the counter
- **WHEN** a pass finishes and no rating was given while it computed
- **THEN** the counter and the share start again at zero

#### Scenario: Correction during a pass
- **WHEN** the user gives a correction while a pass computes
- **THEN** it counts toward the next pass after this one finishes, since this pass did not learn from it

#### Scenario: Few ratings
- **WHEN** fewer than 10 postings were rated since the last pass
- **THEN** the share alone triggers no hint

### Requirement: Quality measure per pass
Each pass SHALL store, with its time, the share of corrections among the ratings counted since the previous pass and the number of postings it scored, so the user and the evals can see whether the ranking improves.

#### Scenario: Two passes compared
- **WHEN** two passes finished
- **THEN** both stored shares are available for comparison

### Requirement: Exploration mark
The filter "noch nicht bewertet" SHALL list the unrated postings by score and place about every fifth posting from the lower half of the scores into that list, marked "Stichprobe", so the system does not only confirm its own ranking. When too few low-scored postings exist, the remaining places SHALL go to the next highest-scored postings.

#### Scenario: Exploration share
- **WHEN** the filter lists 10 unrated postings and enough low-scored ones exist
- **THEN** 2 of them are marked "Stichprobe"
