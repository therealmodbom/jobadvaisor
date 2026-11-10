# Spec Delta

## MODIFIED Requirements

### Requirement: Scoring pass on request
The pool SHALL offer a pass "Neue Anzeigen bewerten" that the user starts. It scores every posting without a score, and rescores every unrated posting when corrections were counted since the last pass. No pass SHALL start without the user's action. A pass SHALL announce how many postings it will score before it starts.

#### Scenario: New postings scored
- **WHEN** 12 postings are stored without a score and the user starts a pass
- **THEN** each receives a score and reasoning, stored with the posting

#### Scenario: Nothing starts by itself
- **WHEN** a posting is added by intake or import
- **THEN** it stays unscored until the user starts a pass or scores it

## ADDED Requirements

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

### Requirement: Single score only for postings the pool would score
A posting the content guard holds or an exclusion rule matches SHALL NOT be scored on request. A posting the content guard never checked SHALL be checked first when a classifier is configured, and refused when the check flags it; without a classifier, it SHALL NOT be scored on request. A posting already checked SHALL keep its stored guard result. Each refusal SHALL name its reason.

#### Scenario: Excluded posting
- **WHEN** the user asks to score a posting an exclusion rule matches
- **THEN** no score is computed, and the answer names the matching rules

#### Scenario: Held posting
- **WHEN** the user asks to score a posting the content guard flagged and nobody released
- **THEN** no score is computed, and the answer says the content guard holds it

#### Scenario: Unchecked posting with a classifier
- **WHEN** the user asks to score a posting the guard never checked and a classifier is configured
- **THEN** the posting is checked, the result is stored with it, and it is scored unless the check flags it

#### Scenario: Unchecked posting without a classifier
- **WHEN** the user asks to score a posting the guard never checked and no classifier is configured
- **THEN** no score is computed, and the answer says the posting was never checked

### Requirement: One scoring at a time
A single score SHALL NOT start while a pass computes, and a pass SHALL NOT start while a single score computes; each refusal SHALL say that another scoring is computing.

#### Scenario: Pass running
- **WHEN** the user asks to score a posting while a pass computes
- **THEN** no score is computed, and the answer says another scoring is computing

#### Scenario: Single score running
- **WHEN** the user starts a pass while a single score computes
- **THEN** the pass does not start, and the answer says another scoring is computing
