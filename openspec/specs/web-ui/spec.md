# web-ui Specification

## Purpose
Gives the single local user a small but polished browser interface to submit postings, rate triage results and talk to the agent, pleasant enough to use daily from the first version on.

## Requirements

### Requirement: Local single-user access
The UI SHALL be served for a single user, without accounts or login: on localhost, or when deployed, on the user's private network only. Access control is the network, never the app.

#### Scenario: Open the app
- **WHEN** the user opens the local address in a browser
- **THEN** the intake and pool views are available without a login

#### Scenario: Open the deployed app
- **WHEN** the user opens the deployed address from a device on the private network
- **THEN** the intake and pool views are available without a login

### Requirement: Intake view
The UI SHALL let the user submit a posting as a URL, pasted text, a PDF upload or a pasted job alert mail, or take postings from a check of the configured mailbox, and SHALL show the intake outcome, including the attempts made when intake fails or finds the posting closed. After a successful intake, it SHALL show the posting's title, company and location for correction. It SHALL show whether content screening is on, and for a flagged posting the flagged categories and a release action. It SHALL let the user view and edit the list of login-walled hosts, stored in the data repository.

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

#### Scenario: Closed link
- **WHEN** intake of a URL ends with the posting closed
- **THEN** the view shows „Stelle geschlossen“ with the attempts, and offers no text or PDF option

#### Scenario: Mailbox source
- **WHEN** the user chooses the source „Postfach“
- **THEN** the view offers the mailbox check instead of an input field

### Requirement: Fast rating from the keyboard
Rating SHALL be the quickest path in the UI. The user SHALL be able to give a verdict, toggle reason chips and move to the next posting from the keyboard, and the shortcuts SHALL be shown in the view. A chip's shortcut SHALL give the verdict when none was given, and SHALL NOT change a verdict already given.

#### Scenario: Rate a batch without the mouse
- **WHEN** the user rates every listed unrated posting using only the keyboard
- **THEN** each rating is stored, the posting stays open with its reasons in focus after the verdict, and Enter moves focus to the next unrated posting

#### Scenario: Typing a note
- **WHEN** the user types text containing shortcut keys into a note or any other text field
- **THEN** the text is entered as typed and no rating, chip toggle or navigation happens

#### Scenario: Chip gives the verdict
- **WHEN** the user toggles a positive chip on a posting without a verdict, by mouse or by keyboard
- **THEN** the verdict is positive, and chips of both polarities remain selectable

#### Scenario: Explicit verdict wins
- **WHEN** the user rated a posting negative and then toggles a positive chip
- **THEN** the verdict stays negative

### Requirement: Visible state at every step
Every action that waits on the backend SHALL show that it is in progress. Every failure SHALL show a plain-language message with a way to retry. Every empty view SHALL say what to do next.

#### Scenario: Waiting on intake
- **WHEN** an intake is running
- **THEN** the view shows progress and does not accept a second submission of the same input

#### Scenario: Backend error
- **WHEN** a request to the backend fails
- **THEN** the view shows what failed and offers a retry, and no input is lost

#### Scenario: No run yet
- **WHEN** the user opens the pool before any posting is stored
- **THEN** the view explains how to add postings

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

### Requirement: Rating at four levels
The UI SHALL let the user rate a posting at four levels, in the pool and on the posting's page: "Ja, auf jeden Fall" (key `1`), "Ja, vielleicht" (`2`), "Nein, eher nicht" (`3`) and "Nein, auf keinen Fall" (`4`), listed in that order. The choice SHALL replace the earlier two-button wording ("Interessant", "Nicht für mich"). The stored level SHALL be shown on the posting's page and in the pool after a reload; a label without a strength SHALL be shown as "Ja" or "Nein". The shortcuts SHALL be listed in the view's legend. Everything the requirement "Fast rating from the keyboard" says of a verdict applies to a level: it is stored at once, the posting stays open with its reasons in focus, and a chip's shortcut gives a direction only when none was given and never changes a level already given. Choosing the level already shown SHALL change nothing.

#### Scenario: Rate at each level
- **WHEN** the user rates one posting at each of the four levels, by mouse or by the keys `1` to `4`
- **THEN** each level is stored, and after a reload the posting shows that level

#### Scenario: Stored label without strength
- **WHEN** the pool lists a posting whose label holds a verdict and no strength
- **THEN** it shows "Ja" or "Nein", and none of the four buttons is marked as chosen

#### Scenario: Chip does not override a level
- **WHEN** a posting is rated "Nein, eher nicht" and the user toggles a positive chip
- **THEN** the level stays "Nein, eher nicht"

### Requirement: Pool view
The UI SHALL show the pool ranked by fit, with the text filter and the state filters, each row showing title, company, score, the user's rating, application status and, where it applies, the exploration mark or the import origin. The user SHALL be able to rate a posting, change a rating and set the application status from the list. The view SHALL show the pass button, the correction counter, the share of corrections and the hint of the pool, and SHALL show a pass's progress. It SHALL name no run.

#### Scenario: Rate from the pool
- **WHEN** the user rates a posting in the list
- **THEN** the rating is stored and the posting shows as rated, with the counter updated

#### Scenario: Start a pass
- **WHEN** the user presses the main part of the pass button
- **THEN** the pass button turns into its cancel button, the pass's progress shows below it, and the new scores appear in the ranking when the pass ends

#### Scenario: Unscreened postings in a pass
- **WHEN** a pass pauses because it holds postings the content guard never checked
- **THEN** the view names those postings and offers to continue with them or abort the pass

#### Scenario: Change the hint settings
- **WHEN** the user opens „Einstellungen“ in the header, sets the threshold to 5 and saves
- **THEN** the hint appears from 5 corrections on

### Requirement: Pass progress below the pass button
While a pass computes, the pool view SHALL show its progress below the pass button and its counter line, in the column of the pass button; the check button and its progress or report sit in the column beside it. The progress SHALL name the phase, show a bar and, while the pass scores, the count as done out of total, moving after every posting. It SHALL keep its size from one phase to the next.

#### Scenario: Same size in every phase
- **WHEN** a pass moves from checking to scoring and to storing, and the user asks to cancel on the way
- **THEN** the progress keeps its size, and only its texts and its bar change

#### Scenario: Scoring
- **WHEN** a pass has scored 12 of 80 postings
- **THEN** the view shows 12 of 80 with a bar filled to that share

#### Scenario: Checking
- **WHEN** a pass is still checking which postings it takes
- **THEN** the view says the pass is checking, without a count

### Requirement: Cancel button of a pass
While a pass computes, the pass button SHALL give way to a button of the same width that cancels the pass, at once and without a confirm step. After the press, the view SHALL say the pass stops after the current posting, until it has stopped. A pass that waits for the answer about unscreened postings SHALL offer no cancel button, since the question offers its own abort.

#### Scenario: Cancel a pass
- **WHEN** the user presses the cancel button of a running pass
- **THEN** the view says the pass stops after the current posting, and no dialog asks to confirm

#### Scenario: Nothing moves sideways
- **WHEN** a pass starts or ends
- **THEN** the button keeps its width, and the check button and its progress keep their place

#### Scenario: Pass waits for an answer
- **WHEN** a pass asks about unscreened postings
- **THEN** the view shows the question with its abort, and no cancel button

