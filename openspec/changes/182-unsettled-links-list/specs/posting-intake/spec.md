## MODIFIED Requirements

### Requirement: Handled mails
A mail SHALL count as handled as soon as the finder has read it and returned no entry. A mail in a pick list SHALL count as handled once the pick list is finished; with a link in the alert run, once that run has started, whatever the outcomes of its links. A mail whose reading failed, or that no model could read because screening is off, SHALL NOT count as handled. The links of a run that end unsettled stay in the list of unsettled links („Unsettled links kept in a list“), not with their mail.

#### Scenario: Pick list not finished
- **WHEN** a check offers postings from three mails and the user leaves without finishing the pick list
- **THEN** none of the three counts as handled

#### Scenario: Mail without postings
- **WHEN** the finder reads a mail and returns no entry
- **THEN** that mail counts as handled at once

#### Scenario: Reading failed
- **WHEN** the model call fails while a check reads a mail
- **THEN** that mail does not count as handled

#### Scenario: Every entry stored
- **WHEN** the user adds both entries of a mail, and the run stores one and reports the other as closed
- **THEN** the mail counts as handled as soon as the run has started, before either entry has ended

#### Scenario: One entry failed
- **WHEN** the user adds both entries of a mail, and the run stores one and reports the other as failed
- **THEN** the mail counts as handled, the next check does not offer it again, and the failed link is in the list of unsettled links

#### Scenario: Failing entry left out
- **WHEN** the user finishes a pick list without selecting one entry of a mail and adds its other entry
- **THEN** the mail counts as handled, and the link of the entry left out is not in the list of unsettled links

#### Scenario: Restart during the run
- **WHEN** the application restarts while the run of a finished pick list computes
- **THEN** the mails of that pick list count as handled, and the links the run did not reach are in the list of unsettled links as not reached

### Requirement: Mailbox entries added like alert entries
Finishing a check's pick list SHALL accept only links the check offered, compared as duplicate detection compares links, from none up to all of them. Chosen entries SHALL be added through the same background run as entries from a pasted mail. When the run cannot start, no mail SHALL count as handled. A finished pick list SHALL NOT be finished again.

#### Scenario: Entries added
- **WHEN** the user finishes a check's pick list with four chosen entries from two mails
- **THEN** an alert run adds the four entries, and both mails count as handled once it has started

#### Scenario: More than 100 entries
- **WHEN** a check's pick list holds 140 selected entries and the user adds them
- **THEN** one alert run adds all 140

#### Scenario: Another run computes
- **WHEN** the user finishes a check's pick list while another alert run computes
- **THEN** no run starts, the answer names the running run, and no mail of the check counts as handled

#### Scenario: Entry the check did not offer
- **WHEN** a request finishes a check with a link the check did not offer
- **THEN** it is refused, and nothing is added or marked

### Requirement: Cancel an alert run
The user SHALL be able to cancel a running alert run. The run SHALL stop after the entry it works on and end cancelled when an entry was left out. The entries stored before SHALL stay stored, and the entries it did not reach SHALL stay not started. A cancel SHALL be refused for a run that has ended.

#### Scenario: Cancelled after some entries
- **WHEN** a run over 120 entries has ended 50 and the user cancels it
- **THEN** it adds no further entry after the current one, ends cancelled, and its report says how many entries it ended

#### Scenario: Cancel during the last entry
- **WHEN** the user cancels a run while it works on its last entry
- **THEN** that entry ends, and the run ends done, not cancelled, since no entry was left out

#### Scenario: Mails of a cancelled mailbox run
- **WHEN** a mailbox run is cancelled before it reached the entries of some mails
- **THEN** all mails of its pick list count as handled, and the links it did not reach are in the list of unsettled links as not reached

#### Scenario: Cancel a run that has ended
- **WHEN** the user cancels a run that is done, cancelled or has failed
- **THEN** the cancel is refused, and the answer says the run is not running

