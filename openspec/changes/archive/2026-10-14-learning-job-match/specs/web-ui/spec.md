# Spec Delta

## Purpose

Gives the single local user a small but polished browser interface to submit postings, rate triage results and talk to the agent, pleasant enough to use daily from the first version on.

## ADDED Requirements

### Requirement: Local single-user access
The UI SHALL be served on localhost for a single user, without accounts or login.

#### Scenario: Open the app
- **WHEN** the user opens the local address in a browser
- **THEN** the intake and feedback views are available without a login

### Requirement: Intake view
The UI SHALL let the user submit a posting as a URL, pasted text or a PDF upload, and SHALL show the intake outcome, including the attempts made when intake fails. After a successful intake, it SHALL show the posting's title, company and location for correction. It SHALL show whether content screening is on, and for a flagged posting the flagged categories and a release action. It SHALL let the user view and edit the list of login-walled hosts, stored in the data repository.

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

### Requirement: Feedback list
The UI SHALL list the postings presented for rating with score, reasoning and exploration mark, SHALL show the rest of the run result with each posting's score or exclusion, and SHALL let the user rate any of them with a verdict, reason chips and free text. Starting a run SHALL offer a field for the number of postings to present, filled with the default of 10.

#### Scenario: Rate from the list
- **WHEN** the user rates a posting in the list
- **THEN** the rating is stored and the posting is shown as rated

#### Scenario: Exploration visible
- **WHEN** a posting is an exploration pick
- **THEN** the list marks it as such

#### Scenario: Unscreened postings in a run
- **WHEN** a run pauses because its batch holds postings the content guard never checked
- **THEN** the view names those postings and offers to continue with them or abort the run

### Requirement: Fast rating from the keyboard
Rating SHALL be the quickest path in the UI. The user SHALL be able to give a verdict, toggle reason chips and move to the next posting from the keyboard, and the shortcuts SHALL be shown in the view.

#### Scenario: Rate a batch without the mouse
- **WHEN** the user rates every presented posting of a run using only the keyboard
- **THEN** each rating is stored, the posting stays open with its reasons in focus after the verdict, and Enter moves focus to the next unrated posting

#### Scenario: Typing a note
- **WHEN** the user types text containing shortcut keys into a note or any other text field
- **THEN** the text is entered as typed and no rating, chip toggle or navigation happens

### Requirement: Visible state at every step
Every action that waits on the backend SHALL show that it is in progress. Every failure SHALL show a plain-language message with a way to retry. Every empty view SHALL say what to do next.

#### Scenario: Waiting on intake
- **WHEN** an intake is running
- **THEN** the view shows progress and does not accept a second submission of the same input

#### Scenario: Backend error
- **WHEN** a request to the backend fails
- **THEN** the view shows what failed and offers a retry, and no input is lost

#### Scenario: No run yet
- **WHEN** the user opens the feedback view before any run exists
- **THEN** the view explains how to start one

### Requirement: Accessible and consistent presentation
All views SHALL share one visual design, and their text SHALL be German. They SHALL be fully operable by keyboard, show a visible focus, and meet WCAG 2.2 AA contrast in both the light and the dark theme. The theme SHALL follow the system setting.

#### Scenario: Automated accessibility check
- **WHEN** the automated accessibility check runs on each view in both themes
- **THEN** it reports no violations

### Requirement: Agent conversation
The UI SHALL provide a chat view for the conversational agent.

#### Scenario: Ask a question
- **WHEN** the user asks why a listed posting was excluded
- **THEN** the chat shows the agent's answer