### Requirement: No double press on the pass button
For about one second after the pass button turns into the cancel button, and after the cancel button turns back, the button that appeared SHALL ignore presses.

#### Scenario: Double press on start
- **WHEN** the user presses the pass button twice in quick succession
- **THEN** the pass starts and is not cancelled

#### Scenario: Cancel as the pass ends
- **WHEN** the user presses the cancel button just as the pass ends
- **THEN** no new pass starts

### Requirement: Focus stays in the pass button
An inert main part of the pass button SHALL keep keyboard focus, so that a key press on it does not reach the pool's shortcuts. Focus inside the pass button SHALL stay inside it when the button turns into the cancel button and back, and SHALL go to the question when a pass stops at the unscreened question, never to a button that starts a pass.

#### Scenario: Focus survives a pass
- **WHEN** the user starts a pass with the keyboard on the main part, and the pass ends with nothing left to score
- **THEN** focus moves to the cancel button, and back to the main part when the pass ends, and a further Enter starts no pass and moves no row selection

#### Scenario: Focus follows an answer to the question
- **WHEN** the user answers the unscreened question with focus on its button
- **THEN** focus moves to the cancel button when the pass goes on, and to the pass button when the aborted pass has ended

### Requirement: No cancel while storing
While a pass stores its scores, the pool view SHALL NOT let the user cancel it, since storing always finishes, and SHALL say so below the button.

#### Scenario: Pass stores
- **WHEN** a pass reaches the storing phase
- **THEN** the view says the scores are being stored and that this cannot be cancelled, and a press on the button does nothing

### Requirement: Result of a cancelled pass
When a cancelled pass has stopped, the pool view SHALL say below the pass button, where its progress was, that the pass was cancelled and how many postings it scored, and the ranking SHALL show the scores it stored. Like the report of a check, this notice SHALL stay, also over a reload, until the user dismisses it or the next pass starts.

#### Scenario: Notice kept until dismissed
- **WHEN** a pass was cancelled after 4 scores and the user reloads the page
- **THEN** the notice still says so, and it goes once the user dismisses it

#### Scenario: Cancelled after some scores
- **WHEN** a pass is cancelled after it scored 30 postings
- **THEN** the view says it was cancelled with 30 postings scored, and those 30 show their new scores in the ranking

#### Scenario: Cancelled before any score
- **WHEN** a pass is cancelled while it checks
- **THEN** the view says it was cancelled with no posting scored, and the ranking is unchanged

### Requirement: Posting page
The UI SHALL give each posting its own address (hash route `#/anzeigen/<id>`), and a posting the agent names in a chat answer SHALL link to it. The page SHALL show the full text, the original link, the score with its reasoning, the rating with chips and note, the application status and the import origin, and SHALL allow rating and setting the status. It SHALL also let the user correct the title, company and location behind "Bearbeiten", for postings whose fields intake read wrongly.

#### Scenario: Correct a posting's fields
- **WHEN** the user opens "Bearbeiten" on a posting page, changes the company and saves
- **THEN** the page shows the new company, and the pool lists the posting under it

#### Scenario: Link from the chat
- **WHEN** the agent names a stored posting in an answer
- **THEN** the chat shows a link to that posting's page

### Requirement: Score button
The posting page and every row of the pool view SHALL offer a button that scores this one posting now.

#### Scenario: Button offered
- **WHEN** the user opens a posting page or the pool view
- **THEN** the page and every row show the button

### Requirement: Score button disabled where no score is possible
For a posting an exclusion rule matches, the content guard holds, or the content guard never checked while no classifier is configured, the button SHALL be disabled, with a visible info icon beside it that shows the reason on hover and on keyboard focus and gives it to screen readers. A posting both held and excluded SHALL show the content guard as its reason.

#### Scenario: Excluded posting
- **WHEN** the user sees the button of a posting an exclusion rule matches and the content guard does not hold
- **THEN** the button is disabled, and pointing at or focusing the info icon beside it says that the posting is excluded by its rules

#### Scenario: Held posting
- **WHEN** the user sees the button of a posting the content guard holds, whether or not an exclusion rule matches
- **THEN** the button is disabled, and its info icon says the content guard holds it

#### Scenario: Unchecked posting without a classifier
- **WHEN** the user sees the button of a posting the content guard never checked and no exclusion rule matches, and no classifier is configured
- **THEN** the button is disabled, and its info icon says the posting was never checked

### Requirement: Score button progress and result
While a score computes, its button SHALL show progress, and the posting page SHALL keep an earlier score visible, marked as being recomputed. When it ends, the page SHALL show the new score with its reasoning, the row its new score with its other marks unchanged, and the pool its updated counter and pass count. A failure or a busy refusal SHALL show its reason with a retry; a refusal a retry cannot change (excluded, held, never checked) SHALL instead disable the button with its info icon.

#### Scenario: Score from the posting page
- **WHEN** the user presses the button on the page of a posting without a score
- **THEN** the button shows progress, and then the page shows the score with its reasoning

#### Scenario: Re-score keeps the old score visible
- **WHEN** the user presses the button on a posting with score 7
- **THEN** the page shows the 7 marked as being recomputed until the new score replaces it

#### Scenario: Score from the pool
- **WHEN** the user presses the button on a row of the pool
- **THEN** the row shows the new score, and the counter and the count on the pass button are updated

#### Scenario: Flagged on the click
- **WHEN** the user presses the button on a posting never checked, and the check it triggers flags the posting
- **THEN** no score is stored, and the button turns disabled with its info icon saying the content guard holds it

#### Scenario: Pass running
- **WHEN** the user presses the button while a pass computes
- **THEN** the view says another scoring is computing, and stores no score

### Requirement: Import view
The UI SHALL offer the import as the source "Liste" of the view for adding postings, next to link, text and PDF, not as a separate entry of the main navigation, and SHALL keep a running import and its report when the user switches to another source or view. It SHALL let the user upload a job list file and SHALL then show the entry tables found and the import mapping as a form: the status column, a choice of "offen", "beworben", "erledigt" or "überspringen" for each of its values, and an optional assessment column, prefilled from the stored mapping. The form SHALL mark each table that lacks the chosen status column as not imported, SHALL mark each status value the stored mapping does not name as new, and SHALL warn when no status column is chosen although the stored mapping names one, since every table with links is then imported with every entry open. Confirming the form stores the mapping and starts the import. The UI SHALL show the import's progress while it runs and, when it ends, the report: the counts (imported, duplicate, skipped by status, skipped as link gone, failed), every entry not imported with its row text, link and reason, each table left out for lacking the status column with its number of entries, and each already stored posting whose application status differs from the list's, with its title, company and both statuses, letting the user take the list's status or keep the app's. The import SHALL NOT be started or inspected by any means other than the UI.

#### Scenario: Upload a list
- **WHEN** the user uploads a list with 20 entries and confirms the mapping
- **THEN** the view shows progress, and at the end the counts per outcome, which add up to 20, and lists the entries that were not imported

#### Scenario: Mapping remembered
- **WHEN** the user uploads a list again after an earlier import
- **THEN** the form shows the mapping stored by the earlier import

#### Scenario: New status value
- **WHEN** the list holds a status value the stored mapping does not name
- **THEN** the form marks that value as new, with "offen" chosen until the user picks another

