# Proposal

## Why

`company_stage` ("startup", "sme", "scale-up", "enterprise", "agency") is decided from the posting text and the company name in the prompt. A posting rarely states its employer's size or age, so the extractor answers `unknown` or from what the model remembers about well-known companies, which cannot be checked and is wrong for small ones. The extractor benchmark (#69) showed this while labelling `company_stage`; the user looks the facts up by hand on the company's LinkedIn page. Issue #79.

Verified on 2026-10-29 against two LinkedIn company pages fetched without a login: the page carries a size class (`about-us__size`, e.g. "51-200 employees") and, when the company filled it in, a founding year (`about-us__foundedOn`). The job page links to the company page (`topcard__org-name-link`).

## What Changes

- A company record in the data repository (`companies/<id>.json`): size class, founding year, the source it came from and the fetch date. One record per company, not one per posting.
- When a posting is added from a URL and its company has no record, intake looks the facts up once: the company's LinkedIn page first (the link comes from the LinkedIn job page), the employer's website as a fallback, read as schema.org `Organization` data. A failed or blocked lookup never fails the intake or changes a stored value.
- The extraction call receives the stored facts as a separate data block, labelled as coming from a lookup, next to the posting block. Only typed values (a size class, a year) reach the model, no free text from the company page.
- A one-off command fills the facts for postings stored before this change (refetching their job page for the company link), dry run by default, like the LinkedIn repair.
- The demo persona fixture gets company records for its fictional employers.

## Capabilities

### New Capabilities
- `company-facts`: the lookup of employer facts (size class, founding year) at intake, its sources and order, failure behavior, rate limit and the stored company record.

### Modified Capabilities
- `data-repository`: a company record entity with a published schema, validated on load.
- `job-triage`: feature extraction receives the stored company facts as a separate, labelled block.

## Impact

- Code: `intake/postings.py` (call after a new posting is stored), `intake/fetch.py` (the LinkedIn company link on the page), a new `intake/company_facts.py`, `tools/extraction.py` and `tools/prompts.py` (the facts block), `data/models.py`, `data/loader.py`, `data/writer.py`, `data/schemas.py` (entity), a repair command next to `data/trim_linkedin.py`.
- Callers of `extract_features` (triage graph, agent tool, benchmark, evals) pass the facts of the posting's company.
- Data repository: new `companies/` directory and `schemas/company.schema.json`; no change to existing files.
- Network: one request per company to linkedin.com (or the employer's site), with a minimum interval; nothing leaves the machine but those requests and the configured model call.
- Eval: `company_stage` accuracy in the extractor benchmark before and after, on the user's labels (design.md → Evals).

## Non-goals

- A company description or any free text from the company page: the user asked for size and founding year, and typed values give the model no injection path.
- The exact employee count, headquarters, industry or funding.
- A company register, a paid data provider or a search provider as a source.
- Refreshing a stored record: the fetch date is kept so a later change can age records out.
- Merging name variants of one employer ("Acme" and "Acme GmbH" are two records).
- Facts for postings added as pasted text or PDF, which carry no link to a company page.
- Using the facts in scoring or the judge prompt; only extraction receives them.
