# Tasks

TDD per task: a failing test first, then the code. Fixtures are fictional and written from scratch (design.md → Eval): invented employers, search terms, places, IDs and `example` hosts, no recipient greeting, name or address, and the placeholder `TOKEN` for tokens. Nothing from a real mail goes into the repository. Commands from `backend/`: `uv run ruff check`, `uv run pytest`. From `frontend/`: `npm run lint`, `npm test`, `npm run build`.

## 1. Fixtures

- [ ] 1.1 Write the fictional alert mails under `fixtures/intake/alert-mails/`, each `<case>.html` or `<case>.txt` with `<case>.json` (expected `[{url, title}]` after cleaning, or `"held": true`). The cases are listed in design.md → Eval. Verify with a test that:
  - every case loads and has its `.json`;
  - every query value is `TOKEN` or an ID from the fixture allow-list;
  - no `@` address appears outside `example.*`;
  - no host appears other than `linkedin.com`, `arbeitsagentur.de` and `example.*`.

## 2. Finder (`intake/alert_mail.py`)

- [ ] 2.1 Link stream from HTML and from plain text:
  - HTML gives text blocks and links, with an image's `alt` only for a link without text, and no `script` or `style`;
  - plain text gives URLs, each with the nearest non-empty line before it that is not a URL as its text;
  - `html` wins when it is not null;
  - only absolute http(s) links on public hosts are kept.

  Verify with tests on the LinkedIn fixture (three links per job, in order) and the plain-text fixture, and with links to `mailto:`, `javascript:`, a relative path, `localhost`, `192.168.1.10`, `10.0.0.1`, `[::1]` and a single-label host, none of them kept.
- [ ] 2.2 `clean_link`, `strip_query` and `navigation_allowed`: `clean_link` gives the rule's canonical URL, or `strip_query` (the allow-listed query parameters plus a hash route without `=`). `navigation_allowed` holds when `strip_query` leaves the address unchanged, for rule and other addresses alike. Verify with tests for:
  - a LinkedIn `/comm/` link with `otpToken`;
  - a Bundesagentur link with search parameters;
  - a career-site link with `refid` and `eid`;
  - an unknown link with `jobId`, `sessionToken` and `utm_source`;
  - a `#/job/1` route and a `#access_token=…` fragment;
  - idempotence (cleaning a cleaned link changes nothing);
  - `navigation_allowed` on a clean address, on a tokenised address, on the same path with a trailing slash, on a LinkedIn `/jobs/view/<id>/` address (allowed) and on the same address with `otpToken` (refused).
- [ ] 2.3 The three rules with their title pickers (image-only links and URL texts skipped), and the rule path of `find_postings`: one entry per key, in mail order, with `read_by`, at most 100 entries with `truncated`. Verify with tests on the rule fixtures:
  - the expected entries and titles for each, and the four LinkedIn forms;
  - footer, unsubscribe and search links not returned;
  - an unrelated `/job/<title>/<number>` link without `refid` not read by `career_site`;
  - a 120-job fixture built in the test giving 100 entries and `truncated`;
  - no model or classifier call (fakes that fail when called).
- [ ] 2.4 Model fallback (design.md → Model fallback, steps 1 to 6). Verify with tests using a fake model and a fake classifier:
  - screening off gives `model_skipped: "screening off"` and calls no model;
  - the no-postings fixture gives no entries and calls neither classifier nor model;
  - the model input holds no `TOKEN` and no `?`, also for the URL printed in the text and in a link's text, and the token in a path is masked;
  - an answer with an unknown number or a written-out URL yields no entry for it;
  - entries come in link-number order;
  - two different titles behind one cleaned click-redirect address give two `ambiguous` entries, and one title behind two links gives one entry;
  - a flagged mail is `held` and calls no model;
  - a raising classifier gives the `screening failed` error and calls no model.
