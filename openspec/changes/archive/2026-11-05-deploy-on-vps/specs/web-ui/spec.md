# Spec Delta

## MODIFIED Requirements

### Requirement: Local single-user access
The UI SHALL be served for a single user, without accounts or login: on localhost, or when deployed, on the user's private network only. Access control is the network, never the app.

#### Scenario: Open the app
- **WHEN** the user opens the local address in a browser
- **THEN** the intake and pool views are available without a login

#### Scenario: Open the deployed app
- **WHEN** the user opens the deployed address from a device on the private network
- **THEN** the intake and pool views are available without a login
