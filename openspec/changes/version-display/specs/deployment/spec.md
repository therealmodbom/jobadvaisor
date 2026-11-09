# Spec Delta

## ADDED Requirements

### Requirement: The image reports its release
The image built for a release tag SHALL report that tag as its version, in the backend and in the frontend it serves, and the image built without a tag SHALL report `dev`. Both SHALL come from the same build, so that they agree for every image. The version SHALL stay the release's whatever the deployment's settings and environment hold, because it is not a setting of the deployment. The deployment documentation SHALL say where to see the running version.

#### Scenario: Version of a release image
- **WHEN** the image of release `v0.1.0` runs and a client asks the backend for its version
- **THEN** the answer is `v0.1.0`, and the frontend served by the same image carries `v0.1.0`

#### Scenario: Settings cannot change the version
- **WHEN** the deployment's settings or environment name a different version for the container of release `v0.1.0`
- **THEN** the backend still answers `v0.1.0`

#### Scenario: Image outside a release
- **WHEN** the image is built locally or by the checks of a branch
- **THEN** its backend and its frontend report `dev`

#### Scenario: Check of the built image
- **WHEN** the smoke check runs on an image built with a version
- **THEN** it fails unless the image's backend and frontend both report that version
