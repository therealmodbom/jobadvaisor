## ADDED Requirements

### Requirement: Mailbox over IMAP with TLS
The system SHALL read job alert mails from one IMAP mailbox given by host, port and user, with the stored password. Every connection SHALL use TLS with the server certificate verified, and the system SHALL never send the password over a connection without TLS. A connection attempt SHALL give up after 30 seconds.

#### Scenario: Certificate not trusted
- **WHEN** the configured server presents a certificate that does not verify for its host
- **THEN** no login is attempted, and the answer says that the server's certificate is not trusted

#### Scenario: Server does not answer
- **WHEN** the configured server does not answer within 30 seconds
- **THEN** the attempt ends, and the answer says that the server is not reachable

### Requirement: Mailbox folders listed
After a successful login, the system SHALL list the account's folders by their readable names. It SHALL mark each folder the server flags as trash, junk, sent or drafts as a system folder.

#### Scenario: Folders of an account
- **WHEN** the user connects to an account with the folders „Posteingang“, „Jobs“ and a trash folder the server flags as trash
- **THEN** the answer lists all three, and only the trash folder is marked as a system folder

#### Scenario: Folder name outside ASCII
- **WHEN** an account holds a folder named „Entwürfe“
- **THEN** the list shows it as „Entwürfe“

### Requirement: Folders a check searches
A check SHALL search every folder that exists at the time of the check except system folders when the user chose all folders, or exactly the folders the user chose otherwise. A chosen folder that no longer exists SHALL be skipped and named in the check's result.

#### Scenario: Folder created later
- **WHEN** the user chose all folders and later creates the folder „Jobs 2027“
- **THEN** the next check searches „Jobs 2027“ too

#### Scenario: Server without folder flags
- **WHEN** the server flags no folder as a system folder and the user chose all folders
- **THEN** every folder is searched

#### Scenario: Chosen folder deleted
- **WHEN** a chosen folder was deleted on the server
- **THEN** the check searches the other chosen folders and names the missing one

### Requirement: The mailbox is read only
A check SHALL open each folder read-only and SHALL fetch mails without setting any flag. It SHALL never move, copy, delete or flag a mail.

#### Scenario: Unread mail stays unread
- **WHEN** a check reads a mail that was unread on the server
- **THEN** the mail is still unread on the server after the check

### Requirement: Mails from the start date on
A check SHALL consider only mails received on or after the start date the user set before the first check. The start date SHALL change only when the user changes it.

#### Scenario: Older mail
- **WHEN** the start date is 24 October and a searched folder holds a mail received on 20 October
- **THEN** no check reads that mail

#### Scenario: Start date after several checks
- **WHEN** the user has run three checks and not changed the start date
- **THEN** the start date is still the one set before the first check

### Requirement: Handled mails
A mail SHALL count as handled once the user has finished the pick list holding it, by adding entries or by adding none, or as soon as the finder has read it and returned no entry. A mail whose reading failed SHALL NOT count as handled.

#### Scenario: Pick list not finished
- **WHEN** a check offers postings from three mails and the user leaves without finishing the pick list
- **THEN** none of the three counts as handled

#### Scenario: Mail without postings
- **WHEN** the finder reads a mail and returns no entry
- **THEN** that mail counts as handled at once

#### Scenario: Reading failed
- **WHEN** the model call fails while a check reads a mail
- **THEN** that mail does not count as handled

### Requirement: Handled mails are skipped
A check SHALL skip every handled mail. A handled mail SHALL stay handled after the server renumbered its folder, and when it was moved to another searched folder.

#### Scenario: Next check
- **WHEN** the user finished the pick list of a check and runs another check
- **THEN** the mails of the first check are not read again

#### Scenario: Mail moved
- **WHEN** a handled mail is moved from „Posteingang“ to „Jobs“ and both are searched
- **THEN** the next check does not read it

#### Scenario: Folder renumbered
- **WHEN** the server renumbers a searched folder
- **THEN** the handled mails in it are not read again

