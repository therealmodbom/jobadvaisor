# Spec Delta

## Purpose

Regenerates the README's screenshots of the app with one command, at no model cost and with repeatable results, so a visible UI change can retake them in the same pull request.

## ADDED Requirements

### Requirement: One command regenerates every README image
One documented command SHALL build the frontend and write every image the README shows into `docs/images/`, replacing the previous files. It SHALL work from a checkout whose backend and frontend dependencies and Playwright's Chromium are installed.

#### Scenario: Retake after a UI change
- **WHEN** a developer runs the command in a checkout with installed dependencies
- **THEN** `docs/images/pool.png` and `docs/images/posting.png` are rewritten from the current frontend source

### Requirement: Temporary copy removed
The command SHALL work on a temporary copy of the demo persona and delete it when it ends, also after a failure.

#### Scenario: Run that fails
- **WHEN** the command stops with an error after the copy was made
- **THEN** no temporary copy remains

### Requirement: Configured data untouched
The command SHALL neither read nor change the configured data repository or state directory.

#### Scenario: Machine with a configured data repository
- **WHEN** the command runs on a machine whose settings name a data repository
- **THEN** that repository and its state directory are unchanged afterwards

### Requirement: No model call and no key
The command SHALL call no language model, embedding model or content-guard classifier, and SHALL need no API key.

#### Scenario: No key configured
- **WHEN** the command runs with no API key in the Keychain, the environment or `.env`
- **THEN** it writes the images and costs nothing

### Requirement: A reached model fails the command
If any code path reaches a model part, or the app answers a request with a server error, or the page reports an error, the command SHALL end with a non-zero exit code and SHALL NOT report success.

#### Scenario: A page action would start a pass
- **WHEN** a change to the command makes the app try to call the judge
- **THEN** the command exits non-zero and names the call

### Requirement: Seeded scores
Every score in the images SHALL come from a committed fixture of score files in the score file format, overlaid on the demo persona copy. The fixture SHALL hold a score for every posting the "Noch nicht bewertet" filter lists on the demo persona that no exclusion rule and no guard result blocks, and for no other posting.

#### Scenario: Every listed posting shows a score or its exclusion
- **WHEN** the pool image is taken
- **THEN** no listed posting shows "noch kein Score"

### Requirement: Captions do not claim model output
Every README image with a score SHALL have a visible line of text under it that says the scores are sample data. Neither that line nor the image's alt text SHALL say that the model produced them.

#### Scenario: Pool image in the README
- **WHEN** a reader looks at the pool image in the README
- **THEN** the line under it says the scores are sample data

### Requirement: Pool image
`docs/images/pool.png` SHALL show the "Anzeigen" pool on the demo persona, filtered to "Noch nicht bewertet", with its first listed posting selected.

#### Scenario: Current controls visible
- **WHEN** the pool image is taken
- **THEN** it shows the score range and sort controls, and the first posting with its added date and score

### Requirement: Posting page image
`docs/images/posting.png` SHALL show the page of the posting listed first in the pool image, with its score, the reasoning and the postings it was compared with.

#### Scenario: Comparison examples visible
- **WHEN** the posting page image is taken
- **THEN** the score card with the reasoning and the "Verglichen mit" list is fully inside the image

### Requirement: Backup button in its normal state
The demo persona copy SHALL be a git repository with every file committed and no remote, so the backup control in the images shows the state of a git-initialised demo copy without a remote.

#### Scenario: Backup control in the image
- **WHEN** an image is taken
- **THEN** it shows the enabled "Gesichert" button with the line "Kein Remote eingerichtet"

### Requirement: Fixed viewport
Every image SHALL be taken at a 1280 by 800 pixel viewport with scale factor 1, and only the viewport SHALL be captured.

#### Scenario: Image size
- **WHEN** an image is written
- **THEN** it is 1280 by 800 pixels

### Requirement: Fixed browser settings
Every image SHALL be taken in light mode, in the Europe/Berlin time zone and with reduced motion, after the web fonts have loaded.

#### Scenario: Time zone independent of the machine
- **WHEN** the command runs on a machine set to another time zone
- **THEN** the added date reads the same as on a machine in Europe/Berlin

### Requirement: Repeatable images
Two consecutive runs of the command on the same machine, with no change to the frontend, the fixtures or the dependencies in between, SHALL write byte-identical image files.

#### Scenario: Retake without a UI change
- **WHEN** the command runs twice in a row
- **THEN** `git status` shows no change to `docs/images/` after the second run

### Requirement: Demo persona only
The command and its fixture SHALL use only the fictional demo persona and localhost. They SHALL hold no personal data and no real host name.

#### Scenario: Fixture content
- **WHEN** a reviewer reads the score fixture
- **THEN** every posting it names belongs to the demo persona and every reasoning describes only demo persona data

### Requirement: The workflow rule names the command
AGENTS.md SHALL name the command, its prerequisites, its measured runtime and its cost, and SHALL keep the rule that a pull request with a visible UI change in an image's view retakes the images in that pull request.

#### Scenario: Developer looks up the retake
- **WHEN** a developer reads "README screenshot" in AGENTS.md
- **THEN** it names the command, what to install first, its runtime and its cost, and no longer asks for a scoring pass
