# Design

## Context

See proposal.md, Why. On a live guest page the box is a `section` with the CSS class `compensation` (a sibling class `compensation--above-description` is a different token), holding the heading "<employer> provided pay range", an explanatory sentence, the base pay range and, sometimes, additional compensation. It sits before the description in the document. The cut in `linkedin-posting-body` already captures elements by CSS class in document order, so the box is one more class in `LINKEDIN_CLASSES`. Pay box, description and criteria become three separate captures joined in page order, and the description is required: a page with criteria or a pay box but no description falls back to the visible text, as the requirement says.

## Decisions

**Capture the whole box by its class, not the figures.** The wording around the figures ("provided by the employer", "actual pay will be based on…") travels with them, so a reader and the extraction model can tell an employer-stated range from an estimate. Parsing the figures into a field would be a schema change and is a non-goal.

**No LLM eval.** No model is involved in the cut, so no eval applies; a unit test on the fictional fixture covers it.

## Risks / Trade-offs

- LinkedIn renames the class → the box silently drops out and the posting is stored as after `linkedin-posting-body`; the description is unaffected.
- A pay range in the text can steer the judge toward or away from a posting. That is the point of keeping it; whether scoring should weigh it is a decision for the user, not this change.
