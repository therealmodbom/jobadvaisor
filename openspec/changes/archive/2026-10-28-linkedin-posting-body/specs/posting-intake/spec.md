# Spec Delta

## ADDED Requirements

### Requirement: LinkedIn page cut to the posting body
For a posting fetched from a LinkedIn page, the system SHALL store as the posting text only the posting's description and its criteria block (such as seniority level and employment type), and SHALL NOT store the sign-in and "join" prompts, the lists of similar jobs and job titles, or the page footer. The title, company and location shown in the page's header SHALL be supplied as the posting's fields, since they are no longer part of the stored text. A description found on the page SHALL be stored whatever its length. When the page has no recognisable description, the system SHALL treat it like any other page and store its visible text.

#### Scenario: LinkedIn guest page
- **WHEN** the user submits the URL of a LinkedIn job page whose guest view holds a header, a description, a criteria block, a "Similar jobs" list and a sign-in footer
- **THEN** the stored text contains the description and the criteria block
- **AND** it contains no sign-in prompt, no similar-job title and no footer text

#### Scenario: Fields from the page header
- **WHEN** the same page is stored
- **THEN** the posting carries the header's title, company and location as its fields
- **AND** a correction by the user still replaces them

#### Scenario: Short description
- **WHEN** a LinkedIn page holds a description of only a few sentences
- **THEN** the stored text is that description and the criteria block, without similar-job or sign-in text

#### Scenario: LinkedIn page without a recognisable description
- **WHEN** a LinkedIn page yields no description
- **THEN** the stored text is the page's visible text, as for any other page

#### Scenario: Stored postings from before the cut
- **WHEN** the user runs the one-off repair on a data repository that holds LinkedIn postings stored whole
- **THEN** each text with the known whole-page layout is reduced to the description and the criteria block, without fetching the page again, and its title, company and location are unchanged
- **AND** each text that does not have that layout is left unchanged and listed in the repair's report
- **AND** scores and extracted features computed on the longer text are recomputed only on the user's request
