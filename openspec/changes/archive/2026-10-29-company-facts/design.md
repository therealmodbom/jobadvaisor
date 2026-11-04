# Design

## Context

See proposal.md for the motivation. Relevant state on `origin/main`:

- `extract_features(posting, features, model)` (`tools/extraction.py`) sends one system message and one `<posting>` data block (`tools/prompts.py`). Callers: triage graph, agent tool, extractor benchmark, three evals.
- `add_from_url` (`intake/postings.py`) stores a posting from `result.page`; the LinkedIn cut (`intake/fetch.py`, `LINKEDIN_CLASSES`) captures the header fields but not the company link.
- The data repository loads entities from `<dir>/<id>.json` with `_load_directory` and publishes one JSON Schema per entity, generated from the models (`data/schemas.py`, ADR 0006).
- `research_company` (`tools/research.py`) already guesses an employer's website from its postings' URLs (`_website`) and fetches it with `download_plain`.
- Checked 2026-10-29 on two LinkedIn company pages without a login: `data-test-id="about-us__size"` holds a size class ("51-200 employees"), `about-us__foundedOn` a year; each exists only when the company filled it in. The job page's `topcard__org-name-link` points to the company page. Not checked: how long LinkedIn keeps answering guest requests at a higher rate (the lookup stays at one request per new company).

## Goals / Non-Goals

**Goals:**
- `company_stage` can use facts instead of memory, and the benchmark shows whether it helps.
- A lookup can never break the intake, and slows it by at most two requests (LinkedIn company page, then the website only when LinkedIn gave no facts), each bounded by the intake fetch timeout (`TIMEOUT_SECONDS`, 20 s), so at most about 40 s per new company.

**Non-Goals:**
- A general company-research feature; `research_company` for the agent stays as it is.
- Reading free text from a company page with a model.

## Decisions

**Record per company, keyed by the company's name as a slug and a hash.** `companies/<id>.json`, `<id>` = the posting ID slug rule applied to the company name alone (`a-z0-9-`, cut to 53 characters), a hyphen and ten hex digits of a SHA-256 of the name with case and spacing normalised (64 characters at most). The hash keeps names that slug alike ("A+B", "A B") apart, so each employer has its own record; names that differ only in case or spacing share one. Fields: `schema_version`, `name`, `size_class` (optional, `^\d[\d,]*(-\d[\d,]*|\+)$`, as LinkedIn writes it minus "employees"), `founded` (optional, four-digit year), `source` (`linkedin` or `website`: the one source that gave the facts, never a mix; for a record without facts the last source read), `source_url`, `fetched_at`. Facts go stale, and a company has many postings, so a record of its own beats copying the facts into each posting (decision, 2026-10-29). Alternative rejected: facts inside the posting file; they would multiply and a refresh would rewrite postings. Name variants stay separate records (proposal non-goal).

**One lookup module, `intake/company_facts.py`.** `look_up(company, company_url, repository root, fetch)` returns a record or `None` and swallows every error; `add_from_url` calls it after `add_submission` stored a new posting, so the lookup never sits between a posting and its storage. The LinkedIn company link rides on a new optional `Page.company_url`, filled by the LinkedIn cut from `topcard__org-name-link` (query string dropped, host forced to `www.linkedin.com`, path must start with `/company/`). No link: the employer website through `research._website`'s heuristic, moved to a shared place instead of copied. Alternative rejected: look up in the triage pass; it would repeat per run and mix a network step into scoring.

**Deterministic parsing only.** The LinkedIn page is read for `about-us__size` and `about-us__foundedOn`; a website is read for schema.org `Organization` JSON-LD (`foundingDate`, `numberOfEmployees` mapped to the same size classes). No model reads the company page, so no content-guard call is needed and nothing but a range and a year can reach the extractor: the injection path stays closed by type, not by screening. Alternative rejected: an LLM summary of the about-us text; free text from a third party needs the guard and an eval of its own, and the user asked for size and year only. Ceiling: an employer whose site has no `Organization` data yields a record without facts, and a LinkedIn page with a size class but no founding year yields a record without a year (the website is asked only when LinkedIn gave nothing; mixing sources would need a source per fact).

