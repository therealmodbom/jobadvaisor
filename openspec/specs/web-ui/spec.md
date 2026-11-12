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
The UI SHALL show the pool ranked by fit, with the text filter and the state filters, each row showing title, company, score, the user's rating, application status and, where it applies, the exploration mark or the import origin. The user SHALL be able to rate a posting, change a rating and set the application status from the list. The view SHALL show the button "Neue Anzeigen bewerten" with the number of postings it will score, the correction counter, the share of corrections, the hint of the pool and the two settings (threshold and rate), and SHALL show a pass's progress. It SHALL name no run.

#### Scenario: Rate from the pool
- **WHEN** the user rates a posting in the list
- **THEN** the rating is stored and the posting shows as rated, with the counter updated

#### Scenario: Start a pass
- **WHEN** the user presses "Neue Anzeigen bewerten"
- **THEN** the view shows progress, and the new scores appear in the ranking when the pass ends

#### Scenario: Unscreened postings in a pass
- **WHEN** a pass pauses because it holds postings the content guard never checked
- **THEN** the view names those postings and offers to continue with them or abort the pass

#### Scenario: Change the hint settings
- **WHEN** the user sets the threshold to 5 and saves
- **THEN** the hint appears from 5 corrections on

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
- **THEN** the row shows the new score, and the counter and the count on "Neue Anzeigen bewerten" are updated

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
The intake view SHALL accept several URLs at once, one per line, and SHALL show the outcome of each: stored, duplicate of a stored posting, or failed with its attempts. A failed URL SHALL NOT stop the others.

#### Scenario: Three links
- **WHEN** the user submits three URLs and the second cannot be read
- **THEN** the first and third are stored, and the view lists the second with its attempts and the text and PDF options

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
- **WHEN** no backup has succeeded for this data repository and nothing is waiting to be backed up
- **THEN** the UI says there is nothing to back up, not that there has been no backup, so the line does not contradict the quiet button
