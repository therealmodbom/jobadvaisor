# Company facts

When you add a posting from a URL, intake looks its employer up once: the size class (such as "51-200") and the founding year. It reads the employer's LinkedIn company page first (the link comes from the LinkedIn job page) and the employer's website second, where it reads only schema.org `Organization` data. The website is asked only when LinkedIn gave no facts, so a record's facts come from one source. The facts go to `companies/<company name as slug>-<hash>.json` in the data repository, the hash keeping employers whose names slug alike apart. The schema is `schemas/company.schema.json`.

For an employer no lookup can reach, write the record yourself with `"source": "manual"` and a `source_url` that points at what you read. The extractor sees it as entered by hand.

A blocked or failed lookup never fails the intake and stores nothing, so the next posting of that company tries again. The extractor receives the stored facts as a block of its own, labelled as the result of a lookup, and only typed values reach it, no text from the company page.

For postings stored before the lookup existed, a one-off command refetches each company's first LinkedIn job page for the company link. It is a dry run unless you pass `--apply`, skips companies that already have a record and changes no posting:

```bash
env -C backend uv run python -m jobadvaisor.data.fill_company_facts <path>
env -C backend uv run python -m jobadvaisor.data.fill_company_facts <path> --apply
```

Requests to one host are at least two seconds apart. The `company_facts` eval checks that the extractor takes a posting's `company_stage` from the facts when the text names neither size nor stage.
