# Spec Delta

## MODIFIED Requirements

### Requirement: Filters
The pool SHALL be filterable by text in title or company and by state, including "noch nicht bewertet" (no rating from the user), "bewertet", "beworben" and "erledigt", and by origin ("Herkunft": imported postings of every status). The text filter, the state filter and the score range SHALL combine: a posting is listed only when it passes all three. "Filter zurücksetzen" SHALL reset all three and SHALL leave the sort as it is.

#### Scenario: Text filter
- **WHEN** the user types a company name into the text filter
- **THEN** only postings whose title or company contains it are listed

#### Scenario: Filters combine
- **WHEN** the state filter is "noch nicht bewertet", the score range is 7 to 9 and the text filter holds a company name
- **THEN** only unrated postings of that company with a score from 7 to 9 are listed

#### Scenario: Reset keeps the sort
- **WHEN** the pool is sorted by score and the user presses "Filter zurücksetzen"
- **THEN** the state filter, the text filter and the score range return to their defaults, and the pool stays sorted by score

### Requirement: Exploration mark
The filter "noch nicht bewertet" SHALL list the unrated postings by score and place about every fifth posting from the lower half of the scores into that list, marked "Stichprobe", so the system does not only confirm its own ranking. When too few low-scored postings exist, the remaining places SHALL go to the next highest-scored postings. Under a sort other than the ranking, these postings SHALL keep their mark and SHALL be ordered like every other posting.

#### Scenario: Exploration share
- **WHEN** the filter lists 10 unrated postings and enough low-scored ones exist
- **THEN** 2 of them are marked "Stichprobe"

#### Scenario: Sorted by score
- **WHEN** the filter "noch nicht bewertet" is sorted by score, descending
- **THEN** a "Stichprobe" posting scored 3 is listed below every posting scored higher, and still carries its mark

## ADDED Requirements

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

### Requirement: Range ends stay in order
The score range SHALL never end below its start: moving one end past the other SHALL move the other end with it.

#### Scenario: Start moved past the end
- **WHEN** the range is 3 to 5 and the user moves its start to 8
- **THEN** the range becomes 8 to 8

### Requirement: Postings without a score in the range
The step "ohne Score" SHALL select the postings a scoring pass would still score, whether or not the user rated them, including those whose stored score cannot be read. It SHALL NOT select excluded postings or postings the content guard holds. A range from "ohne Score" to a score below 10 SHALL list those postings and the postings scored up to that score.

#### Scenario: Only the unscored
- **WHEN** the user sets the range from "ohne Score" to "ohne Score"
- **THEN** every posting not yet scored is listed, rated ones included, and no excluded, held or scored posting is

#### Scenario: Unscored and low scores
- **WHEN** the user sets the range from "ohne Score" to 5
- **THEN** every posting not yet scored and every posting scored 0 to 5 is listed

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
A posting the user rates or scores in the pool SHALL keep its place in the shown order until the user changes the sort, the state filter or the score range, or the pool loads again. It SHALL stay listed until the user changes the state filter or the score range, even when it no longer matches them. A change of its application status SHALL still remove it from a list it no longer fits.

#### Scenario: Rated while sorted by rating
- **WHEN** the pool is sorted by rating and the user rates an unrated posting "Ja, auf jeden Fall"
- **THEN** the posting stays where it was listed until the user changes the sort, the state filter or the range, or the pool loads again

#### Scenario: Scored under "ohne Score"
- **WHEN** the range is "ohne Score" to "ohne Score" and the user scores one posting with its score button
- **THEN** the posting stays listed with its new score until the user changes the state filter or the range

#### Scenario: Pass finishes under "ohne Score"
- **WHEN** the range is "ohne Score" to "ohne Score" and a scoring pass finishes
- **THEN** the pool loads again, and the postings the pass scored are no longer listed, except those rated or scored by the user since the filter or the range last changed
