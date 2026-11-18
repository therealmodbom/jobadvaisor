# Spec Delta

## MODIFIED Requirements

### Requirement: Scoring pass on request
The pool SHALL offer a pass that the user starts, in one of two variants. „Anzeigen ohne Score scoren“ scores every posting without a score, rated or not. „Alle Anzeigen neu scoren“ scores every posting, rated or not, with or without a score. Neither variant SHALL score a posting an exclusion rule matches or the content guard holds. No pass SHALL start without the user's action. A pass SHALL announce how many postings it will score before it starts.

#### Scenario: New postings scored
- **WHEN** 12 postings, neither excluded nor held, are stored without a score and the user starts „Anzeigen ohne Score scoren“
- **THEN** each receives a score and reasoning, stored with the posting

#### Scenario: Rated posting without a score
- **WHEN** a posting the user rated before any pass scored it, neither excluded nor held, is stored without a score, and the user starts a pass
- **THEN** it receives a score, and the posting itself is not among the examples its judge was given

#### Scenario: Rescore everything on request
- **WHEN** no correction was counted and the user starts „Alle Anzeigen neu scoren“
- **THEN** every posting neither excluded nor held receives a new score, the rated ones included

#### Scenario: Rescore after corrections
- **WHEN** the corrections reached the threshold and the user starts the default variant
- **THEN** every posting neither excluded nor held receives a new score, the rated ones included

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
- **WHEN** a pass „Alle Anzeigen neu scoren“ finishes and no rating was given while it computed
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

## ADDED Requirements

### Requirement: Default pass variant
The default pass variant SHALL be „Alle Anzeigen neu scoren“ while the pool shows the hint „neu scoren sinnvoll“, and „Anzeigen ohne Score scoren“ otherwise. Corrections SHALL change the default only through the hint.

#### Scenario: One correction below the threshold
- **WHEN** the threshold is 10, one correction is counted, and 3 of 40 postings, neither excluded nor held, have no score
- **THEN** the default is „Anzeigen ohne Score scoren“, announced with 3 postings

#### Scenario: Threshold reached
- **WHEN** the counter reaches the threshold and 40 postings are neither excluded nor held
- **THEN** the default is „Alle Anzeigen neu scoren“, announced with 40 postings

### Requirement: Counter window
The counter window SHALL start at the start of the last finished pass „Alle Anzeigen neu scoren“, and without one it SHALL hold every rating. A pass „Anzeigen ohne Score scoren“ SHALL leave the window as it is. A stored pass record without a variant SHALL count as a pass over all postings.

#### Scenario: Pass over postings without a score keeps the counter
- **WHEN** 4 corrections are counted and a pass „Anzeigen ohne Score scoren“ finishes that scored no rated posting
- **THEN** the counter still shows 4 corrections

#### Scenario: Pass record from before variants
- **WHEN** the last stored pass record names no variant
- **THEN** the window starts at that pass's start