### Requirement: Each mail through the finder
A check SHALL pass each unhandled mail to the same finder as a pasted mail, with the mail's HTML part, or its plain-text part when it has no HTML part. The fixed rules, the content guard, the model and the record of how each mail was read SHALL apply unchanged. A mail with a part over 2,000,000 characters SHALL be skipped and named.

#### Scenario: Known sender
- **WHEN** a check reads a LinkedIn job alert mail
- **THEN** its postings are found and no model is called

#### Scenario: Mail held by the content guard
- **WHEN** the content guard flags a mail a check reads
- **THEN** no model reads it, and the check's result names it as held with no entry

#### Scenario: Oversized mail
- **WHEN** a mail's HTML part holds more than 2,000,000 characters
- **THEN** the check skips it and names it in its result

### Requirement: At most 200 mails per check
A check SHALL read at most 200 unhandled mails, oldest first, and SHALL say how many unhandled mails remain for the next check.

#### Scenario: Large first check
- **WHEN** the searched folders hold 260 unhandled mails since the start date
- **THEN** the check reads the 200 oldest and says that 60 remain

### Requirement: One mailbox check at a time
The system SHALL run a check in the background and SHALL report how many unhandled mails it found and how many it has read. It SHALL refuse to start a check while another one runs, naming the running check. A check's state SHALL live in memory only.

#### Scenario: Second check
- **WHEN** the user starts a check while another check runs
- **THEN** the start is refused, and the answer names the running check

#### Scenario: Restart during a check
- **WHEN** the application restarts before the user finished the pick list of a check
- **THEN** the check's state is gone, and its mails are offered again by the next check

### Requirement: A failed check names its reason
When the server cannot be reached, its certificate is not trusted, it refuses the login, or a folder cannot be opened, the check SHALL end with that reason. No mail of a failed check SHALL count as handled.

#### Scenario: Login refused
- **WHEN** the server refuses the user name or the password
- **THEN** the check ends with the reason that the login was refused, and no mail counts as handled

### Requirement: Mailbox password stored encrypted
The system SHALL store the mailbox password only encrypted, in the state directory on the machine the backend runs on. The key SHALL come from the application's secret configuration, never from a file in the state directory or the data repository. Without a configured key, the system SHALL refuse to store a password.

#### Scenario: Copy of the state directory
- **WHEN** someone holds a copy of the state directory but not the key
- **THEN** the stored password cannot be read from it

#### Scenario: No key configured
- **WHEN** no key is configured and the user saves a password
- **THEN** the password is not stored, and the answer says that no key is configured

### Requirement: The mailbox password is never revealed
The mailbox password SHALL NOT appear in an API answer, a log line, a trace, an error message or a file of the data repository. The API SHALL answer only whether a password is stored.

#### Scenario: Settings read back
- **WHEN** a client reads the mailbox settings after a password was stored
- **THEN** the answer says that a password is stored and does not contain it

#### Scenario: Login fails
- **WHEN** a login with the stored password fails
- **THEN** neither the answer nor the log contains the password

### Requirement: Unreadable stored password
When the stored password cannot be decrypted with the configured key, the system SHALL NOT attempt a login, and SHALL say that the password must be entered again.

#### Scenario: Key changed
- **WHEN** the key was changed after a password was stored, and the user starts a check
- **THEN** no login is attempted, and the answer says that the password must be entered again

### Requirement: Mailbox entries added like alert entries
Finishing a check's pick list with chosen entries SHALL add them through the same background run as entries from a pasted mail. The check's mails SHALL count as handled once that run has started, or at once when no entry was chosen. When the run cannot start, no mail SHALL count as handled.

#### Scenario: Entries added
- **WHEN** the user finishes a check's pick list with four chosen entries
- **THEN** an alert run adds the four entries, and the check's mails count as handled

#### Scenario: Another run computes
- **WHEN** the user finishes a check's pick list while another alert run computes
- **THEN** no run starts, the answer names the running run, and no mail of the check counts as handled
