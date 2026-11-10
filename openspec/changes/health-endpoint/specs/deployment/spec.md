# Spec Delta

## ADDED Requirements

### Requirement: The backend reports its health
The backend SHALL answer a health request with its status, the result of each check and the version it runs. The one check is that the data repository loads. When it passes, the status SHALL be `ok` and the answer a success; when it fails, the status SHALL be `fail`, the check SHALL carry its error, and the answer SHALL be an error status with the same fields, so that the version is reported in both cases. The request SHALL need no credentials. The deployment's container healthcheck SHALL use it, so that a data repository that does not load shows the container as unhealthy.

#### Scenario: Data repository loads
- **WHEN** a client requests the health of a backend whose data repository loads
- **THEN** the answer is a success with status `ok`, the data repository check `ok` and the backend's version

#### Scenario: Data repository does not load
- **WHEN** a client requests the health of a backend whose data repository does not load
- **THEN** the answer is an error status with status `fail`, the data repository check carrying the load error, and the backend's version

#### Scenario: Container healthcheck
- **WHEN** the data repository of a running container stops loading
- **THEN** the container shows as unhealthy, and is not restarted by that alone

## MODIFIED Requirements

### Requirement: The image reports its release
The image built for a release tag SHALL report that tag as its version, in the backend's health answer and in the frontend it serves, and the image built without a tag SHALL report `dev`. Both SHALL come from the same build, so that they agree for every image. The version SHALL stay the release's whatever the deployment's settings and environment hold, because it is not a setting of the deployment. The deployment documentation SHALL say where to see the running version.

#### Scenario: Version of a release image
- **WHEN** the image of release `v0.1.0` runs and a client requests the backend's health
- **THEN** the answer's version is `v0.1.0`, and the frontend served by the same image carries `v0.1.0`

#### Scenario: Settings cannot change the version
- **WHEN** the deployment's settings or environment name a different version for the container of release `v0.1.0`
- **THEN** the backend's health answer still carries `v0.1.0`

#### Scenario: Image outside a release
- **WHEN** the image is built without a version, as a local build is
- **THEN** its backend and its frontend report `dev`

#### Scenario: Check of the built image
- **WHEN** the smoke check runs on an image built with a version
- **THEN** it fails unless the image's backend and frontend both report that version, whether or not a data repository is present
