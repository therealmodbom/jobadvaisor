# Spec Delta

## ADDED Requirements

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

## MODIFIED Requirements

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
