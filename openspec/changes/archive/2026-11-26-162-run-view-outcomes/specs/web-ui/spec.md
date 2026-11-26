## MODIFIED Requirements

### Requirement: Alert mail run progress and outcome
While the chosen entries are added, the view SHALL show for each entry whether it waits, is being added, was stored, is a duplicate, is closed or failed, and how many entries are done. A failed entry SHALL offer its attempts, or say that it could not be read when it has none, and SHALL offer the text and PDF options. A closed entry SHALL show „Stelle geschlossen“ and offer its attempts. Switching to another source or view and back, and reloading the page, SHALL keep the run and its report while the server still knows the run.

#### Scenario: Second of three fails
- **WHEN** the user adds three entries and the second cannot be read
- **THEN** the view shows the first and third as stored with a link to each posting, and the second with the text and PDF options and its attempts behind „Details“

#### Scenario: Switching away and reloading
- **WHEN** the user switches to the link source during a run, comes back, and then reloads the page
- **THEN** the view still shows the run's progress, or its report once the run ended

#### Scenario: Closed entry
- **WHEN** an added entry ends closed
- **THEN** the view shows it as „Stelle geschlossen“ with its attempts behind „Details“, and counts it as done

### Requirement: Entry that could not be judged
A failed entry whose link could not be judged SHALL show „Nicht beurteilbar“ instead of „Nicht gelesen“, say that the link answered once as closed while other requests were refused, so it is unclear whether the posting is closed, and offer its attempts and the text and PDF options.

#### Scenario: One 404 among rate-limited answers
- **WHEN** a run reports an entry as failed because its gone answer was disputed
- **THEN** the row shows „Nicht beurteilbar“ with the explanation and the text and PDF options, and its attempts behind „Details“

## ADDED Requirements

### Requirement: Run row attempts collapsed
The attempts of a closed or failed run row SHALL sit behind a collapsed control „Details: n Versuche“ („Details: 1 Versuch“ for one), collapsed by default for every row, keyboard-operable and announcing whether it is expanded. The outcome, title, link, the explanation of the outcome and the row's buttons SHALL stay visible outside it.

#### Scenario: Collapsed by default
- **WHEN** a run ends with 40 closed entries
- **THEN** each closed row shows „Stelle geschlossen“, its title, link and „Nichts gespeichert.“, and no attempt line until its „Details“ is opened

#### Scenario: Details opened
- **WHEN** the user opens „Details: 2 Versuche“ of a closed row with the keyboard
- **THEN** the two attempts show below it, and the control is announced as expanded

#### Scenario: Entry that could not be judged
- **WHEN** a row shows „Nicht beurteilbar“
- **THEN** its explanation and its text and PDF options stay visible, and its attempts are behind „Details“

#### Scenario: Failed row without attempts
- **WHEN** a run reports a failed entry without attempts
- **THEN** the row says that the posting could not be read, offers the text and PDF options, and shows no „Details“

### Requirement: Filter an alert run by outcome
A run SHALL offer the filter „Alle (n)“, n being the number of rows, and one filter for each outcome that at least one entry has, named with its count: „hinzugefügt“, „schon gespeichert“, „geschlossen“, „nicht gelesen“, „nicht beurteilbar“. The counts SHALL count a link once and SHALL stay those of the whole run while a filter is active. Exactly one filter SHALL be active, „Alle“ at first; choosing the active filter again SHALL return to „Alle“.

#### Scenario: Filters of a finished run
- **WHEN** a run of 120 entries ended with 3 added, 40 already stored, 30 closed, 37 not read and 10 not assessable
- **THEN** the view offers „Alle (120)“, „3 hinzugefügt“, „40 schon gespeichert“, „30 geschlossen“, „37 nicht gelesen“ and „10 nicht beurteilbar“, with „Alle“ active

#### Scenario: Back to all
- **WHEN** the user chooses the active filter again, or „Alle“
- **THEN** „Alle“ is active and the list shows every row again

### Requirement: Rows of a filtered run
A filter for an outcome SHALL show only the rows with that outcome and no repeat of a link, each with its buttons, plus the rows stored anyway under it („Row stored anyway keeps its place in a filtered run“). „Alle“ SHALL show every row, repeats and entries not started included.

#### Scenario: Filter to the entries that could not be judged
- **WHEN** the user chooses „10 nicht beurteilbar“
- **THEN** the list shows those 10 rows, each with its text and PDF options

#### Scenario: Repeat of a link
- **WHEN** a run holds two entries with the same link, both closed, and the user chooses „geschlossen“
- **THEN** the list shows the first of them only

### Requirement: Active filter announced
The filters SHALL be keyboard-operable and announce which one is active. A status line SHALL say how many rows the list shows, of how many rows the run has, and, for an outcome filter, which outcome; it SHALL be announced when it changes.

