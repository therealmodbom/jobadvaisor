## ADDED Requirements

### Requirement: Mailbox key from the host
The key that encrypts the mailbox password SHALL come from the host's secret file like the other secrets, and the encrypted password SHALL live on the state volume. Neither the state volume nor the data repository alone SHALL reveal the password.

#### Scenario: Restart
- **WHEN** the service restarts with the same secret file and state volume
- **THEN** the stored mailbox password still works

#### Scenario: State volume without the key
- **WHEN** the state volume is copied to another machine without the secret file
- **THEN** the mailbox password cannot be read from the copy
