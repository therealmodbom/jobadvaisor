# Spec Delta

## MODIFIED Requirements

### Requirement: Intake view
The UI SHALL let the user submit a posting as a URL, pasted text, a PDF upload or a pasted job alert mail, and SHALL show the intake outcome, including the attempts made when intake fails. After a successful intake, it SHALL show the posting's title, company and location for correction. It SHALL show whether content screening is on, and for a flagged posting the flagged categories and a release action. It SHALL let the user view and edit the list of login-walled hosts, stored in the data repository.

#### Scenario: Edit the login-walled hosts
- **WHEN** the user adds a host to the login-walled list and saves
- **THEN** later intake of a URL on that host does not fetch it

#### Scenario: Release a flagged posting
- **WHEN** intake stores a posting flagged by the content guard and the user releases it
- **THEN** the stored posting is no longer excluded by the content guard

#### Scenario: Correct a field
- **WHEN** the user changes the company shown after intake and saves
- **THEN** the stored posting carries the corrected company

#### Scenario: Failed link
- **WHEN** intake of a URL fails after all attempts
- **THEN** the view lists the attempts and offers the text and PDF options

## ADDED Requirements

### Requirement: Pasting an alert mail keeps its links
The alert-mail input SHALL take the HTML of a pasted mail, so the links behind titles and buttons are kept, and SHALL show the pasted text. A paste without HTML SHALL be read as plain text. When the mail yields no posting, the view SHALL say so and point to the link and text inputs. While screening is off, the view SHALL say that only known senders' mails can be read.

#### Scenario: Paste from a mail client
- **WHEN** the user copies a whole alert mail in a mail client, whose plain-text copy holds no URL, and pastes it into the alert-mail input
- **THEN** the postings behind the mail's titles are found

#### Scenario: Nothing found
- **WHEN** the pasted mail yields no posting
- **THEN** the view says that no posting was found and points to the link and text inputs

#### Scenario: Screening off
- **WHEN** no classifier is configured and the pasted mail comes from an unknown sender
- **THEN** the view says that only known senders' mails can be read while screening is off

### Requirement: Alert mail pick list
Before anything is fetched, the view SHALL list the postings found in the mail with their titles and links. New ones SHALL be preselected. Ones already stored SHALL be marked, linked to the stored posting and not selectable. Ones on a login-walled host SHALL be marked and not preselected. Ones whose link does not tell them apart SHALL be marked and not selectable, with the text option. The user SHALL be able to change the selection and add the selected entries with one action.

#### Scenario: Mail with a stored posting
- **WHEN** a mail lists five postings and one of them is already stored
- **THEN** the view lists five entries, four of them selected, and the stored one is marked with a link to its posting

#### Scenario: Login-walled host
- **WHEN** one of the found postings is on a login-walled host
- **THEN** it is marked as such and is not selected until the user selects it

### Requirement: Alert mail held or failed
When the content guard holds the mail, the view SHALL say so and list nothing. When reading the mail fails, the view SHALL say so and offer a retry, keeping the pasted mail.

#### Scenario: Mail held by the content guard
- **WHEN** the content guard flags the mail's text
- **THEN** the view says the content guard held the mail and lists no entry

#### Scenario: Reading fails
- **WHEN** the screening or the model call fails
- **THEN** the view says that reading the mail failed, offers a retry, and the pasted mail is still in the field

### Requirement: Alert mail run progress and outcome
While the chosen entries are added, the view SHALL show for each entry whether it waits, is being added, was stored, is a duplicate or failed, and how many entries are done. A failed entry SHALL show its attempts or its reason, and SHALL offer the text and PDF options. Switching to another source or view and back, and reloading the page, SHALL keep the run and its report while the server still knows the run.

#### Scenario: Second of three fails
- **WHEN** the user adds three entries and the second cannot be read
- **THEN** the view shows the first and third as stored with a link to each posting, and the second with its attempts and the text and PDF options

#### Scenario: Switching away and reloading
- **WHEN** the user switches to the link source during a run, comes back, and then reloads the page
- **THEN** the view still shows the run's progress, or its report once the run ended

### Requirement: Alert mail run refused or lost
When a run is refused because another one computes, the view SHALL show that run's progress. When the server no longer knows a run, because it restarted, the view SHALL say so and offer to start over.

#### Scenario: Run already computing
- **WHEN** the user adds entries while another alert-mail run computes
- **THEN** the view shows the computing run's progress

#### Scenario: Server restarted
- **WHEN** the server restarted during a run
- **THEN** the view says the run is no longer known and offers to paste the mail again