#### Scenario: Table without the status column
- **WHEN** one table of the list lacks the chosen status column
- **THEN** the form marks it as not imported, and the report names it with its number of entries

#### Scenario: Upload again after an interruption
- **WHEN** the application restarted during an import and the user uploads the same file again
- **THEN** entries already stored count as duplicates and the rest is imported

#### Scenario: Status differs from the list
- **WHEN** the list says "beworben" for a stored posting whose status in the app is open
- **THEN** the report lists that posting with "App: offen · Liste: beworben", and taking the list's status stores "beworben" while keeping the app's changes nothing

### Requirement: Several links at once
The intake view SHALL accept several URLs at once, one per line, and SHALL show the outcome of each: stored, duplicate of a stored posting, closed with its attempts, or failed with its attempts. A failed or closed URL SHALL NOT stop the others.

#### Scenario: Three links
- **WHEN** the user submits three URLs and the second cannot be read
- **THEN** the first and third are stored, and the view lists the second with its attempts and the text and PDF options

#### Scenario: A closed link among several
- **WHEN** the user submits two URLs and the first ends closed
- **THEN** the view lists the first as „Stelle geschlossen“ with its attempts, and the second with its own outcome

### Requirement: Version and backend shown
The UI SHALL show, on every view, the version of the loaded frontend, the version the backend reports, and the origin the page's requests go to. A page from a release image SHALL show the release tag as both versions; a local or CI build SHALL show `dev`. The display SHALL name no host or address beyond the origin the browser already uses.

#### Scenario: Released page
- **WHEN** the user opens the app served by the image of release `v0.1.0`
- **THEN** the footer shows `v0.1.0` as the frontend version and as the backend version, and the origin the page was opened from

#### Scenario: Local build
- **WHEN** the user opens the app from a local or CI build
- **THEN** the footer shows `dev` as both versions

### Requirement: Backend version unavailable
While no backend version has been fetched successfully, the display SHALL say the backend version is unknown and SHALL NOT report a mismatch. A later failed fetch SHALL leave the last backend version fetched in place. A backend that reports a failing check still reports its version, so that version counts as fetched, and the display SHALL NOT show the status.

#### Scenario: Backend unreachable on load
- **WHEN** the backend version cannot be fetched when the page loads
- **THEN** the footer shows the frontend version and that the backend version is unknown, and no mismatch is reported

#### Scenario: Refetch fails after a version was shown
- **WHEN** the footer shows the backend version and a later fetch fails
- **THEN** the footer keeps showing the last backend version fetched

#### Scenario: Backend reports a failing check
- **WHEN** the backend's health answer says `fail` and carries its version
- **THEN** the footer shows that version as the backend version, and shows no status

### Requirement: Stale page is announced
The UI SHALL fetch the backend version when the page loads and again whenever the tab becomes visible. When the backend version differs from the frontend's version, the UI SHALL show a banner that says the page is out of date and offers a reload button. The UI SHALL NOT reload the page by itself.

#### Scenario: Tab open across an update
- **WHEN** a tab loaded with `v0.1.0` stays open while the server is updated to `v0.2.0`, and the user returns to the tab
- **THEN** the banner says the page runs `v0.1.0` and the server `v0.2.0` and offers a reload button, and no view's input is lost until the user reloads

#### Scenario: Reload after the banner
- **WHEN** the user presses the reload button
- **THEN** the page reloads, loads the frontend of the new release, and shows no banner

#### Scenario: Versions agree
- **WHEN** the frontend and the backend report the same version
- **THEN** no banner is shown

### Requirement: The banner follows the latest version fetched
The banner SHALL follow the latest backend version fetched successfully: it is shown while that version differs from the frontend's, it is removed when a fetch shows them equal, and a failed fetch leaves it as it is. A health answer that reports a failing check still carries the version, so it is a successful fetch; a fetch fails only when no version is obtained.

#### Scenario: Refetch fails while the banner is shown
- **WHEN** the banner is shown and a later fetch of the backend version fails, so that no version is obtained
- **THEN** the banner stays

#### Scenario: Failing check while the versions differ
- **WHEN** a tab loaded with `v0.1.0` returns while the server runs `v0.2.0` and its health answer says `fail`
- **THEN** the banner says the page runs `v0.1.0` and the server `v0.2.0`, as it would for a healthy answer

#### Scenario: Server returns to the loaded version
- **WHEN** the banner is shown and a later fetch returns the frontend's own version
- **THEN** the banner is removed without a reload

### Requirement: Date a posting was added
Each pool row and the posting page SHALL show, above the title, a line with „Hinzugefügt“ followed by the date and time to the minute at which the posting was added.

#### Scenario: Two postings added on one day
- **WHEN** the pool holds two postings added on 12 November 2026 at 09:41 and at 14:05 local time
- **THEN** their rows show „Hinzugefügt 12.11.2026, 09:41“ and „Hinzugefügt 12.11.2026, 14:05“

#### Scenario: Same date on the posting page
- **WHEN** the user opens the posting page of a posting from the pool
- **THEN** the page shows the same „Hinzugefügt …“ line as the posting's pool row

### Requirement: Added date in German form
The added date SHALL be written as day, month and four-digit year separated by dots, then a comma and the time as hours and minutes, each two digits.

#### Scenario: Single-digit day, month and hour
- **WHEN** a posting was added on 5 January 2026 at 09:03 local time
- **THEN** the line shows „Hinzugefügt 05.01.2026, 09:03“

### Requirement: Added date in the browser's time zone
The added date SHALL be shown in the browser's time zone.

#### Scenario: Date across midnight
- **WHEN** a posting was added at 23:30 UTC on 11 November 2026 and the browser's time zone is Europe/Berlin
- **THEN** the line shows „Hinzugefügt 12.11.2026, 00:30“

### Requirement: Added date as secondary information
The added-date line SHALL be set smaller and with lower contrast than company and place, and SHALL still meet the contrast the requirement "Accessible and consistent presentation" sets, in both themes.

#### Scenario: Contrast in both themes
- **WHEN** the contrast check runs on the line's colour in the light and the dark theme
- **THEN** it reaches 4.5:1 on the page background and on a card, and stays below the contrast of company and place

### Requirement: Backup button on every view
Every view SHALL show a backup button. It SHALL be highlighted while the backend reports something not backed up yet, and quiet otherwise.

#### Scenario: After a rating
- **WHEN** the user rates a posting after a successful backup
- **THEN** the button is highlighted

#### Scenario: Nothing pending
- **WHEN** the backend reports nothing pending
- **THEN** the button is shown without the highlight

### Requirement: Backup status kept current
The UI SHALL fetch the backup status when the page loads, when the tab becomes visible, every second while a backup runs, and every 15 seconds otherwise while the tab is visible. A failed fetch SHALL leave the last status shown.

#### Scenario: Change made outside the app
- **WHEN** a file in the data repository is changed by hand while the tab is open and visible
- **THEN** the button is highlighted within 15 seconds

### Requirement: Backup unavailable
When the backend reports the backup as unavailable, the button SHALL be disabled, with a visible, focusable info icon that gives the reason.

#### Scenario: Data directory without git
- **WHEN** the data repository is a plain copied directory
- **THEN** the button is disabled and its info icon says the data directory is not a git repository

