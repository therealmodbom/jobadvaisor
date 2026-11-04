# Spec Delta

## ADDED Requirements

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