**Completed lookup stores a record, an incomplete one stores nothing.** Page read but nothing found, or HTTP 404/410: record without facts, no repeat. Transport error, 429, 5xx: nothing stored, the next posting of that company retries. A blocked or failing LinkedIn page ends the lookup and the website is not asked, so a stored website record never stands in for the LinkedIn facts the retry would get. A minimum interval of 2 seconds between company requests to one host, a module-level clock (`ponytail:` one process; a second process would need a shared limit).

**The facts block, not a changed posting block.** `extract_features` gets an optional `facts` argument (a record or `None`). With facts, the human message holds two data blocks: `<posting>` and `<company_facts>` ("Size class: 51-200 employees. Founded: 2019. Looked up on LinkedIn on 2026-10-29."), and the instructions add one sentence: the facts come from a lookup about the employer, the text from the posting, and `company_stage` comes from the posting where it states size or stage and from the facts where it does not (a first wording that called the size class evidence, not the decision, made the model answer `unknown` in two of three live eval runs). Callers pass `repository.companies.get(company_id(posting.company))`. The benchmark and the evals pass it too, so they measure what production sends. Alternative rejected: appending the facts to the posting text; the model could not tell lookup from posting, and the prompt hash in a benchmark record would not move.

**Backfill by refetching the job page.** Stored LinkedIn postings carry no company link (the cut dropped it), so `python -m jobadvaisor.data.fill_company_facts <repo> [--apply]` (next to `trim_linkedin`) fetches each posting's first URL once, takes the company link and runs the same lookup; companies already holding a record are skipped. A one-off repair, not a user-facing action, like `trim_linkedin`; new postings go through intake. Dry run lists the companies and makes no request to a company page.

## Evals

The behavior that is LLM-backed is the extractor's use of the facts.

- **Metric and data:** per-feature accuracy of the extractor benchmark (`python -m jobadvaisor.evals.extractor_benchmark`, DeepEval metric `ExtractionAccuracy`) on the user's settled labels (`extraction-labels.json`: 32 settled labels on 15 postings on 2026-10-29, of which 8 are `company_stage`; a movement of one label is 12.5 points, so the result is read as direction, not as a gate). Runs before this change exist (2026-10-29: the current extractor and `typesafe/jev-1.14.0`, the latter a decision model); the run after the backfill is compared with the current extractor's by `--compare`. The accuracy of `company_stage` should not fall and is expected to rise; `unknown` answers for it should fall. The extraction instructions change, so the benchmark's record already flags the runs as not comparable by hash; the comparison is read as before/after on the same postings, not as a regression gate.
- **CI:** the demo persona's fictional employers get company records (consistent with the stage their postings state), so the existing extraction eval (`evals/feature_extraction.py`) now sends the facts block. A new eval, `company_facts` (`evals/company_facts.py`, case in `fixtures/evals/company-facts/case.json`), extracts one hand-written posting whose text states neither size nor stage and asserts that `company_stage` follows from the record's facts; it is skipped without a model key like the other live evals, and runs with the suite on an `eval-*` tag. No real data in CI.
- The paid benchmark run happens on explicit go-ahead, after the backfill, not per task.

## Risks / Trade-offs

- [LinkedIn changes the markup or blocks guest requests] → changed markup: the parser returns no facts and the record is empty; blocked requests (429, 5xx): nothing is stored and the next posting retries; intake is unaffected either way; tests use synthetic pages, one real page layout is re-checked at implementation start.
- [The model leans on size alone ("501+ employees" is enterprise)] → the instruction names the facts as evidence and keeps the feature's phase rules; the benchmark shows it.
- [Two name variants of one employer cost two requests and two records] → accepted; merging needs a company identity the data does not have.
- [Backfill requests: about 45 job pages and up to 45 company pages] → the interval applies, the run is dry by default and resumable (existing records are skipped).
- [Stale records] → `fetched_at` is stored; aging them out is a later change.

## Migration Plan

Records are new files; existing repositories load unchanged and extract as before. Before merging, on explicit go-ahead: run the backfill on the user's data repository (commit there directly, per the data repository rules), then the benchmark; the numbers go into the PR body (tasks 6.2). Rollback: delete `companies/`; extraction falls back to no facts block.