### Requirement: Backup progress shown
While a backup runs, the UI SHALL show its current step, the number of files being committed and, during the push, the share git reports as done, so the user can see where it stands.

#### Scenario: Push under way
- **WHEN** a backup of 40 files is pushing and the backend reports 60 percent
- **THEN** the UI shows that it is pushing, the 40 files and 60 percent

### Requirement: Backup progress and result
A press SHALL start a backup and disable the button until it ends. Afterwards the UI SHALL show the result: success, committed without a remote, or the failure with its reason. A failure SHALL leave every view usable, and the button SHALL stay enabled for a retry.

#### Scenario: Successful backup
- **WHEN** the user presses the highlighted button and the backup succeeds
- **THEN** the button is quiet and the UI shows the time of this backup

#### Scenario: Push fails
- **WHEN** the user presses the button and the push fails
- **THEN** the UI shows the reason, the button stays highlighted and enabled, and the open view keeps working

#### Scenario: No remote
- **WHEN** the data repository has no remote and the user presses the button
- **THEN** the UI says the changes were committed and not pushed because no remote is set

### Requirement: Last successful backup shown
Next to the backup button, the UI SHALL show the time of the last successful backup, or that there has been none yet while changes are not backed up.

#### Scenario: No backup yet
- **WHEN** no backup has succeeded for this data repository and changes are not backed up
- **THEN** the UI says there has been no backup yet

#### Scenario: Nothing to back up and no backup yet
- **WHEN** no backup has succeeded for this data repository, it has a remote and nothing is waiting to be backed up
- **THEN** the UI says there is nothing to back up, not that there has been no backup, so the line does not contradict the quiet button

#### Scenario: No remote and no backup yet
- **WHEN** no backup has succeeded for this data repository, it has no remote and nothing is waiting to be backed up
- **THEN** the UI says that no remote is set and that there has been no backup yet, because nothing can have been pushed

### Requirement: Pasting an alert mail keeps its links
The alert-mail input SHALL take the HTML of a pasted mail, so the links behind titles and buttons are kept, and SHALL show the pasted text. A paste without HTML SHALL be read as plain text. When the mail yields no posting, the view SHALL say so and point to the link and text inputs. While screening is off, the view SHALL say that only known senders' mails can be read. When some links of the mail were not read, the view SHALL name their hosts and say to paste that mail alone.

#### Scenario: Links not read
- **WHEN** a pasted mail holds LinkedIn postings and links on another host that no fixed rule reads
- **THEN** the view lists the LinkedIn postings and says that the links of that host were not read, and that the mail should be pasted alone

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

### Requirement: Alert mail duplicate by text
An entry the run reports as a duplicate by link SHALL show the stored posting with a link to it, and offer no way to store it again. An entry reported as a duplicate by text SHALL show the stored posting it matches and offer "Trotzdem als neue Anzeige speichern", which SHALL ask for confirmation, naming that posting, before it stores anything.

#### Scenario: Duplicate by text
- **WHEN** the run reports an entry as a duplicate by text
- **THEN** the view shows the matching stored posting with a link, and offers to store the entry anyway

#### Scenario: Confirmed
- **WHEN** the user chooses to store it anyway and confirms
- **THEN** the entry is added as a new posting, and its row shows it as stored

#### Scenario: Not confirmed
- **WHEN** the user chooses to store it anyway and cancels the confirmation
- **THEN** nothing is stored, and the row still shows the duplicate

#### Scenario: Duplicate by link
- **WHEN** the run reports an entry as a duplicate by link
- **THEN** the row shows the stored posting with a link and offers no way to store it again

### Requirement: Alert mail run refused or lost
When a run is refused because another one computes, the view SHALL show that run's progress. When the server no longer knows a run, because it restarted, the view SHALL say so and offer to start over.

#### Scenario: Run already computing
- **WHEN** the user adds entries while another alert-mail run computes
- **THEN** the view shows the computing run's progress

#### Scenario: Server restarted
- **WHEN** the server restarted during a run
- **THEN** the view says the run is no longer known and offers to paste the mail again

### Requirement: Score range and sort controls
The pool view SHALL show the score range and the sort choice in one row with the text filter, above the state filters, stacked at a phone's width. Both SHALL be operable by keyboard alone and usable at a phone's width without scrolling sideways.

#### Scenario: Keyboard only
- **WHEN** the user sets the range and the sort using only the keyboard
- **THEN** the list follows each choice, and focus stays on the control that changed

#### Scenario: Phone width
- **WHEN** the pool view is shown 390 pixels wide
- **THEN** the range and the sort are fully visible and usable, and the page does not scroll sideways

### Requirement: Keyboard follows the shown order
J and K SHALL move to the next and the previous posting in the order the pool shows, and Enter to the next unrated posting in that order.

#### Scenario: Sorted by added date
- **WHEN** the pool is sorted by added date, ascending, and the user presses J on the first posting
- **THEN** the selection moves to the posting added second earliest

### Requirement: Pass button
The pass button SHALL be a split button. Its main part SHALL name the shown variant and its count, for example „Anzeigen ohne Score scoren (3)“, and start that variant. When the shown variant has nothing to score, the main part SHALL be inert, with a visible, focusable info icon beside the button that gives the reason, and the menu SHALL stay usable. While a pass computes, the split button SHALL give way to the cancel button.

#### Scenario: Cost before the start
- **WHEN** the shown variant is „Alle Anzeigen neu scoren“ with 40 postings and the user opens the menu
- **THEN** the main part reads „Alle Anzeigen neu scoren (40)“, and the menu says 40 postings at one model call each, replacing existing scores

#### Scenario: Size stays when the variant changes
- **WHEN** the user switches the shown variant
- **THEN** the main part keeps its width, and the counter line below stays in its place

#### Scenario: Nothing without a score
- **WHEN** every posting neither excluded nor held has a score and the shown variant is „Anzeigen ohne Score scoren“
- **THEN** the main part is inert, its info icon gives the reason, and the menu still offers „Alle Anzeigen neu scoren“

### Requirement: Pass variant menu
The menu beside the main part SHALL list both variants, each with its count and its cost, and mark the shown one. Choosing an entry SHALL make it the shown variant and SHALL NOT start a pass. A variant chosen by hand SHALL stay shown until the pool loads again (a page reload, or the reload after a pass) or the default variant changes. The menu SHALL be operable by keyboard, and its trigger SHALL have an accessible name.

#### Scenario: Choosing does not start
- **WHEN** the user opens the menu and chooses „Alle Anzeigen neu scoren“
- **THEN** the main part reads „Alle Anzeigen neu scoren (N)“, and no pass starts

#### Scenario: Shortcuts stay off in the menu
- **WHEN** the menu has focus and the user presses a rating key, j, k, n or Enter
- **THEN** no rating is stored and the selected posting stays as it was; Enter chooses the focused entry

#### Scenario: Default change replaces the choice
- **WHEN** the user chose „Anzeigen ohne Score scoren“ while the default was „Alle Anzeigen neu scoren“, and a rating moves the hint to „Ranking passt gut“ and back to „neu scoren sinnvoll“
- **THEN** the main part shows „Alle Anzeigen neu scoren“

