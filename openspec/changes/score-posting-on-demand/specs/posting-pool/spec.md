# Spec Delta

## MODIFIED Requirements

### Requirement: Scoring pass on request
The pool SHALL offer a pass "Neue Anzeigen bewerten" that the user starts. It scores every posting without a score, rated or not, and rescores every posting, rated or not, when corrections were counted since the last pass. It SHALL NOT score a posting an exclusion rule matches or the content guard holds. No pass SHALL start without the user's action. A pass SHALL announce how many postings it will score before it starts.

#### Scenario: New postings scored
- **WHEN** 12 postings, neither excluded nor held, are stored without a score and the user starts a pass
- **THEN** each receives a score and reasoning, stored with the posting

#### Scenario: Rated posting without a score
- **WHEN** a posting the user rated before any pass scored it, neither excluded nor held, is stored without a score, and the user starts a pass
- **THEN** it receives a score, and the posting itself is not among the examples its judge was given

#### Scenario: Rescore after corrections
- **WHEN** corrections were counted since the last pass and the user starts a pass
- **THEN** every posting neither excluded nor held receives a new score, the rated ones included

#### Scenario: Rating during a pass
- **WHEN** the user rates a posting while a pass computes its score
- **THEN** the pass stores that score, and the rating counts toward the counter after this pass

#### Scenario: Nothing starts by itself
- **WHEN** a posting is added by intake or import
- **THEN** it stays unscored until the user starts a pass or scores it

### Requirement: Quality measure per pass
Each pass SHALL store, with its time, the share of corrections among the ratings counted since the previous pass and the number of postings it scored, so the user and the evals can see whether the ranking improves. The share SHALL be measured against the scores from before the pass, not against the scores it writes.

#### Scenario: Two passes compared
- **WHEN** two passes finished
- **THEN** both stored shares are available for comparison

#### Scenario: Rescored rated posting
- **WHEN** a posting with score 8 was rated negative since the previous pass, and the pass rescores it with 2
- **THEN** the share the pass stores counts that rating as a correction

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
