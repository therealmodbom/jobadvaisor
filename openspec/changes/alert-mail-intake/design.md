# Design

## Context

See proposal.md for why. Today the intake view's inputs are `<textarea>`s (`IntakeView.tsx`), so a paste delivers only the clipboard's `text/plain` part. For a rendered mail that part holds the titles but no URL, while the `text/html` part holds every link. This was checked with a real alert mail from a mail client: 0 URLs in plain text, all 10 job links in the HTML part.

The intake pieces this change reuses:

- `add_from_url` (`intake/postings.py`) checks URL duplicates before fetching, runs the fetch ladder and the intake loop, then fills and stores through `add_submission`, which checks duplicates again under `_STORE_LOCK`.
- `posting_urls` stores the submitted URL and, when it differs after `normalize_url`, the page's final address (a redirect target or an alternative source).
- `normalize_url` (`intake/duplicates.py`) keys Bundesagentur detail URLs by their reference number. It keys other URLs by host, path and the query without tracking parameters, so a LinkedIn link on the `/comm/` tracking path does not match a stored `linkedin.com/jobs/view/<id>`. The data repository holds that stored form.
- The list import (`intake/imports.py`) runs its entries in a one-worker background thread with in-memory state. `ImportView` keeps its import's ID in `sessionStorage`, so a reload attaches to the running import.
- `POST /postings/batch` runs URLs serially inside one request.
- `ContentGuard.third_party` returns `WITHHELD` for flagged text, and the text unchanged when screening is off. `screen` raises when the classifier fails. Its other callers (`intake/loop.py`, `tools/research.py`) withhold the text then.
- In `IntakeView`, the link, text and PDF inputs render only while chosen, inside one `<form>`. `ImportView` stays mounted, hidden, outside that form. The app's views stay mounted while hidden (`App.tsx`), which is how a running list import keeps polling.

A spike on 2026-11-13 fetched job links rebuilt without their query. A LinkedIn `/jobs/view/<id>` answers the guest view through the plain fetch, with the header's title, company and place. A large employer's own job site answers through the plain fetch. The career-site platform answers 403 to the plain fetch, with or without the original query, and gives the posting through the rendered fetch, the ladder's next step. Removing the query therefore costs no posting there.

Sample mails show where the titles sit:

- LinkedIn has three anchors per job: an image, the title, and "company · place".
- The Bundesagentur has two: "N. title" and a "view job" button.
- The career-site platform has one: "title - City, CC".

## Goals / Non-Goals

