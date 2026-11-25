## ADDED Requirements

### Requirement: Run row attempts collapsed
The attempts of a closed or failed run row SHALL sit behind a collapsed control „Details: n Versuche“, collapsed by default for every row, keyboard-operable and announcing whether it is expanded. The outcome, title, link, the explanation of the outcome and the row's buttons SHALL stay visible outside it.

#### Scenario: Collapsed by default
- **WHEN** a run ends with 40 closed entries
- **THEN** each closed row shows „Stelle geschlossen“, its title, link and „Nichts gespeichert.“, and no attempt line until its „Details“ is opened

#### Scenario: Details opened
- **WHEN** the user opens „Details: 2 Versuche“ of a closed row with the keyboard
- **THEN** the two attempts show below it, and the control is announced as expanded

#### Scenario: Entry that could not be judged
- **WHEN** a row shows „Nicht beurteilbar“
- **THEN** its explanation and its text and PDF options stay visible, and its attempts are behind „Details“

### Requirement: Filter an alert run by outcome
A run SHALL offer the filter „Alle (n)“, n being the number of rows, and one filter for each outcome that at least one entry has, named with its count: „hinzugefügt“, „schon gespeichert“, „geschlossen“, „nicht gelesen“, „nicht beurteilbar“. The counts SHALL count a link once and SHALL stay those of the whole run while a filter is active. Exactly one filter SHALL be active, „Alle“ at first; choosing the active filter again SHALL return to „Alle“.

#### Scenario: Filters of a finished run
- **WHEN** a run of 169 entries ended with 2 added, 62 already stored, 42 closed, 51 not read and 12 not assessable
- **THEN** the view offers „Alle (169)“, „2 hinzugefügt“, „62 schon gespeichert“, „42 geschlossen“, „51 nicht gelesen“ and „12 nicht beurteilbar“, with „Alle“ active

#### Scenario: Back to all
- **WHEN** the user chooses the active filter again, or „Alle“
- **THEN** „Alle“ is active and the list shows every row again

### Requirement: Rows of a filtered run
A filter for an outcome SHALL show only the rows with that outcome and no repeat of a link, each with its buttons. „Alle“ SHALL show every row, repeats and entries not started included.

#### Scenario: Filter to the entries that could not be judged
- **WHEN** the user chooses „12 nicht beurteilbar“
- **THEN** the list shows those 12 rows, each with its text and PDF options

#### Scenario: Repeat of a link
- **WHEN** a run holds two entries with the same link, both closed, and the user chooses „geschlossen“
- **THEN** the list shows the first of them only

### Requirement: Active filter announced
The filters SHALL be keyboard-operable and announce which one is active. A status line SHALL say how many of how many entries are shown and, for an outcome filter, which outcome; it SHALL be announced when it changes.

#### Scenario: Status line
- **WHEN** the user chooses „12 nicht beurteilbar“ in a run of 169 entries
- **THEN** the filter is announced as pressed, and the status line says „Zeigt 12 von 169 Anzeigen: nicht beurteilbar“

### Requirement: Filtered run while it computes
The filters SHALL show while the run computes. Their counts SHALL grow as entries end, a filter SHALL appear once its outcome first occurs, and an entry that ends with the chosen outcome SHALL appear in the filtered list without any action of the user. Entries that wait or are being added SHALL show only under „Alle“.

#### Scenario: A third unread entry ends
- **WHEN** the filter „2 nicht gelesen“ is active during a run, and one more entry ends not read
- **THEN** the filter reads „3 nicht gelesen“, the new row appears in the list, and the status line says that 3 entries are shown

### Requirement: Row stored anyway keeps its place in a filtered run
A row the user chose to store anyway SHALL stay in the filtered list while it is fetched again and after it ends with another outcome, until the user chooses another filter. The counts SHALL follow its new outcome.

#### Scenario: Stored anyway under „schon gespeichert“
- **WHEN** the filter „schon gespeichert“ is active and the user stores a text duplicate anyway
- **THEN** its row stays in the list showing that it is fetched, then „Hinzugefügt“, the count of „hinzugefügt“ grows by one and that of „schon gespeichert“ shrinks by one

### Requirement: Posting link in the pick list and the run
In the pick list of a pasted mail or a mailbox check, and in the rows of a run, an entry's link SHALL be a link to that address that opens in a new tab, without passing the app's address or a handle to the app to the opened page. Its visible text SHALL be the address, and its accessible name SHALL name the posting's title and say that it opens in a new tab.

#### Scenario: Open the posting of an entry that could not be judged
- **WHEN** the user activates the link of a „Nicht beurteilbar“ row with the keyboard
- **THEN** the posting's page opens in a new tab, and the run view stays as it was

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
