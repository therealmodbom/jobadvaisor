## MODIFIED Requirements

### Requirement: Mailbox pick list grouped by mail
A finished check SHALL show the entries of all its mails in one list, grouped by mail, with the rules of the alert mail pick list for each entry. Each mail head SHALL show the sender, and the subject, date and folder in one line below it, stacked at a phone's width. „N Anzeigen hinzufügen“ SHALL add all selected entries, and „Nichts hinzufügen“ none; the view SHALL say which mails count as handled afterwards („Note on handled mails below the pick list“).

#### Scenario: Three mails
- **WHEN** a check read three mails with seven entries, one already stored
- **THEN** the list shows three mail heads with their entries, six of them selected, and „6 Anzeigen hinzufügen“

#### Scenario: Nothing added
- **WHEN** the user presses „Nichts hinzufügen“
- **THEN** no entry is added, and the mails of the check are not offered again

## ADDED Requirements

### Requirement: Note on handled mails below the pick list
Below the mailbox pick list, the view SHALL say that a mail counts as handled once its added entries are stored, that a mail from which nothing is added counts as handled at once, and that a mail with an entry that cannot be read comes again in the next check.

#### Scenario: Note below the pick list
- **WHEN** a check ends with a pick list
- **THEN** the note below it says when its mails count as handled and that a mail with an unread entry comes again

### Requirement: Same link in another mail of the pick list
An entry whose link an earlier mail of the pick list offers SHALL show its title and link with the note that it is offered in that mail, naming the mail's sender and subject. It SHALL NOT be selectable, and SHALL NOT count in its mail's „n von m ausgewählt“.

#### Scenario: Posting in two mails
- **WHEN** two mails of a check list the same posting
- **THEN** the second mail lists it with a note naming the first mail, without a checkbox to tick, and the add button counts it once

### Requirement: Same link in a run
A run row whose outcome was taken from an earlier entry with the same link SHALL show that outcome and say that the link was fetched once, for the entry above.

#### Scenario: Same link twice
- **WHEN** a run holds two entries with the same link, and the first one is stored
- **THEN** the second row shows it as stored with a link to the posting, and says that the link was fetched once, above

### Requirement: Entry that could not be judged
A failed entry whose link could not be judged SHALL show „Nicht beurteilbar“ instead of „Nicht gelesen“, say that the link answered once as closed while other requests were refused, so it is unclear whether the posting is closed, and offer its attempts and the text and PDF options.

#### Scenario: One 404 among rate-limited answers
- **WHEN** a run reports an entry as failed because its gone answer was disputed
- **THEN** the row shows „Nicht beurteilbar“ with the explanation, its attempts, and the text and PDF options

### Requirement: Mails offered again after a mailbox run
When a run from a mailbox pick list has entries that failed or were not reached, its report SHALL say that the next check offers their mails again.

#### Scenario: Failed entries after a mailbox run
- **WHEN** a mailbox run ends with three entries failed
- **THEN** the report says that the next check offers the mails of those entries again

### Requirement: Cancel button of an alert run
While a run computes, the view SHALL offer „Lauf abbrechen“, which cancels the run at once and without a confirm step. The view SHALL say that the run stops after the current entry and that what is stored stays stored. Once pressed, the button SHALL be disabled and say that the run is being cancelled.

#### Scenario: Cancel a run
- **WHEN** the user presses „Lauf abbrechen“ during a run
- **THEN** the button is disabled and says that the run is being cancelled, and the run stops after the current entry

### Requirement: Result of a cancelled alert run
A cancelled run SHALL show that it was cancelled after N of M entries, with its rows, the rows not reached showing as not started. For a pasted mail, the view SHALL say that pasting the mail again adds the rest, and that the entries already stored then show as stored.

#### Scenario: Cancelled pasted run
- **WHEN** a run of a pasted mail with ten entries is cancelled after four
- **THEN** the view says that the run was cancelled after 4 of 10 entries, shows six rows as not started, and says that pasting the mail again adds the rest

### Requirement: Mailbox check refused while an alert run computes
When „Postfach prüfen“ is refused because an alert run computes, the view SHALL show that run's progress and say that the check can start once the run has ended.

#### Scenario: Check during a run
- **WHEN** the user presses „Postfach prüfen“ while an alert run computes
- **THEN** the view shows that run's progress, and says that the check can start once it has ended
