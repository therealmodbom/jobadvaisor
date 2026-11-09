# Spec Delta

## ADDED Requirements

### Requirement: Version and backend shown
The UI SHALL show, on every view, the version of the loaded frontend, the version the backend reports, and the origin the page's requests go to. A page from a release image SHALL show the release tag as both versions; a local or CI build SHALL show `dev`. The display SHALL name no host or address beyond the origin the browser already uses. When the backend cannot be reached, the display SHALL say the backend version is unknown and SHALL NOT report a mismatch.

#### Scenario: Released page
- **WHEN** the user opens the app served by the image of release `v0.1.0`
- **THEN** the footer shows `v0.1.0` as the frontend version and as the backend version, and the origin the page was opened from

#### Scenario: Local build
- **WHEN** the user opens the app from a local or CI build
- **THEN** the footer shows `dev` as both versions

#### Scenario: Backend unreachable
- **WHEN** the backend version cannot be fetched
- **THEN** the footer shows the frontend version and that the backend version is unknown, and no mismatch is reported

### Requirement: Stale page is announced
The UI SHALL fetch the backend version when the page loads and again whenever the tab becomes visible. When the backend version differs from the frontend's version, the UI SHALL show a banner that says the page is out of date and offers a reload button. The UI SHALL NOT reload the page by itself, and SHALL keep the banner until the page is reloaded.

#### Scenario: Tab open across an update
- **WHEN** a tab loaded with `v0.1.0` stays open while the server is updated to `v0.2.0`, and the user returns to the tab
- **THEN** the banner says the page runs `v0.1.0` and the server `v0.2.0` and offers a reload button, and no view's input is lost until the user reloads

#### Scenario: Reload after the banner
- **WHEN** the user presses the reload button
- **THEN** the page reloads, loads the frontend of the new release, and shows no banner

#### Scenario: Versions agree
- **WHEN** the frontend and the backend report the same version
- **THEN** no banner is shown