**Goals:**
- No personal link parameter reaches a fetch, the data repository, a log, the model provider, the guard's classifier or the trace store.
- The finder is a plain function. A later mailbox (#58) calls it, and calls the run, unchanged.

**Non-Goals:**
- Reading the MIME structure of a mail. The paste is a body. #58 will hand the finder a mail's HTML part.
- Changing `POST /postings/batch` or the list import.

## Decisions

[ADR 0011](../../../docs/decisions/0011-alert-mails-read-by-link-rules-and-a-model-that-picks-link-numbers.md) records the finder's approach and the link cleaning, with the rejected alternatives. The decisions below say how they are built.

**Paste.** The alert-mail input is a `<textarea>` whose `onPaste` reads `clipboardData.getData('text/html')` and `getData('text/plain')`. It shows the plain text and keeps the HTML in component state.

- A new paste replaces both. Clearing the field drops both.
- Typing after a paste leaves the HTML as it is, since the pick list is where entries are dropped.
- "Stellen finden" sends `{html, text}`, where `html` is `null` when the clipboard had none.
- The finder reads `html` when it is not null, and `text` otherwise.

**Link extraction.** `intake/alert_mail.py` has one small `HTMLParser` subclass, on stdlib like `fetch._PageParser`. It turns the HTML into an ordered stream of text blocks and links (`href` and link text), and drops `script` and `style`. An image's `alt` is the link text only when the link has no text of its own. `fetch.page_links` is not reused: it keeps the first occurrence of each URL only, and the rules need every anchor of a job to pick its title.

For plain text, a URL regex yields the links. Each link's text is the nearest non-empty line before it that is not itself a URL.

Only absolute `http`/`https` links with a public host are kept. These are dropped:

- relative links and other schemes (`mailto:`, `tel:`, `javascript:`, `data:`);
- `localhost`, single-label hosts, and IP literals in loopback, private, link-local or reserved ranges (`ipaddress`).

**Rules.** A rule is a frozen dataclass: name, a match function `url → posting key | None`, the canonical URL for a key, and a title picker over that key's link texts. All rules apply to every link.

- `linkedin`: host `linkedin.com` or a subdomain. It reads four forms: `/jobs/view/<id>`, `/comm/jobs/view/<id>`, the slug-and-ID form `/jobs/view/<slug>-<id>`, and a `currentJobId=<id>` parameter on a `/jobs/` path. Canonical `https://www.linkedin.com/jobs/view/<id>`. Title: the first non-empty link text without " · ".
- `bundesagentur`: `bundesagentur.reference_number`. Canonical `https://www.arbeitsagentur.de/jobsuche/jobdetail/<ref>`. Title: the longest link text with a leading "N. " removed.
- `career_site`: any host, path `/job/<title>/<number>[-<ll>_<CC>]/`, and a query holding `refid`. The query key is the platform's signature and keeps the rule off unrelated `/job/` paths. Canonical: scheme, host and path. Title: the link text with a trailing " - <place>, <CC>" removed.

Title pickers skip image-only links. A link text that is a URL is never a title.

When any link matches, the mail is read by the rules: one entry per key, in order of first appearance, and links no rule matches are ignored (Risks). `read_by` lists the rules that matched.

**Model fallback.** It runs only when no link matches a rule.

1. *Screening off.* With no classifier configured, the model does not read the mail. The answer is `model_skipped: "screening off"`, and the view says that only known senders can be read while screening is off. This keeps #56's criterion that an instruction in a mail never reaches a model unscreened.
2. *Drop list.* Before numbering, links are dropped when their text or path names unsubscribing, settings, preferences, a saved search or job alert, a search page, a profile, the network feed, messages, notifications, premium offers, help, privacy, an imprint, or a browser or web version of the mail (German and English words; one list in the module). When no link is left, the finder answers no entries and calls neither the guard nor the model.
3. *Rendering.*
   - The stream becomes text, with each kept link written as `[link text](#N host/path)`.
   - Every URL that appears in a text block or a link text is replaced by its host and path without the query.
   - A path segment that looks opaque is replaced by `…`. Opaque here means at least 20 characters of `[A-Za-z0-9_=-]`, holding upper case, lower case and a digit, with fewer than three hyphens, so word slugs survive.
   - The text is capped at 30,000 characters, cut at the end.
4. *Screening.* The text goes to `intake.guard.screen`. A flagged result ends the finder with `held: true` and no entries. A classifier error ends it with 502 `screening failed`, and the model is not called on unscreened text.
5. *Model call.* The `intake` role model (`Intake.model`) runs once, with structured output `{postings: [{link: int, title: str}]}`. The prompt carries `DATA_RULE` for the `mail` tag and `data_block("mail", text)`. The `intake` model is used rather than a new role, since reading a mail is intake work, and `INTAKE_MODEL` already lets the user change it. `Intake.model` always exists, since `LLM_MODEL` is required.
6. *Answer.*
   - Numbers outside the table are dropped. Entries are sorted by link number, which is mail order.
   - Entries are grouped by their cleaned link. A group whose titles are all the same, ignoring case and spaces, becomes one entry. A group with different titles means the cleaned link does not tell the postings apart. Each of its entries is kept and marked `ambiguous`; it is not selectable, and the view suggests pasting that posting's text.
   - `read_by` is `["model"]`.

**Cleaning.** `clean_link(url)` returns the rule's canonical URL when a rule matches. Otherwise it keeps:

- scheme, host and path, with opaque path segments left as they are (the link is fetched as it is);
- the query parameters whose lowercased name is in `POSTING_PARAMETERS` (`id`, `jobid`, `job_id`, `job`, `jid`, `reqid`, `req_id`, `requisitionid`, `postingid`, `posting_id`, `vacancyid`, `positionid`);
- a fragment only when it is a hash route (`#/…`, `#!…`) without `=`.

A link no rule reads whose path has an opaque segment is not offered to the model (it is dropped with the drop list), since its path may itself be a token.

- The finder's entries carry cleaned links only, and `POST /alert-mails/runs` cleans every link again, so a client can never send a raw one.
- The run calls `add_from_url(…, redirect=redirect_url)`, a new keyword that `posting_urls` applies to the page's final address. `redirect_url(final)` returns the rule's canonical URL when a rule matches, or `final` when `clean_link(final) == final`, and `None` otherwise. A `None` stores no second address, so a cleaned target can never make two postings share a URL.
- Plain link intake passes no `redirect` and keeps storing the final address as today.

**Duplicate key.** `normalize_url` keys a LinkedIn job page by its ID (`linkedin:<id>`), in the four forms the `linkedin` rule reads, like the Bundesagentur reference number. It changes no stored file, and it also applies to plain link intake and the list import:

- a LinkedIn link in another form now finds the stored posting before any fetch;
- `posting_urls` no longer stores a second LinkedIn form of the same job;
- the import's "listed link" check matches across forms.

The preview marks an entry as stored through `duplicate_of(postings, urls=[link])` and answers that posting's ID and title. It also marks an entry whose host is in the policy pack's login-walled hosts (`login_wall_hosts`) as `login_walled`. That entry is not preselected, since it can only be found through the intake loop's search.

**Record for #109.** After each preview, one JSON line is appended to `alert-mails.jsonl` in the state directory (`state_path`, outside the data repository): `{at, read_by, hosts: {host: count}, entries: <count>, held, model_skipped}`. It holds no path, query, title or text. A failed write is ignored, since the record is a convenience.

**Run.** `intake/alert_runs.py` has `AlertRuns`, built like `Imports`: a one-worker executor, a lock, in-memory state, and `AlertRunBusyError` carrying the computing run's ID.

- Each entry calls `add_from_url(intake, link, redirect=redirect_url)` with the defaults of a single link, so a gone link is still looked for elsewhere.
- Errors map as in `import_entry`: `PostingNotFoundError` gives `failed` with its attempts; a `ValueError` gives `failed` with its text (`ValidationError` with its type name); anything else gives `failed` with its type name. One entry never stops the run.
- State is `{run_id, status, error, total, done, entries: [{url, title, state, posting_id?, attempts?, reason?}]}`. `state` is one of `waiting`, `running`, `stored`, `duplicate`, `failed`. `status` is one of `running`, `done`, `failed`.

An alert run and a list import may compute at the same time. Both store through `_STORE_LOCK` and the write gate, so nothing is stored twice; the cost is two browser fetches at once. Merging the two runners is left to #91 (import survives a restart), which reworks the import's state anyway.

**API.**

- `POST /alert-mails/preview`:
  - Body: JSON `{html: string | null, text: string}`, each at most 2,000,000 characters; 422 `invalid request` for more, or when both are empty.
  - 200: `{entries: [{url, title, duplicate: {posting_id, title} | null, login_walled, ambiguous}], read_by: [string], held, model_skipped: string | null, screening, truncated}`.
  - At most 100 entries are answered, the run's limit. `truncated` is true when the mail held more.
  - 502 `screening failed` when the classifier fails, and 502 `finder failed` when the model call fails. Both offer a retry.
- `POST /alert-mails/runs`:
  - Body: `{entries: [{url, title}]}`, 1 to 100 entries, each `url` an http(s) address.
  - 202: `{run_id}`.
  - 409: `{error: "alert run in progress", detail, run_id}`, so the client can attach to the computing run.
  - 422 `invalid request`.
- `GET /alert-mails/runs/{run_id}`: the state above. 404 for an unknown run, since a restart forgets runs.

**UI.**

- `IntakeView`'s `SOURCES` gains `['mail', 'Alert-Mail']`.
- A new `AlertMailView` sits beside `ImportView`, outside the intake `<form>`, mounted and hidden while another source shows. It takes `onText` and `onPdf` callbacks, which `IntakeView` passes as `switchTo('text')` and `switchTo('pdf')`.
- It holds three steps: the paste with "Stellen finden", the pick list, and the run.
- The run's ID is kept in `sessionStorage` (try/catch), as `ImportView` does, so a reload attaches to the running run. Polling runs every second, as in `ImportView`.
- Pick list:
  - one checkbox row per entry, with its title and cleaned link;
  - a stored entry shows "Schon gespeichert" with a link to the posting, and its checkbox is disabled;
  - an `ambiguous` entry is disabled, with its reason and the text option;
  - a `login_walled` entry shows "Seite mit Login-Pflicht" and is not preselected;
  - `truncated` says that only the first 100 are listed;
  - the action is "N Anzeigen hinzufügen", and "Andere Mail einfügen" starts over.
- The view's states beyond the pick list:
  - screening on or off, as in the rest of the intake view;
  - "screening off, only known senders";
  - held by the content guard;
  - nothing found;
  - 502 with a retry;
  - 409, which attaches to the running run;
  - 404 while polling ("Lauf nicht mehr bekannt", start over);
  - a run that ended `failed`.
- Run: one row per entry with its state, "x von y erledigt", failed rows with the ladder's attempts (`AttemptList`, moved to a shared component) and the text and PDF buttons, and stored rows with "Anzeige ansehen".
- Copy is German, in the view's existing tone. "Bewerten" does not appear in this view.
- The look and position come from a Design artifact on the "JobAdvAIsor Design System", agreed before the UI is built.

**Eval.**

- Behavior: the finder, both paths.
- Data: fictional alert mails under `fixtures/intake/alert-mails/`, one `<case>.html` or `<case>.txt` each, plus `<case>.json` with the expected `[{url, title}]` (or `"held": true`).
  - The fixtures are written from scratch in the layout of each sender's mail. Search terms, places, employers, IDs and hosts are invented (`example` domains for the career site). They hold no greeting, name or address of a recipient.
  - Tokens appear only as the placeholder `TOKEN`, so the cleaning is exercised.
  - A test enforces this. Query values are `TOKEN` or an invented ID from the fixture allow-list. No `@` address appears outside `example.*`. No host appears other than `linkedin.com`, `arbeitsagentur.de` and `example.*`.
- The cases:
  - LinkedIn digest and single job, with three links per job and footer links;
  - Bundesagentur numbered list;
  - career-site platform on two fictional employer hosts;
  - Bundesagentur alert as plain text with printed URLs;
  - two unknown senders for the model. One has `?jobId=` links, a session token, a tokenised URL printed in its text and in a link text, and a link with a token in its path. The other has job paths and two different postings behind one click-redirect address;
  - a mail without postings, whose links all fall to the drop list;
  - an unknown-sender mail with an instruction addressed to an AI system and a link it tries to add.
- Metric:
  - *postings found*: expected links returned over expected links;
  - *links correct*: returned links that are expected over returned links, compared exactly after cleaning;
  - a case that expects nothing and returns nothing scores 1.0 on both;
  - a case that expects `held` scores 1.0 on both when the answer is held, and 0.0 otherwise;
  - ambiguous entries count as returned.
  - Both are reported per rule and for the model, with each case's figures and the name of the guard that ran.
- Framework:
  - The two metrics are DeepEval custom metrics without an LLM judge (`BaseMetric`, as `extraction_accuracy.py` does). They are scored with DeepEval's evaluate through `load_deepeval(state_path(settings, repository.root))`, and the test uses the `deepeval` fixture of `tests/conftest.py`.
  - Case loading and the per-rule grouping stay custom, as in the extractor benchmark.
  - The eval is `alert_mail` in `evals/__main__.py`. It receives a model factory, not a model, because `_run` turns a `ModelNotConfiguredError` raised at the entry into a skip of the whole eval. The model cases build the model themselves and report `skipped` with the reason on that error, while the rule cases run anyway.
- Screening: the injection case expects `held` with a classifier configured. Without one, the model cases report `skipped` (screening off), which is what the spec asks.
- Default test run: a `pytest` test runs the rule cases and the no-postings case without DeepEval, so a rule regression fails CI.
- Cost: the paid part is three model cases, one classifier call and at most one `intake` call each. The run happens once at the change's wrap-up, on request, with its cost measured and named first.

## Risks / Trade-offs

- [A sender changes its link shape] → that mail falls to the model, `read_by` shows it, and the rule's fixture still passes. A drift shows when the finder runs on a fresh real mail, outside the repository; #109 automates that later.
- [A mail from an unknown sender that also holds one link a rule reads] → only that link's posting is listed, and `read_by` names the rule. The record's host counts show the other hosts. Accepted: alert mails come from one sender each, and the pick list shows what was found.
- [The career-site rule matches an unrelated `/job/<title>/<number>` link with a `refid` parameter] → it would only list a link that is shown in the pick list and can be deselected. The rule is checked against the fixtures of the other senders.
- [The model picks an action link the drop list does not name] → the cleaned link has no token for an action, the pick list shows every link before anything is fetched, and only public http(s) hosts are kept.
- [A job site that names the posting in a parameter outside `POSTING_PARAMETERS`] → its postings clean to one link and show as `ambiguous`, or a single one is fetched without its ID and fails or stores the wrong page (ADR 0011, Consequences). A further name is a one-line addition.
- [The opacity heuristic misses a token in a path segment, or blanks a real slug] → a missed token is fetched with the link, as the mail's own click would do, but never shown to the model. A blanked slug only shortens the model's view of that link.
- [Login-walled hosts such as Xing] → their entries are marked and not preselected. When chosen, they go through the intake loop's search like any login-walled link.
- [Two rendered fetches at once while an import also runs] → slower, not wrong.
- [A 30,000-character cap cuts a very long unknown mail] → the later postings are not found. The cap sits well above the samples' visible text.
- [The run state is lost on restart] → stated in the view (404 while polling), as for the import. A new paste marks what was stored.
