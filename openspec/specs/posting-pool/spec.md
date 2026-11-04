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
The pool SHALL offer a pass "Neue Anzeigen bewerten" that the user starts. It scores every posting without a score, and rescores every unrated posting when corrections were counted since the last pass. No pass SHALL start without the user's action. A pass SHALL announce how many postings it will score before it starts.

#### Scenario: New postings scored
- **WHEN** 12 postings are stored without a score and the user starts a pass
- **THEN** each receives a score and reasoning, stored with the posting

#### Scenario: Nothing starts by itself
- **WHEN** a posting is added by intake or import
- **THEN** it stays unscored until the user starts a pass

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
