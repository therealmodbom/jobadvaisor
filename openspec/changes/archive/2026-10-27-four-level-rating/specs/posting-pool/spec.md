# Spec Delta

## Purpose

Keeps every stored posting in one pool with its latest score, the user's rating and an application status, so the user can see at any time which postings fit best and are worth applying to, and can tell when the ranking needs a new scoring pass.

## ADDED Requirements

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