## ADDED Requirements

### Requirement: Unsettled links kept in a list
Every alert run, from a mailbox check or a pasted mail, SHALL put each of its links into the list of unsettled links as waiting when it starts, before any mail of its pick list counts as handled. When an entry ends, its link SHALL leave the list if it ended stored, as a duplicate or closed, and SHALL stay with its outcome otherwise: not read (with its attempts, or the reason when no attempt was made) or not judgeable.

#### Scenario: Failed link kept
- **WHEN** a run reports an entry as failed after rate-limited attempts
- **THEN** its link is in the list as not read, with its title and its attempts

#### Scenario: Stored link leaves the list
- **WHEN** a link that is in the list as not read is taken into a later run, which stores it
- **THEN** the link is no longer in the list

#### Scenario: Pasted mail
- **WHEN** a run of a pasted alert mail reports an entry as failed
- **THEN** its link is in the list with the source pasted mail

#### Scenario: Waiting during the run
- **WHEN** a run over 50 entries has ended 10
- **THEN** the list shows the 40 links not yet ended as waiting

### Requirement: No run while the list is unreadable
When the list of unsettled links cannot be read or written, an alert run SHALL NOT start, no mail of its pick list SHALL count as handled, and the answer SHALL say that the list is unreadable.

#### Scenario: List cannot be written
- **WHEN** a pick list is finished and the list of unsettled links cannot be written
- **THEN** no run starts, and no mail of the pick list counts as handled

#### Scenario: Invalid list file
- **WHEN** the list file in the data repository is invalid and the user adds the entries of a pasted mail
- **THEN** no run starts, and the answer says that the list is unreadable

### Requirement: Links a run did not reach
A link the run did not reach SHALL be not reached once the run has ended, whether it was cancelled or crashed. A link that is waiting in the list while no run computes, or while the computing run is not the one that took it, SHALL be reported as not reached, so a restart leaves no link waiting.

#### Scenario: Cancelled run
- **WHEN** a run is cancelled before it reached 30 of its links
- **THEN** those 30 links are in the list as not reached

#### Scenario: Restart during a run
- **WHEN** the application restarts while a run computes, and the list is read afterwards
- **THEN** every link of that run that had not ended is reported as not reached

#### Scenario: Next run after a restart
- **WHEN** a link was left waiting by a run lost in a restart, and a new run starts with other links
- **THEN** the left link is reported as not reached, and only the new run's links as waiting

### Requirement: Tries of an unsettled link
A row SHALL count one try each time a run ends an entry with its link, and SHALL record when that was. Entries with the same link in one run SHALL count as one try, and a link the run did not reach SHALL count none. A link already in the list that a run takes again SHALL keep its row and the date it first entered the list.

#### Scenario: First try
- **WHEN** a run reports a link as not read that was not in the list before
- **THEN** its row shows one try, the time of that try, and the date it entered the list

#### Scenario: Tried again
- **WHEN** a link in the list as not read with one try is taken into a later run, which reports it as not judgeable
- **THEN** its row shows not judgeable, two tries, the new time of the last try and the unchanged date it first entered the list

#### Scenario: Not reached again
- **WHEN** a link in the list with one try is taken into a run that is cancelled before it reaches the link
- **THEN** its row shows not reached and still one try

### Requirement: Unsettled link removed
The user SHALL be able to remove a link from the list of unsettled links. A link that the computing run has not yet ended SHALL NOT be removable. Removing a link SHALL NOT change any posting or mail mark.

#### Scenario: Remove a link
- **WHEN** the user removes a link that is in the list as not read
- **THEN** the link is no longer in the list, also after a restart and on another device

#### Scenario: Remove during the run
- **WHEN** the user removes a link that the computing run lists as waiting
- **THEN** the removal is refused, and the answer says the link is still in the run

#### Scenario: Unknown link
- **WHEN** a request removes a link that is not in the list
- **THEN** it is refused as not found