#### Scenario: Reload drops the choice
- **WHEN** the user chose „Alle Anzeigen neu scoren“ below the thresholds and reloads the page
- **THEN** the main part shows „Anzeigen ohne Score scoren“

#### Scenario: Pass end drops the choice
- **WHEN** the user chose „Alle Anzeigen neu scoren“ below the thresholds and that pass ends
- **THEN** the main part shows „Anzeigen ohne Score scoren“ again

### Requirement: Scoring wording
UI texts SHALL say „scoren“ or „Score“ for the AI's scoring, and „bewerten“ or „Bewertung“ only for the user's own rating.

#### Scenario: Pass progress
- **WHEN** a pass computes
- **THEN** its progress says „Scoren läuft“ with the counts, and no text about the pass says „Bewertung“

#### Scenario: Rating texts unchanged
- **WHEN** the user filters the pool to „Noch nicht bewertet“
- **THEN** the filter keeps that name, because it is about the user's own rating

### Requirement: Availability check button
The pool view SHALL offer „Verfügbarkeit prüfen“ beside the pass button, naming how many postings the check will cover. When it covers none, the button SHALL be disabled, with a visible, focusable info icon that says why.

#### Scenario: Nothing to check
- **WHEN** no open posting has a link the check can fetch
- **THEN** the button is disabled, and its info icon says there is nothing to check

### Requirement: Availability check progress and report
While a check runs, the pool view SHALL show below its button how many of its postings are done, and SHALL NOT offer a second start. When the check ends, the view SHALL load the pool again and show the report in the same place: how many postings it found closed, available and unknown, and each posting it newly closed with a link to its page. The report SHALL list the first three closed postings and the rest behind a toggle, and the user SHALL be able to dismiss it.

#### Scenario: Check from the pool
- **WHEN** the user presses „Verfügbarkeit prüfen“ and the check finds 2 postings closed
- **THEN** the view shows the progress, then the report with 2 closed and both postings linked, and the two are no longer listed under „Offen“

#### Scenario: Unknown postings named in the report
- **WHEN** 4 postings of a check answer HTTP 429
- **THEN** the report counts 4 unknown, and those postings stay listed

#### Scenario: Many closed postings
- **WHEN** a check finds 5 postings closed
- **THEN** the report links the first three and offers the other two behind „2 weitere anzeigen“

### Requirement: Availability check refused or lost
When a check is refused because another one runs, the view SHALL show that check's progress. Switching to another view and back, and reloading the page, SHALL keep the check and its report while the server still knows the check. When the server no longer knows it, because it restarted, the view SHALL say so and offer „Verfügbarkeit prüfen“ again.

#### Scenario: Reload during a check
- **WHEN** the user reloads the pool view while a check runs
- **THEN** the view shows the running check's progress

#### Scenario: Server restarted
- **WHEN** the server restarted during a check
- **THEN** the view says the check is no longer known and offers to start a new one

### Requirement: Closed mark on a row
Wherever the pool view lists a closed posting, its row SHALL carry the mark „Stelle geschlossen“, and the user SHALL be able to rate it from the row.

#### Scenario: Rate a closed posting from its filter
- **WHEN** the user picks „Stelle geschlossen“ and rates a listed posting
- **THEN** the rating is stored and the row shows it, still marked as closed

#### Scenario: Closed posting under Herkunft
- **WHEN** an imported posting is closed and the user picks „Herkunft“
- **THEN** its row is listed and marked as closed

### Requirement: Posting no check can read, on its page
A posting no check can read is never checked: one added as pasted text or a PDF, and one whose links are all login-walled or not on a public host. The note below its availability on the posting page SHALL say so and SHALL NOT promise a next check, also after a hand setting. A check covers open postings only, so for a posting whose application status is not open the note of a hand setting SHALL NOT promise a next check either.

#### Scenario: Posting without a link
- **WHEN** the user opens a posting added as pasted text and sets it to closed
- **THEN** the note says it was set by hand and promises no check

#### Scenario: Only a login-walled link
- **WHEN** the user opens a posting whose only link is on a login-walled host
- **THEN** the note says no link can be checked

#### Scenario: Applied posting set by hand
- **WHEN** the user sets a posting with application status „beworben“ to closed
- **THEN** the note says it was set by hand and promises no check

### Requirement: Availability on the posting page
The posting page SHALL show the posting's availability under the title, beside „Bearbeiten“ and the application status, as a field the user can set to closed or to available. Below it the page SHALL say when the availability was set and whether a check or the user set it, or that it was never checked. For a hand setting, the note SHALL say that the next check replaces it.

#### Scenario: Close by hand
- **WHEN** the user sets an open posting to closed on its page
- **THEN** the page shows it as closed, set by hand, and the pool lists it only under „Stelle geschlossen“

#### Scenario: Reopen by hand
- **WHEN** the user sets a closed posting to available on its page
- **THEN** the page shows it as available, set by hand, with the note that the next check replaces it

### Requirement: Cancel button of a check
While a check runs, „Verfügbarkeit prüfen“ SHALL give way to „Prüfen abbrechen“, which cancels the check at once and without a confirm step. The view SHALL say that the check stops after the current posting and that what it already found stays stored. When the cancelled check has stopped, the view SHALL show its report with what it found so far, and say it was cancelled.

#### Scenario: Cancel a check
- **WHEN** the user presses „Prüfen abbrechen“ after the check found 2 of its postings closed
- **THEN** the check stops after the current posting, the 2 stay closed, and the report says the check was cancelled and lists the 2

### Requirement: Filter Stelle geschlossen
The pool view SHALL offer the state filter „Stelle geschlossen“, listing the closed postings with application status open. The filters „Offen“, „Noch nicht bewertet“ and „Bewertet“ SHALL NOT list closed postings.

#### Scenario: Closed posting moves to its filter
- **WHEN** a check closes an unrated posting
- **THEN** „Noch nicht bewertet“ no longer lists it, and „Stelle geschlossen“ does

### Requirement: Result of a finished pass
When a pass has finished, the pool view SHALL say below the pass button, where its progress was, that the pass is done and how many postings it scored, like the report of a finished check. The notice SHALL stay, also over a reload, until the user dismisses it or the next pass starts.

#### Scenario: Pass finished
- **WHEN** a pass finishes after scoring 12 postings
- **THEN** the view says the pass is done with 12 postings scored, and the notice goes once the user dismisses it

### Requirement: Counter line below the pass button
Directly below the pass button the pool view SHALL show one line with the correction counter, the hint of the pool, and the share of corrections or how many ratings the share still needs. How many postings each pass variant scores and at how many model calls SHALL be said only in the pass button's menu.

#### Scenario: Counter below the button
- **WHEN** the pool has 3 corrections and 7 ratings
- **THEN** the line below the pass button reads „3 Korrekturen · Ranking passt gut · Anteil ab 10 Bewertungen (bisher 7)“

### Requirement: Labels for application status and availability
Wherever the UI shows the application status, it SHALL label it „Bewerbungsstatus“, and a closed posting SHALL read „Stelle geschlossen“, so the two states are not mistaken for one another. On the posting page, „Bearbeiten“, the application status and the availability SHALL sit in one row under the title.

#### Scenario: Closed but status open
- **WHEN** a closed posting with application status open is listed
- **THEN** its row shows „Stelle geschlossen“ and the field „Bewerbungsstatus“ reading „offen“

