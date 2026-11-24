## ADDED Requirements

### Requirement: Mailbox over IMAP with TLS
The system SHALL read job alert mails from one IMAP mailbox given by host, port and user, with the stored password. Every connection SHALL use TLS with the server certificate verified, and the system SHALL never send the password over a connection without TLS. A connection attempt SHALL give up after 30 seconds.

#### Scenario: Certificate not trusted
- **WHEN** the configured server presents a certificate that does not verify for its host
- **THEN** no login is attempted, and the answer says that the server's certificate is not trusted

#### Scenario: Server does not answer
- **WHEN** the configured server does not answer within 30 seconds
- **THEN** the attempt ends, and the answer says that the server is not reachable

#### Scenario: Port without TLS
- **WHEN** the configured port answers without TLS
- **THEN** no login is attempted, and the answer names a connection problem without any text from the server

### Requirement: Mailbox folders listed
After a successful login, the system SHALL list the account's folders that can hold mails, by their readable names, and leave out folders the server marks as not selectable. It SHALL mark each folder the server flags as trash, junk, sent, drafts, all mails, flagged or important as a system folder.

#### Scenario: Folders of an account
- **WHEN** the user connects to an account with the folders „Posteingang“, „Jobs“ and a trash folder the server flags as trash
- **THEN** the answer lists all three, and only the trash folder is marked as a system folder

#### Scenario: Folder name outside ASCII
- **WHEN** an account holds a folder named „Entwürfe“
- **THEN** the list shows it as „Entwürfe“

#### Scenario: Parent folder that holds no mails
- **WHEN** the server lists a folder marked as not selectable
- **THEN** the list leaves it out, and no check tries to open it

### Requirement: Folders a check searches
A check SHALL search every listed folder that exists at the time of the check except system folders when the user chose all folders, or exactly the folders the user chose otherwise. A chosen folder that no longer exists SHALL be skipped and named in the check's result.

#### Scenario: Folder created later
- **WHEN** the user chose all folders and later creates the folder „Jobs 2027“
- **THEN** the next check searches „Jobs 2027“ too

#### Scenario: Server without folder flags
- **WHEN** the server flags no folder as a system folder and the user chose all folders
- **THEN** every listed folder is searched

#### Scenario: Chosen folder deleted
- **WHEN** a chosen folder was deleted on the server
- **THEN** the check searches the other chosen folders and names the missing one

### Requirement: One mail read once per check
A mail that appears in several searched folders SHALL be read once per check, recognised by its message ID.

#### Scenario: Mail in two folders
- **WHEN** the same mail is in „Posteingang“ and in a chosen folder „Alle Nachrichten“
- **THEN** the check reads it once, and its entries appear once

### Requirement: The mailbox is read only
A check SHALL open each folder read-only and SHALL fetch mails without setting any flag. It SHALL never move, copy, delete or flag a mail.

#### Scenario: Unread mail stays unread
- **WHEN** a check reads a mail that was unread on the server
- **THEN** the mail is still unread on the server after the check

### Requirement: Mails from the start date on
A check SHALL consider only mails received on or after the start date set before the first check. The start date SHALL be stored when a check first logs in successfully, and SHALL change only when the account changes.

#### Scenario: Older mail
- **WHEN** the start date is 24 October and a searched folder holds a mail received on 20 October
- **THEN** no check reads that mail

#### Scenario: Start date after several checks
- **WHEN** the user has run three checks on the same account
- **THEN** the start date is still the one set before the first check

#### Scenario: First check fails at login
- **WHEN** the first check fails because the server refuses the login
- **THEN** no start date is stored, and the next check asks for one again

### Requirement: Handled mails
A mail SHALL count as handled once the user has finished the pick list holding it, by adding entries or by adding none, or as soon as the finder has read it and returned no entry. A mail whose reading failed, or that no model could read because screening is off, SHALL NOT count as handled.

#### Scenario: Pick list not finished
- **WHEN** a check offers postings from three mails and the user leaves without finishing the pick list
- **THEN** none of the three counts as handled

#### Scenario: Mail without postings
- **WHEN** the finder reads a mail and returns no entry
- **THEN** that mail counts as handled at once

