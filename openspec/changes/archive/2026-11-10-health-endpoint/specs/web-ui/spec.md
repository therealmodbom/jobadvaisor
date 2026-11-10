# Spec Delta

## MODIFIED Requirements

### Requirement: Version and backend shown
The UI SHALL show, on every view, the version of the loaded frontend, the version the backend reports, and the origin the page's requests go to. A page from a release image SHALL show the release tag as both versions; a local or CI build SHALL show `dev`. The display SHALL name no host or address beyond the origin the browser already uses. While no backend version has been fetched successfully, the display SHALL say the backend version is unknown and SHALL NOT report a mismatch. A later failed fetch SHALL leave the last backend version fetched in place. A backend that reports a failing check still reports its version, so that version counts as fetched, and the display SHALL NOT show the status.

#### Scenario: Released page
- **WHEN** the user opens the app served by the image of release `v0.1.0`
- **THEN** the footer shows `v0.1.0` as the frontend version and as the backend version, and the origin the page was opened from

#### Scenario: Local build
- **WHEN** the user opens the app from a local or CI build
- **THEN** the footer shows `dev` as both versions

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
The UI SHALL fetch the backend version when the page loads and again whenever the tab becomes visible. When the backend version differs from the frontend's version, the UI SHALL show a banner that says the page is out of date and offers a reload button. The UI SHALL NOT reload the page by itself. The banner SHALL follow the latest backend version fetched successfully: it is shown while that version differs from the frontend's, it is removed when a fetch shows them equal, and a failed fetch leaves it as it is. A health answer that reports a failing check still carries the version, so it is a successful fetch for the banner: it shows, keeps or removes the banner by that version like any other answer. A fetch fails only when no version is obtained.

#### Scenario: Tab open across an update
- **WHEN** a tab loaded with `v0.1.0` stays open while the server is updated to `v0.2.0`, and the user returns to the tab
- **THEN** the banner says the page runs `v0.1.0` and the server `v0.2.0` and offers a reload button, and no view's input is lost until the user reloads

#### Scenario: Reload after the banner
- **WHEN** the user presses the reload button
- **THEN** the page reloads, loads the frontend of the new release, and shows no banner

#### Scenario: Refetch fails while the banner is shown
- **WHEN** the banner is shown and a later fetch of the backend version fails, so that no version is obtained
- **THEN** the banner stays

#### Scenario: Failing check while the versions differ
- **WHEN** a tab loaded with `v0.1.0` returns while the server runs `v0.2.0` and its health answer says `fail`
- **THEN** the banner says the page runs `v0.1.0` and the server `v0.2.0`, as it would for a healthy answer

#### Scenario: Server returns to the loaded version
- **WHEN** the banner is shown and a later fetch returns the frontend's own version
- **THEN** the banner is removed without a reload

#### Scenario: Versions agree
- **WHEN** the frontend and the backend report the same version
- **THEN** no banner is shown