### Requirement: Delete button in a pool row
Each pool row SHALL hold a delete button right of „Bewerbungsstatus“. The button SHALL show a trash icon and no text, and SHALL be named „Anzeige löschen“ for screen readers. After a confirmed delete the row SHALL disappear without a page reload, and the counter, the pass button and the check button SHALL show the pool without the posting.

#### Scenario: Delete from the pool
- **WHEN** the user presses the trash button of a row and confirms
- **THEN** the row disappears and the view stays where it was, with its filters and sort kept, and the focus moves to the row selected next

### Requirement: Delete button on the posting page
The posting page SHALL hold the same delete button in the head row under the title, after „Verfügbarkeit“. On that row „Bearbeiten“, the „Bewerbungsstatus“ select, the „Verfügbarkeit“ select and the delete button SHALL be equally high. After a confirmed delete the app SHALL return to the pool.

#### Scenario: Delete from the posting page
- **WHEN** the user presses the trash button on a posting's page and confirms
- **THEN** the app shows the pool, which no longer lists the posting

### Requirement: Delete confirmation
Every delete SHALL ask first, in a modal dialog titled „Anzeige löschen?“. The dialog SHALL name the posting's title and company and say that it is deleted for good, with its score. For a rated posting it SHALL also name the rating level and say that the rating stops counting as an example for scoring. „Endgültig löschen“ SHALL delete.

#### Scenario: Unrated posting
- **WHEN** the user presses the trash button of an unrated posting
- **THEN** the dialog names its title and company and mentions no rating

#### Scenario: Rated posting
- **WHEN** the user presses the trash button of a posting rated „Ja, auf jeden Fall“
- **THEN** the dialog names that rating and says it stops counting as an example for scoring

### Requirement: Keys and focus in the delete dialog
„Abbrechen“ SHALL have the focus when the delete dialog opens. Escape and „Abbrechen“ SHALL close the dialog without a delete and return focus to the trash button. While the dialog is open, the pool view's keyboard shortcuts SHALL be off. „Endgültig löschen“ SHALL send one delete per confirmation, however often it is pressed.

#### Scenario: Cancel
- **WHEN** the user presses Escape or „Abbrechen“ in the dialog
- **THEN** the dialog closes, nothing is deleted, and focus returns to the trash button

#### Scenario: Shortcut keys in the dialog
- **WHEN** the dialog is open over the pool and the user presses „1“
- **THEN** no posting is rated

#### Scenario: Double press
- **WHEN** the user presses „Endgültig löschen“ twice in quick succession
- **THEN** the app sends one delete

### Requirement: Delete disabled while a pass or a check runs
In the pool view the delete buttons SHALL be disabled while the view's scoring pass runs or waits for its answer about unscreened postings, and while an availability check runs. On the posting page the button SHALL be disabled while a pass or a single score computes or a check runs, read as the page loads and again every second while the button is disabled.

#### Scenario: Pool during a pass
- **WHEN** a pass runs and the user looks at a pool row
- **THEN** its trash button is disabled, and the info icon beside it names the running pass

#### Scenario: Posting page during a check
- **WHEN** an availability check runs and the user opens a posting's page
- **THEN** its trash button is disabled, and the info icon beside it names the running check

#### Scenario: Posting page after the check
- **WHEN** the check ends while the user stays on a posting's page with a disabled trash button
- **THEN** the button becomes usable without a page reload

### Requirement: Delete refused or failed
When the server refuses a delete because a pass, a score or a check started meanwhile, the dialog SHALL stay open and say why in words. When the delete fails for any other reason, the dialog SHALL say so and offer to try again. When the posting turns out to be gone already, the UI SHALL treat it as deleted.

#### Scenario: Pass started meanwhile
- **WHEN** the user confirms a delete on a posting page loaded before a pass started
- **THEN** the dialog says that a scoring run is in progress, and the posting stays

#### Scenario: Already gone
- **WHEN** the user confirms a delete of a posting another tab deleted already
- **THEN** the UI behaves as after its own delete

### Requirement: Reason beside a disabled delete button
A visible, focusable info icon beside each disabled delete button SHALL give the reason: „Gerade läuft ein Score-Durchlauf. Löschen geht wieder, wenn er fertig ist.“ or „Gerade läuft eine Verfügbarkeitsprüfung. Löschen geht wieder, wenn sie fertig ist.“ The reason SHALL show on hover and on keyboard focus and reach screen readers.

#### Scenario: Reason by keyboard
- **WHEN** a pass runs and the user tabs to the info icon beside a row's trash button
- **THEN** the reason about the running pass is shown and announced

### Requirement: Settings page
The header's settings button „Einstellungen“ SHALL open the settings page, reachable from every view. The page SHALL list its sections beside the content, and above it at a phone's width: „Scoren“ with the two settings of the pool's hint (threshold and rate), and „Postfach“ with the mailbox account and folders. Each section SHALL have its own address.

#### Scenario: Hint settings on the page
- **WHEN** the user opens „Einstellungen“ from the intake view, chooses „Scoren“, sets the threshold to 5 and saves
- **THEN** the pool's hint appears from 5 corrections on

#### Scenario: Section by address
- **WHEN** the user opens the address of the section „Postfach“
- **THEN** the settings page shows that section

#### Scenario: Phone width
- **WHEN** the settings page is shown 390 pixels wide
- **THEN** the sections are listed above the content, and the page does not scroll sideways

#### Scenario: Pool keys off
- **WHEN** the settings page is open and the user presses a rating key of the pool view
- **THEN** no posting is rated

### Requirement: Mailbox settings form
The section „Postfach“ SHALL offer the fields server, port (993 when empty), user name and password, and the action „Verbinden und Ordner laden“. That action SHALL store the account and, after a successful login, show the folder choice. A failed login SHALL show its reason beside the form.

#### Scenario: First connection
- **WHEN** the user enters server, user name and password and presses „Verbinden und Ordner laden“
- **THEN** the view says it is connected, names the number of folders and shows the folder choice

#### Scenario: Login refused
- **WHEN** the server refuses the login
- **THEN** the view says that the login was refused, and the fields keep their values except the password

### Requirement: Password field
The password field SHALL mask its text, and a button with an eye icon SHALL show and hide the typed text. A stored password SHALL show as eight dots, labelled as stored, and SHALL never be filled in; an empty field SHALL keep the stored password on save while server, port and user name stay the same. The section SHALL recommend an app password that the provider can revoke on its own.

#### Scenario: Show the typed password
- **WHEN** the user types a password and presses the eye button
- **THEN** the typed text is readable, and a second press masks it again

#### Scenario: Stored password kept
- **WHEN** a password is stored and the user changes only the folder choice and saves
- **THEN** the stored password stays, and the field still shows eight dots

#### Scenario: Server changed
- **WHEN** a password is stored and the user changes the server without entering a password and saves
- **THEN** the field is empty, no longer labelled as stored, and asks for the password

### Requirement: Mailbox settings without a key
When no key for the password is configured, the password field and „Verbinden und Ordner laden“ SHALL be disabled. A visible info icon that keyboard users can reach SHALL say that no key is configured and that the README explains how to set one up.

#### Scenario: No key
- **WHEN** the backend has no key configured and the user opens the section „Postfach“
- **THEN** the password field is disabled, and the info icon beside it gives the reason

