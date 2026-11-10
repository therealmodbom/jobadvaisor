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