#### Scenario: Status line
- **WHEN** the user chooses „10 nicht beurteilbar“ in a run of 120 entries
- **THEN** the filter is announced as pressed, and the status line says „Zeigt 10 von 120 Anzeigen: nicht beurteilbar“

### Requirement: Filtered run while it computes
The filters SHALL show while the run computes. Their counts SHALL grow as entries end, a filter SHALL appear once its outcome first occurs, and an entry that ends with the chosen outcome SHALL appear in the filtered list without any action of the user. Entries that wait or are being added SHALL show only under „Alle“, except a row stored anyway („Row stored anyway keeps its place in a filtered run“).

#### Scenario: A third unread entry ends
- **WHEN** the filter „2 nicht gelesen“ is active during a run, and one more entry ends not read
- **THEN** the filter reads „3 nicht gelesen“, the new row appears in the list, and the status line says that 3 entries are shown

### Requirement: Row stored anyway keeps its place in a filtered run
A row the user chose to store anyway SHALL stay in the filtered list while it is fetched again and after it ends with another outcome, until the user chooses another filter. The counts SHALL follow its new outcome, and the active filter SHALL stay offered and active until then, also when its count drops to 0. When the user confirms, focus SHALL move to the row's outcome line, which stays in place while the row is fetched and after, with or without a filter.

#### Scenario: Stored anyway under „schon gespeichert“
- **WHEN** the filter „schon gespeichert“ is active and the user stores a text duplicate anyway
- **THEN** its row stays in the list showing that it is fetched, then „Hinzugefügt“, the count of „hinzugefügt“ grows by one and that of „schon gespeichert“ shrinks by one

#### Scenario: Last entry of the active filter stored anyway
- **WHEN** the filter „1 schon gespeichert“ is active and the user stores that text duplicate anyway
- **THEN** „0 schon gespeichert“ stays active with the row in the list, the status line says that 1 entry is shown, and the filter disappears once the user chooses another filter

#### Scenario: Focus after confirming
- **WHEN** the user confirms „Ja, als neue Anzeige speichern“ with the keyboard
- **THEN** focus is on the row's outcome line, which reads that the row is fetched and then „Hinzugefügt“, and focus is not lost while the confirmation and its buttons go away

#### Scenario: Two rows stored anyway in a row
- **WHEN** the filter „schon gespeichert“ is active and the user stores two text duplicates anyway, one after the other
- **THEN** both rows stay in the list until the user chooses another filter

### Requirement: Posting link in the pick list and the run
In the pick list of a pasted mail or a mailbox check, and in the rows of a run, an entry's link SHALL be a link to that address that opens in a new tab, without passing the app's address or a handle to the app to the opened page. Its visible text SHALL be the address, and its accessible name SHALL name the posting's title and say that it opens in a new tab. An address that is not http or https SHALL show as plain text, not as a link.

#### Scenario: Open the posting of an entry that could not be judged
- **WHEN** the user activates the link of a „Nicht beurteilbar“ row with the keyboard
- **THEN** the original ad opens in a new tab, and the run view stays as it was

#### Scenario: Link in the pick list
- **WHEN** a pick list shows an entry titled „Data Engineer“
- **THEN** its link is announced as opening „Data Engineer“ in a new tab, and the entry is still selected with its checkbox

### Requirement: Attempt reasons in German
Wherever the view lists attempts (a single link, several links, an alert run), each attempt's reason SHALL be German. An HTTP status SHALL show as „HTTP“ with its code. A reason the view does not know SHALL show as it came, never be left out.

#### Scenario: No posting text
- **WHEN** an attempt reports that the page held no posting text
- **THEN** its line reads „fehlgeschlagen (kein Anzeigentext gefunden)“

#### Scenario: Rate-limited
- **WHEN** an attempt reports HTTP 429
- **THEN** its line reads „fehlgeschlagen (HTTP 429)“

#### Scenario: Unknown reason
- **WHEN** an attempt reports a reason the view does not know
- **THEN** its line shows that reason as it came

### Requirement: Stored posting linked after a single add
When a single add of a link, a text or a PDF has stored a posting or found it already stored, the result SHALL link to that posting's page („Anzeige ansehen“) next to the link to the original ad, reachable by keyboard and named for screen readers.

#### Scenario: New posting
- **WHEN** a single add stores a new posting
- **THEN** the result offers „Anzeige ansehen“, which opens the page of that posting in the app

#### Scenario: Posting already stored
- **WHEN** a single add ends „Schon gespeichert“
- **THEN** the result offers „Anzeige ansehen“, which opens the page of the stored posting it matched