### Requirement: Folder choice
After connecting, the section SHALL offer „Alle Ordner“, which includes folders created later and leaves out system folders, or „Nur diese Ordner“ with a checkbox per folder, system folders marked and unticked at first. Above the choice, the hint „Wähle nur Ordner, in denen ausschließlich Job-Alert-Mails liegen.“ SHALL stand. Saving SHALL store the choice.

#### Scenario: Selection
- **WHEN** the user chooses „Nur diese Ordner“, ticks „Posteingang“ and „Jobs“ and saves
- **THEN** checks search those two folders only

#### Scenario: Folder hint
- **WHEN** the section shows the folder choice
- **THEN** the hint to choose only folders holding job alert mails stands above it

### Requirement: Mails per check setting
The section „Postfach“ SHALL offer „Höchstens Mails pro Prüfung“, a whole number from 1 to 1000, preset to 200. Saving SHALL store it, and the next check SHALL use it. A value outside that range SHALL be refused with a message beside the field.

#### Scenario: Limit set
- **WHEN** the user sets „Höchstens Mails pro Prüfung“ to 50 and saves
- **THEN** the next check reads at most 50 mails

#### Scenario: Limit out of range
- **WHEN** the user enters 5000 and saves
- **THEN** nothing is stored, and the field says that the number must be from 1 to 1000

### Requirement: Mailbox source
The intake source „Postfach“ SHALL point to the section „Postfach“ while no mailbox is configured. Once one is, it SHALL show the account, the folder choice and the time of the last check, and „Postfach prüfen“. Before the first check it SHALL show „Mails ab“, a date preset to 30 days back, with a hint that older mails are never read and that each mail from a sender without a fixed rule costs a model call.

#### Scenario: Not configured
- **WHEN** no mailbox is configured and the user chooses the source „Postfach“
- **THEN** the view says so and links to the section „Postfach“ of the settings page

#### Scenario: First check
- **WHEN** a mailbox is configured but never checked
- **THEN** the view shows „Mails ab“ preset to 30 days back with the cost hint, and „Postfach prüfen“

#### Scenario: Later checks
- **WHEN** the mailbox was checked before
- **THEN** the view shows no „Mails ab“ field, only the time of the last check and „Postfach prüfen“

### Requirement: Mailbox check progress and outcome
While a check runs, the view SHALL show how many new mails it found and how many it has read, and „Postfach prüfen“ SHALL be disabled. A check without new mails SHALL say so. A failed check SHALL show its reason with „Erneut versuchen“ and a link to the settings. A stored password the key cannot decrypt SHALL be named, with a link to enter it again. Switching away and reloading the page SHALL keep a running check's progress.

#### Scenario: Progress
- **WHEN** a check found 12 new mails and has read 5
- **THEN** the view shows 12 found and 5 read, and „Postfach prüfen“ is disabled

#### Scenario: Nothing new
- **WHEN** a check finds no unhandled mail
- **THEN** the view says that there are no new mails since the start date

#### Scenario: Server not reachable
- **WHEN** a check ends because the server did not answer
- **THEN** the view says the server is not reachable, and offers „Erneut versuchen“ and the settings

### Requirement: Cancel button of a mailbox check
While a check runs, the view SHALL offer „Prüfen abbrechen“, which cancels the check at once and without a confirm step. The view SHALL say that the check stops after the current mail and that the mails read so far stay in the pick list. When the cancelled check has stopped, the view SHALL show its pick list and report, with a note that it was cancelled after N of M mails.

#### Scenario: Cancel a check
- **WHEN** the user presses „Prüfen abbrechen“ after the check has read 37 of 200 mails
- **THEN** the check stops after the current mail, and the view shows the pick list of the mails read with the note that the check was cancelled after 37 of 200 mails

### Requirement: Mailbox pick list grouped by mail
A finished check SHALL show the entries of all its mails in one list, grouped by mail, with the rules of the alert mail pick list for each entry. Each mail head SHALL show the sender, and the subject, date and folder in one line below it, stacked at a phone's width. „N Anzeigen hinzufügen“ SHALL add all selected entries, and „Nichts hinzufügen“ none; the view SHALL say which mails count as handled afterwards („Note on handled mails below the pick list“).

#### Scenario: Three mails
- **WHEN** a check read three mails with seven entries, one already stored
- **THEN** the list shows three mail heads with their entries, six of them selected, and „6 Anzeigen hinzufügen“

#### Scenario: Nothing added
- **WHEN** the user presses „Nichts hinzufügen“
- **THEN** no entry is added, and the mails of the check are not offered again

### Requirement: Oversized mail in the pick list
A mail the check did not read because it is too large SHALL appear in the pick list as its own mail head with sender, subject, date and folder, the note „Zu groß, nicht gelesen“ and a checkbox that is not ticked.

#### Scenario: Oversized mail not ticked
- **WHEN** the user presses „N Anzeigen hinzufügen“ without ticking an oversized mail
- **THEN** no entry of that mail is added, and the mail is not offered again

### Requirement: Reading an oversized mail from the pick list
Ticking an oversized mail's checkbox SHALL read the mail, show that it is being read, and then show its entries below the head like those of any other mail. A failed reading SHALL show its reason at the head and leave the checkbox unticked. While the mail is being read, „N Anzeigen hinzufügen“ and „Nichts hinzufügen“ SHALL be disabled, with the reason.

#### Scenario: Oversized mail ticked
- **WHEN** the user ticks the checkbox of an oversized mail
- **THEN** the view shows that the mail is being read, and then its entries appear below the head

### Requirement: Mailbox check report
Above the pick list, the view SHALL name, each as a short note: the number of mails left for the next check, chosen folders that no longer exist, mails whose reading failed, mails held by the content guard, mails not read while screening is off, and an interrupted connection. A mail head SHALL carry the notes of the pasted alert mail for that mail (hosts not read, more than 100 entries).

#### Scenario: Mails left
- **WHEN** a check read 200 mails and 60 remain
- **THEN** a note says that 60 mails are left for the next check

#### Scenario: Failed and held mails
- **WHEN** a check could not read one mail and the content guard held another
- **THEN** a note names each with its sender and subject, and neither appears in the pick list

### Requirement: Mailbox pick list kept when adding is refused
When finishing a check's pick list is refused because another alert run computes, the view SHALL show that run's progress and keep the pick list, so it can be finished afterwards.

#### Scenario: Alert run busy
- **WHEN** the user adds entries while another alert run computes
- **THEN** the view shows the computing run's progress, and the pick list can be finished afterwards

### Requirement: Select a mail's entries at once
Each mail head SHALL have a checkbox that selects all selectable entries of that mail when not all are selected, and clears them otherwise. It SHALL show a dash while only some are selected. The head SHALL show „n von m ausgewählt“ for its mail.

#### Scenario: Clear a mail
- **WHEN** all three selectable entries of a mail are selected and the user clears the mail's checkbox
- **THEN** none of them is selected, the head shows „0 von 3 ausgewählt“, and the add button counts three fewer

#### Scenario: Some selected
- **WHEN** one of a mail's two entries is selected
- **THEN** the mail's checkbox shows a dash

