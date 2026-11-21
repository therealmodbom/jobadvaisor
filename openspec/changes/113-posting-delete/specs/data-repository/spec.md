# Spec Delta

## ADDED Requirements

### Requirement: Deletion leaves the repository valid
Deleting a posting SHALL remove every file and entry keyed by its ID: `postings/<id>.json`, `labels/<id>.json`, `scores/<id>.json` and its key in `extraction-labels.json`. The data repository SHALL load without a problem afterwards. A backup SHALL NOT see half a deletion. The next backup SHALL commit the removed files, counted by kind like any other change.

#### Scenario: Hand-settled values removed
- **WHEN** a posting with an entry in `extraction-labels.json` is deleted
- **THEN** the entry is gone, every other entry stays, and the data repository loads

#### Scenario: Backup after a delete
- **WHEN** a posting with a rating and a score is deleted and a backup runs
- **THEN** the commit removes the three files, and its message names 1 rating, 1 score and 1 posting