#### Scenario: Reading failed
- **WHEN** the model call fails while a check reads a mail
- **THEN** that mail does not count as handled

### Requirement: Mails waiting for screening
A mail that no model read because screening is off SHALL be named in the check's result as not read. Later checks SHALL skip it while screening stays off, and the first check after screening is turned on SHALL read it.

#### Scenario: Screening off
- **WHEN** no classifier is configured and a check reads a mail from a sender without a fixed rule
- **THEN** the result names it as not read while screening is off, and the next check does not read it again

#### Scenario: Screening turned on
- **WHEN** a classifier is configured after such a check
- **THEN** the next check reads that mail

### Requirement: Handled mails are skipped
A check SHALL skip every handled mail. A handled mail that carries a message ID SHALL stay handled after the server renumbered its folder, and when it was moved to another searched folder.

#### Scenario: Next check
- **WHEN** the user finished the pick list of a check and runs another check
- **THEN** the mails of the first check are not read again

#### Scenario: Mail moved
- **WHEN** a handled mail with a message ID is moved from „Posteingang“ to „Jobs“ and both are searched
- **THEN** the next check does not read it

#### Scenario: Folder renumbered
- **WHEN** the server renumbers a searched folder
- **THEN** the handled mails in it that carry a message ID are not read again

### Requirement: Each mail through the finder
A check SHALL pass each unhandled mail to the same finder as a pasted mail, with the mail's HTML part, or its plain-text part when the HTML part is missing or blank. The fixed rules, the content guard, the model and the record of how each mail was read SHALL apply unchanged.

#### Scenario: Known sender
- **WHEN** a check reads a LinkedIn job alert mail
- **THEN** its postings are found and no model is called

#### Scenario: Mail held by the content guard
- **WHEN** the content guard flags a mail a check reads
- **THEN** no model reads it, and the check's result names it as held with no entry

#### Scenario: Blank HTML part
- **WHEN** a mail has an empty HTML part and a plain-text part with posting URLs
- **THEN** the finder reads the plain-text part

### Requirement: Oversized mails skipped
A mail over 4,000,000 bytes, or with a part over 2,000,000 characters, SHALL NOT be read. It SHALL be named in the check's result and count as handled at once.

#### Scenario: Oversized mail
- **WHEN** a mail's HTML part holds more than 2,000,000 characters
- **THEN** the check does not read it, names it in its result, and no later check offers it

### Requirement: At most 200 mails per check
A check SHALL read at most 200 unhandled mails, oldest first, and SHALL say how many unhandled mails remain for the next check.

#### Scenario: Large first check
- **WHEN** the searched folders hold 260 unhandled mails since the start date
- **THEN** the check reads the 200 oldest and says that 60 remain

### Requirement: One mailbox check at a time
The system SHALL run a check in the background and SHALL report how many mails it will read and how many it has read. It SHALL refuse to start a check while another one runs, naming the running check. A check's state SHALL live in memory only. The system SHALL name the running check, or the last check whose pick list is not finished, to every client.

#### Scenario: Second check
- **WHEN** the user starts a check while another check runs
- **THEN** the start is refused, and the answer names the running check

#### Scenario: Restart during a check
- **WHEN** the application restarts before the user finished the pick list of a check
- **THEN** the check's state is gone, and the mails of its pick list are offered again by the next check

#### Scenario: Another browser tab
- **WHEN** a check ended with a pick list and the user opens the mailbox source in a new tab
- **THEN** the new tab shows that pick list

### Requirement: A failed check names its reason
When the key is missing, the password is missing or unreadable, the server cannot be reached, its certificate is not trusted, it refuses the login, or the connection fails otherwise before any mail was read, the check SHALL end with that reason, and no mail SHALL count as handled. A reason SHALL never contain text from the server.

#### Scenario: Login refused
- **WHEN** the server refuses the user name or the password
- **THEN** the check ends with the reason that the login was refused, and no mail counts as handled

### Requirement: An interrupted check keeps what it read
When the connection fails after a check has read mails, the check SHALL end with the mails read so far and name the interruption, and the mails it did not read SHALL stay unhandled.