### Requirement: Collapse a mail
Each mail head SHALL have a button that collapses and expands the mail's entries. A collapsed mail SHALL keep its selection and keep showing its head with „n von m ausgewählt“.

#### Scenario: Collapse
- **WHEN** the user collapses a mail with two of three entries selected
- **THEN** its entries are hidden, its head shows „2 von 3 ausgewählt“, and the add button still counts them

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
- **THEN** the row shows „Nicht beurteilbar“ with the explanation and the text and PDF options, and its attempts behind „Details“

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

### Requirement: Note on handled mails below the pick list
Below the mailbox pick list, the view SHALL say that every mail of the pick list counts as handled once its entries are being added, that a mail from which nothing is added counts as handled at once, and that links that cannot be read are kept under „Offene Links“ instead of bringing their mail back.

#### Scenario: Note below the pick list
- **WHEN** a check ends with a pick list
- **THEN** the note below it says that its mails count as handled once their entries are being added, and that links that cannot be read are kept under „Offene Links“

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

### Requirement: Unsettled links named after a run
When a run, from a mailbox check or a pasted mail, ends with entries not read, not judgeable or not reached, ends crashed, or is no longer known to the server, its report SHALL say that those links are kept under „Offene Links“ and SHALL link there. The report of a mailbox run SHALL NOT say that the next check offers its mails again.

#### Scenario: Failed entries after a mailbox run
- **WHEN** a mailbox run ends with three entries failed
- **THEN** the report says that their links are kept under „Offene Links“, links there, and does not say that the next check offers their mails again

#### Scenario: Mailbox run no longer known
- **WHEN** the server restarted during a mailbox run
- **THEN** the view says the run is no longer known and that the links not added are kept under „Offene Links“

#### Scenario: Pasted run with a failed entry
- **WHEN** a run of a pasted mail ends with one entry failed
- **THEN** the report says that its link is kept under „Offene Links“

### Requirement: Unsettled links tab
„Anzeige hinzufügen“ SHALL offer the source „Offene Links“ next to „Postfach“. It SHALL list the unsettled links in rows of neutral colour, with only the outcome word in colour, unlike the red rows of failed entries in the run view.

#### Scenario: List after a run
- **WHEN** a mailbox run has ended with two entries not read and one not judgeable, and the user opens „Offene Links“
- **THEN** the tab lists the three links with outcome, title, source „Postfach“, „in 1 Lauf abgerufen“ and the time of that try, in rows without a red background

#### Scenario: Another device
- **WHEN** the user opens „Offene Links“ on another device after the run
- **THEN** it lists the same links

### Requirement: Row of an unsettled link
A row SHALL show its outcome („Wartet“, „Nicht gelesen“, „Nicht beurteilbar“ or „Nicht gestartet“, the run view's word for a link a run did not reach), its title, its link (opening in a new tab), its source („Postfach“ or „Alert-Mail“), in how many runs it was fetched („in 2 Läufen abgerufen“), the date it entered the list and when it was last tried. The attempts of its last try SHALL sit behind „Details: n Versuche“, like those of a run row.

#### Scenario: Link not reached
- **WHEN** a run was cancelled before it reached a link that was not in the list before
- **THEN** its row shows „Nicht gestartet“, „noch in keinem Lauf abgerufen“ and that the run ended before it reached the link

### Requirement: Unsettled links tab address and empty states
The tab „Offene Links“ SHALL have its own address, so a reload and the link of a run report open it. Without unsettled links, it SHALL say that no link is open. When the list cannot be read, it SHALL say so and name the file.

#### Scenario: Empty list
- **WHEN** no link is open and the user opens „Offene Links“
- **THEN** the tab says that no link is open

#### Scenario: Reload on the tab
- **WHEN** the user reloads the app while „Offene Links“ is open
- **THEN** „Offene Links“ is open again

#### Scenario: Unreadable list
- **WHEN** the list file in the data repository is invalid and the user opens „Offene Links“
- **THEN** the tab says that the list cannot be read and names the file, and no badge shows

### Requirement: Count of unsettled links
The source tab „Offene Links“ and the navigation item „Anzeige hinzufügen“ SHALL each show, as a badge, the number of unsettled links that need attention: every link of the list except those a computing run still has to fetch. At 0 there SHALL be no badge. The number SHALL be part of the accessible name of both. It SHALL be read when the app loads and when the tab is opened, and again when a run starts, each time it ends an entry, when it ends, and after a link was removed.

#### Scenario: Open links after a run
- **WHEN** a run has ended with 12 links unsettled and the list was empty before
- **THEN** the navigation item „Anzeige hinzufügen“ and the tab „Offene Links“ show a badge with 12, and a screen reader announces the number with each name

#### Scenario: Waiting links not counted
- **WHEN** a mailbox run over 100 links starts and the list was empty before
- **THEN** no badge shows, and each link that ends not read or not judgeable raises both badges by one

#### Scenario: No open link
- **WHEN** the list of unsettled links is empty
- **THEN** neither the navigation item nor the tab shows a badge

#### Scenario: Reload
- **WHEN** the user reloads the app with five links open
- **THEN** both badges show 5

### Requirement: Remove an unsettled link
Each row of „Offene Links“ SHALL offer „Entfernen“, which removes the link at once and without a confirm step, since no posting or mail changes. The view SHALL announce the removal, update the count and move the focus to the next row, or to the list's heading after the last one. While the computing run has not yet ended a link, its „Entfernen“ SHALL be disabled, with an info icon beside it that says why.

#### Scenario: Remove a link
- **WHEN** the user presses „Entfernen“ on one of three rows
- **THEN** that row disappears, the view announces the removal, both badges show 2, and the focus is on the next row

#### Scenario: Link still in the run
- **WHEN** a run computes and the user opens „Offene Links“
- **THEN** the rows of the links still waiting in that run show „Entfernen“ disabled, and their info icon says that the run still has to fetch the link

### Requirement: Try unsettled links again
„Offene Links“ SHALL offer „Alle erneut versuchen (n)“ in its head, the only filled button of the view, and „Erneut versuchen“ in each row. Either SHALL start one alert run with those links at once, without a confirm step, and the tab SHALL then show that run in the run view, with „Zurück zu den offenen Links“ once it has ended. While an alert run computes, both SHALL be disabled, each with an info icon that says why.

#### Scenario: Try all again
- **WHEN** the list holds five links and the user presses „Alle erneut versuchen (5)“
- **THEN** a run of the five links starts, and the tab shows its progress with „Lauf abbrechen“

#### Scenario: Back to the list
- **WHEN** that run has stored one link and the user presses „Zurück zu den offenen Links“
- **THEN** the tab lists the four others, each with one more run in „in n Läufen abgerufen“

#### Scenario: Retry refused
- **WHEN** another run started on another device after the list was read, and the user presses „Erneut versuchen“
- **THEN** no run starts, and the tab shows the computing run's progress

#### Scenario: Retry while a run computes
- **WHEN** a mailbox run computes and the user opens „Offene Links“
- **THEN** „Alle erneut versuchen“ and every „Erneut versuchen“ are disabled, and their info icon says that a run is computing

#### Scenario: Phone
- **WHEN** the user opens „Offene Links“ at a phone's width
- **THEN** „Alle erneut versuchen“ spans the width below the head text, and each row's „Erneut versuchen“ and „Entfernen“ stack below its text at full width