- [ ] 2.5 Duplicate and login-wall marks, and the record:
  - each entry gets `duplicate` from `duplicate_of(postings, urls=[link])` and `login_walled` from the policy pack's hosts;
  - each preview appends `{at, read_by, hosts, entries, held, model_skipped}` to `alert-mails.jsonl` in the state directory, ignoring a failed write.

  Verify with tests that a stored posting is named, that a `xing.com` link is `login_walled`, and that the record holds no path, query or title.

## 3. Duplicates and redirect guard

- [ ] 3.1 `normalize_url` keys LinkedIn job pages by ID in the four forms. Verify with `test_intake_duplicates.py` tests for each form against a stored `https://www.linkedin.com/jobs/view/<id>`, and that a LinkedIn company page keeps its old key. Add a regression test that `posting_urls` stores one URL when the final address is another LinkedIn form of the same job.
- [ ] 3.2 `guarded_link` in `intake/fetch.py`: while it names the URL a fetch starts at, `download_plain` (httpx `request` event hook) and `download_rendered` (`page.route` on main-frame navigations) check every redirect hop with `navigation_allowed` before requesting it, and raise `FetchError("redirect with personal parameters")` on a failing hop. Verify with:
  - an httpx `MockTransport` test: a 302 to a tokenised address raises, and the transport never receives that request; a 301 to the same path with a trailing slash is followed;
  - a rendered test against a local server (the eval's `serve_pages` pattern): a 302 to a tokenised local address raises, and the server's log shows the target was never requested;
  - a test that a fetch of another URL while the guard is set, and any fetch without the guard, follows redirects as today.

## 4. Background run (`intake/alert_runs.py`)

- [ ] 4.1 `AlertRuns` (`start`, `read`, `AlertRunBusyError` with the computing run's ID), built like `Imports`: per-entry state `waiting → running → stored | duplicate | failed`, with attempts or a reason, `guarded_link` set around each entry, and one entry's error never stops the run. Verify with tests using fake fetchers:
  - the guard holds the entry's link while it runs and is cleared after;
  - three entries where the second fails;
  - an entry stored meanwhile reported as a duplicate;
  - a second start refused while the first computes (a test holding the first entry), naming the first run's ID;
  - a crash of the loop reported as `status: failed`.

## 5. API

- [ ] 5.1 `POST /alert-mails/preview`, `POST /alert-mails/runs` and `GET /alert-mails/runs/{run_id}` in `api/app.py`, with the bodies and errors from design.md, and the run's links cleaned again on start. Verify with `test_api.py` tests for:
  - a preview of a rule fixture, with a stored posting marked;
  - `held` with a flagging classifier, and `model_skipped` without a classifier;
  - 502 `screening failed` from a raising classifier, and 502 `finder failed` from a failing model;
  - 422 for more than 2,000,000 characters and for empty input;
  - 202, then the polled state up to `done`;
  - 409 `alert run in progress` with `run_id`;
  - 404 for an unknown run;
  - a raw link with a token sent to `/runs` arrives cleaned.

## 6. Design artifact session (gate for the UI)

- [ ] 6.1 Design the alert-mail source in a Design artifact on the "JobAdvAIsor Design System", before group 7 starts:
  - the source button;
  - the paste field with its hint and "Stellen finden", the finding state, and the screening line;
  - the pick list with new, stored, login-walled, not-addable and deselected rows, and the truncation note;
  - the states "no posting found", "screening off, only known senders", "held by the content guard", "reading failed" with a retry, and "run no longer known";
  - the run with waiting, running, stored, duplicate and failed rows, the done count, and a run that ended `failed`;
  - the narrow phone width.

  Verify by the artifact being approved. Group 7 starts only after this.

## 7. Frontend

- [ ] 7.1 API types in `api.ts` and the paste handling: `onPaste` keeps `text/html` and shows `text/plain`, a new paste replaces both, and clearing drops both. Verify with Vitest tests that dispatch a paste with both flavors, with plain text only, and a second paste.
- [ ] 7.2 `AlertMailView` as designed in 6.1:
  - the preview call with its states (found, nothing found, screening off, held, 502 with retry and the mail kept);
  - the pick list (new preselected; stored marked, linked and disabled; login-walled not preselected; not-addable disabled with the text option; the count in the action; the truncation note);
  - the run, polled every second, with per-row states, attempts and the text and PDF buttons;
  - the run's ID in `sessionStorage`, attaching after a reload, attaching on 409 to the named run, and "run no longer known" on 404;
  - "Andere Mail einfügen".

  Move `AttemptList` to a shared component. Verify with component tests for each state, and with tests that switching the source away and back keeps a run polling, and that a remount with a stored run ID attaches to the run.
- [ ] 7.3 `IntakeView` gains the source "Alert-Mail", and mounts `AlertMailView` beside `ImportView`, outside the form, hidden while another source shows, with `switchTo('text')` and `switchTo('pdf')` as its callbacks. Verify with the existing `IntakeView` tests plus one for the new source and one for the text button switching the source.

## 8. Eval

- [ ] 8.1 `evals/alert_mail.py`:
  - *postings found* and *links correct* as DeepEval custom metrics without a judge, loaded through `load_deepeval(state_path(…))`;
  - the empty-case and `held` scoring from design.md;
  - figures per rule and for the model, with each case's figures and the guard's name;
  - a model factory, so the model cases report `skipped` with the reason when no `intake` model or no classifier is configured, while the rule cases run;
  - registered as `alert_mail` in `evals/__main__.py`.

  Verify with `test_eval_alert_mail.py` using the `deepeval` fixture and a fake model: rule cases at 1.0 for both metrics, the no-postings case at 1.0, the report's shape, and the skipped model cases.
- [ ] 8.2 A default-run `pytest` test runs the rule cases and the no-postings case of the eval without DeepEval. Verify that it is collected by `uv run pytest` and fails when a fixture's expected title is changed.

## 9. Documentation and issues

- [ ] 9.1 README:
  - the intake section names the alert mail as a fourth input, with the paste, the pick list, the background run, and that unknown senders need screening on;
  - the eval section gains `alert_mail`.

  Verify by reading it against the web-ui delta.
- [ ] 9.2 `AGENTS.md` "Current state": add this change and drop the oldest entry. Verify that it lists two changes.
- [ ] 9.3 Update #56's open question on LinkedIn: LinkedIn serves a guest view that the fetch cuts to the posting, and only `xing.com` is login-walled by default. Verify by reading the issue.
- [ ] 9.4 Run `/opsx:sync` after the last delta edit, and `openspec validate alert-mail-intake --strict`. Verify that both pass and the baseline specs in the diff show the target text.

## 10. Before the PR leaves draft

- [ ] 10.1 Full suite: backend `uv run ruff check`, `uv run pytest`, `uv run pytest -m e2e`; frontend `npm run lint`, `npm test`, `npm run build`. Add one e2e walkthrough first: paste a rule fixture's HTML (a synthetic paste event carrying `text/html`), see the pick list with one stored entry marked, add the rest with fake fetchers, and see them stored. Verify that all pass.
- [ ] 10.2 Browser click test at desktop and phone width on the demo persona, with a pasted fictional mail, including one failing entry. Verify by screenshots in the PR, and name what the test cannot show: a real mail client's clipboard and real alert senders.
- [ ] 10.3 Paid eval run of `alert_mail` (model cases, with the configured classifier), on request, with its cost measured and named first. Verify that the report is quoted in the PR.
- [ ] 10.4 Review:
  - a fresh review agent without history checks the diff against the specs and tasks;
  - `/code-review high` runs on the diff;
  - real findings from both are fixed in the same turn.

  Then `gh pr ready`, and rewrite the description for the implementation: `Closes #56`, `Closes #57`, `Refs #2`. Verify that the PR is ready and the follow-up monitor runs.
