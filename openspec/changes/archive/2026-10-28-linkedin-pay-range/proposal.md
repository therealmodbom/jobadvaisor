# Proposal

## Why

The cut of a LinkedIn page to the posting body (`linkedin-posting-body`) keeps the description and the criteria block. LinkedIn also shows a pay range box above the description, for the postings whose employer supplies one. The box names the employer as its source ("This range is provided by …"), and its figures usually appear nowhere in the description, so the cut drops the only place the pay is stated. The already repaired texts keep the box.

## What Changes

- A posting fetched from a LinkedIn page also stores the pay range box when the page shows one, in front of the description. A page without a box stores none.
- The one-off repair is unchanged: it already keeps the box in the texts it trims.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `posting-intake`: the requirement "LinkedIn page cut to the posting body" names the pay range box as part of what is kept.

## Impact

- `backend/jobadvaisor/intake/fetch.py` (one more captured element), `backend/tests/test_intake_fetch.py`, the LinkedIn fixture under `fixtures/intake/pages/`.

## Non-goals

- Reading the figures into a structured field or into scoring; the text carries them, like the rest of the posting.
- Pay boxes of other portals.