#### Scenario: Connection lost
- **WHEN** the connection drops after a check has read 5 of 12 mails
- **THEN** the pick list holds the entries of those 5 mails, the result names the interruption, and the next check reads the other 7

### Requirement: Cancel a mailbox check
The user SHALL be able to cancel a running check. The check SHALL stop after the mail it reads, end with the mails read so far and name the cancel, and the mails it did not read SHALL stay unhandled. A cancel SHALL be refused for a check that is not running.

#### Scenario: Cancelled after some mails
- **WHEN** a check covering 200 mails has read 37 and the user cancels it
- **THEN** it reads no further mail, the pick list holds the entries of those 37 mails, the result says it was cancelled after 37 of 200, and the next check reads the other 163

#### Scenario: Cancel a check that has ended
- **WHEN** the user cancels a check that is done or has failed
- **THEN** the cancel is refused, and the answer says the check is not running

### Requirement: Mailbox password stored encrypted
The system SHALL store the mailbox password only encrypted, in the state directory on the machine the backend runs on. The key SHALL come from the application's secret configuration, never from a file in the state directory or the data repository. Without a valid key, the system SHALL refuse to store a password.

#### Scenario: Copy of the state directory
- **WHEN** someone holds a copy of the state directory but not the key
- **THEN** the stored password cannot be read from it

#### Scenario: No key configured
- **WHEN** no key is configured, or the configured key is malformed, and the user saves a password
- **THEN** the password is not stored, and the answer says that no key is configured

### Requirement: The mailbox password is never revealed
The mailbox password SHALL NOT appear in an API answer, a log line, a trace, an error message or a file of the data repository. The API SHALL answer only whether a password is stored.

#### Scenario: Settings read back
- **WHEN** a client reads the mailbox settings after a password was stored
- **THEN** the answer says that a password is stored and does not contain it

#### Scenario: Login fails
- **WHEN** a login with the stored password fails
- **THEN** neither the answer nor the log contains the password

### Requirement: The password stays with its account
Changing the server, the port or the user name without entering a new password SHALL remove the stored password, so it is never sent to another server or account.

#### Scenario: Server changed
- **WHEN** a password is stored and the user changes the server without entering a password
- **THEN** the stored password is removed, and no login is attempted until a new one is entered

### Requirement: A new account starts fresh
Changing the server or the user name SHALL clear the start date, the time of the last check and the record of handled mails, and SHALL drop an unfinished pick list. While a check runs, the account SHALL NOT be changed.

#### Scenario: Other account
- **WHEN** the user changes the user name to another account
- **THEN** the next check asks for a start date and offers every mail since then

#### Scenario: Change during a check
- **WHEN** the user saves another server while a check runs
- **THEN** the change is refused, and the answer names the running check

### Requirement: Unreadable stored password
When the stored password cannot be decrypted with the configured key, the system SHALL NOT attempt a login, and SHALL say that the password must be entered again.

#### Scenario: Key changed
- **WHEN** the key was changed after a password was stored, and the user starts a check
- **THEN** no login is attempted, and the answer says that the password must be entered again

### Requirement: Mailbox entries added like alert entries
Finishing a check's pick list SHALL accept only entries the check offered, from none up to all of them. Chosen entries SHALL be added through the same background run as entries from a pasted mail. The mails of the pick list SHALL count as handled once that run has started, or at once when no entry was chosen. When the run cannot start, no mail SHALL count as handled. A finished pick list SHALL NOT be finished again.

#### Scenario: Entries added
- **WHEN** the user finishes a check's pick list with four chosen entries
- **THEN** an alert run adds the four entries, and the mails of the pick list count as handled

#### Scenario: More than 100 entries
- **WHEN** a check's pick list holds 140 selected entries and the user adds them
- **THEN** one alert run adds all 140

#### Scenario: Another run computes
- **WHEN** the user finishes a check's pick list while another alert run computes
- **THEN** no run starts, the answer names the running run, and no mail of the check counts as handled

#### Scenario: Entry the check did not offer
- **WHEN** a request finishes a check with a link the check did not offer
- **THEN** it is refused, and nothing is added or marked
