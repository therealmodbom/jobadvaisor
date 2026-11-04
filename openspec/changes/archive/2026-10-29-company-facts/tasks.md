# Tasks

## 1. Company record in the data repository

- [x] 1.1 Add the `Company` entity (`data/models.py`: name, `size_class`, `founded`, `source`, `source_url`, `fetched_at`; patterns from design.md), the `companies/` directory in `load` as `DataRepository.companies`, `write_company`/`read_company` in `data/writer.py`, and the company ID rule; tests: valid record loads, bad year and bad size class fail naming file and constraint, absent directory loads as before
- [x] 1.2 Regenerate the published schemas (`python -m jobadvaisor.data.schemas`) so `schemas/company.schema.json` exists and `tests/test_schemas.py` passes
- [x] 1.3 Add company records for the demo persona's fictional employers and verify the fixture validates

## 2. Reading the facts

- [x] 2.1 In `intake/fetch.py` capture the LinkedIn company link (`topcard__org-name-link`) into `Page.company_url` (query dropped, host `www.linkedin.com`, path `/company/…` only); test on a synthetic guest page with and without the link
- [x] 2.2 Add `intake/company_facts.py` parsers: LinkedIn company page (`about-us__size`, `about-us__foundedOn`) and schema.org `Organization` JSON-LD (`foundingDate`, `numberOfEmployees` mapped to size classes); tests on synthetic pages: both facts, size only, none, malformed markup, a year or class that fails the record's patterns is dropped
- [x] 2.3 Add `look_up` with source order (LinkedIn, then website via the shared host heuristic moved out of `tools/research.py`), the completed-versus-incomplete rule (record without facts on a read page or 404/410, nothing on transport error, 429, 5xx) and the per-host minimum interval; tests with a fake fetcher and a fake clock for each outcome in the specs

## 3. Intake

- [x] 3.1 Call `look_up` from `add_from_url` after a new posting is stored (no call for a duplicate, an "unknown" company, an existing record, or text/PDF postings); tests: first and second posting of one company make one request, a lookup that raises leaves the stored posting unchanged and the call returns as before

## 4. Extraction

- [x] 4.1 Give `extract_features` the optional `facts` argument and the `<company_facts>` block with the added instruction sentence (`tools/extraction.py`, `tools/prompts.py`); tests: the block appears only with facts, holds only typed values, is escaped like any data block, the posting block is unchanged
- [x] 4.2 Pass the posting company's record at every caller (triage graph, agent tool, extractor benchmark, `evals/logistic.py`, `evals/feature_extraction.py`); test that the triage graph and the benchmark send the block for a company with a record
- [x] 4.3 Add the `company_facts` eval (the case from design.md → Evals, run on the demo persona, skipped like the other live evals without a key) and register it; tests with a fake model; its live run waits for the user's word with the benchmark

## 5. Backfill

- [x] 5.1 Add `python -m jobadvaisor.data.fill_company_facts <repo> [--apply]` (dry run by default; refetches each posting's first URL once, skips companies with a record, changes no posting, prints a report); tests on a temporary repository with a fake fetcher: dry run writes nothing and requests no company page, apply writes records, rerun is a no-op

## 6. Wrap-up

- [x] 6.1 Update README (workflow: company facts, the backfill command) and `AGENTS.md` current-state line; verify `ruff` and `openspec validate company-facts --strict` are clean and the full backend suite passes
- [x] 6.2 Run the backfill on the user's data repository, then the extractor benchmark and `--compare` against the 2026-10-29 run, on explicit go-ahead (paid, writes into the data repository); put `company_stage` accuracy and the share of `unknown` before and after into the PR body
- [x] 6.3 Tick the tasks, run `openspec archive company-facts --yes` on this PR's branch and check the baseline specs hold no duplicate requirement
