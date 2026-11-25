/** A failed API call: HTTP `status` (0 when the server was unreachable), the API's `error` and
 * `detail`, and the whole answer `body` for routes that add fields (such as `attempts`). */
export class ApiError extends Error {
  readonly status: number
  readonly error: string
  readonly detail: string
  readonly body: Record<string, unknown>

  constructor(status: number, error: string, detail: string, body: Record<string, unknown> = {}) {
    super(`${status} ${error}: ${detail}`)
    this.status = status
    this.error = error
    this.detail = detail
    this.body = body
  }
}

/** The window event `api` fires after a write the backend accepted (any method but GET), so the
 * backup status can show the new pending change without waiting for its next poll. */
export const WRITE_DONE = 'jobadvaisor:write-done'

/** Calls the backend at `path`. `json` is sent as a JSON body, `form` as multipart form data.
 * Resolves the parsed answer; rejects with `ApiError` for an error status or no connection.
 * A successful call with a method other than GET, except to `/backup` itself, fires
 * `WRITE_DONE` on the window. */
export async function api<T>(path: string, { method = 'GET', json, form }: {
  method?: string
  json?: unknown
  form?: FormData
} = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      method,
      headers: json === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: json === undefined ? form : JSON.stringify(json),
    })
  } catch (error) {
    throw new ApiError(0, 'unreachable', String(error))
  }
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new ApiError(response.status, body.error ?? 'request failed', body.detail ?? '', body)
  }
  if (method !== 'GET' && !path.startsWith('/backup')) window.dispatchEvent(new Event(WRITE_DONE))
  return body as T
}

/** The content guard's result on a stored posting. */
export type Guard = {
  flagged: boolean
  categories: string[]
  checked_by: string
  checked_at: string
  released_at?: string
}

/** A stored posting as the API returns it (the fields the UI reads). */
export type Posting = {
  title: string
  company: string
  location_raw: string
  source_type: 'url' | 'text' | 'pdf'
  urls: string[]
  text?: string
  guard?: Guard
  availability?: Availability | null
}

/** One fetch-ladder or intake-loop step tried on a URL. */
export type Attempt = { step: string; url: string; outcome: string }

/** A stored rating as the pool carries it; `verdict` null marks an import that is no preference.
 * `strength` null (or absent) is a plain yes or no. */
export type Label = {
  verdict: 'positive' | 'negative' | null
  strength?: Strength | null
  chips: string[]
  note: string | null
  rated_at: string
}

/** A reason chip of the policy pack; no polarity fits either verdict. */
export type ReasonChip = { id: string; label: string; polarity: 'positive' | 'negative' | null }

/** The application status of a posting. */
export type Status = 'open' | 'applied' | 'done'

/** Whether a posting is still open for applications: a check or the user set `state` at `set_at`
 * (ISO timestamp). `unknown` is what a check stores when it could not tell. A pool row carries
 * `null` and a posting no value while the posting was never checked. */
export type Availability = {
  state: 'available' | 'closed' | 'unknown'
  set_at: string
  set_by: 'check' | 'user'
}

/** The `availability` value of `PATCH /postings/{id}`: a hand setting, which the next check
 * replaces in turn. */
export type AvailabilityChoice = 'available' | 'closed'

/** One pool row (`GET /pool` `rows`), in rank order. */
export type PoolRow = {
  posting_id: string
  title: string
  company: string
  location_raw: string
  added_at: string
  state: 'scored' | 'unscored' | 'excluded' | 'held'
  /** The content guard never checked the posting (it carries no guard result). */
  unscreened: boolean
  rules: string[]
  categories: string[]
  score: number | null
  score_problem: string | null
  label: Label | null
  status: Status
  origin: { table: string; fit: string | null; status: string | null } | null
  exploration: boolean
  availability: Availability | null
}

/** The two scoring passes: `unscored` scores the postings without a score, `all` every scorable posting. */
export type PassVariant = 'unscored' | 'all'

/** The pool's `next_pass` figures: how many postings each pass variant would score, with
 * excluded and held postings left out. `unscored` counts the postings without a score, `all`
 * every scorable one; `default` is the variant the counter hint recommends. */
export type NextPass = { default: PassVariant; unscored: number; all: number }

/** The correction counter of `GET /pool`; `rate` is null below ten ratings. */
export type Counter = {
  corrections: number
  rated: number
  rate: number | null
  hint: 'rescore' | 'fits'
  since: string | null
}

/** The hint thresholds (`correction_rate` in 0..1). */
export type PoolSettings = { correction_threshold: number; correction_rate: number }

/** `GET /pool`; `screening` is true when a content-guard classifier is configured. `next_check`
 * says how many postings an availability check would cover. */
export type Pool = {
  rows: PoolRow[]
  counter: Counter
  settings: PoolSettings
  next_pass: NextPass
  next_check: { total: number }
  reason_chips: ReasonChip[]
  screening: boolean
}

/** A verdict the user can give. */
export type Verdict = 'positive' | 'negative'

/** How firmly the user holds a verdict; with the verdict it makes the four rating levels. */
export type Strength = 'weak' | 'strong'

/** `PUT /postings/{id}/rating` body. `verdict` is sent only when the user set one; without it the
 * server takes the polarity of the first chip that has one (422 when none does). `strength` goes
 * only with a verdict (422 otherwise). The label is replaced as a whole, so `strength`, `chips`
 * and `note` always carry the full current state. */
export type RatingBody = { verdict?: Verdict; strength?: Strength; chips: string[]; note?: string | null }

/** The answer of a rating: the posting's pool row (with the stored label) and the counter and
 * next-pass figures as `GET /pool` has them. */
export type RatingAnswer = { row: PoolRow; counter: Counter; next_pass: NextPass }

/** Stores the rating of `postingId` at once. Rejects with `ApiError` (404 unknown posting, 422
 * unknown chip or no verdict to derive, 0 unreachable). */
export const putRating = (postingId: string, body: RatingBody) =>
  api<RatingAnswer>(`/postings/${encodeURIComponent(postingId)}/rating`, { method: 'PUT', json: body })

/** Deletes a posting for good (`DELETE /postings/{id}`, 204 without a body). Rejects with
 * `ApiError`: 404 unknown posting (already gone); 409 with `error` `scoring in progress` or
 * `check in progress` while a pass, a single score or an availability check runs; 500 or 0
 * (unreachable) otherwise. */
export const deletePosting = (postingId: string) =>
  api<void>(`/postings/${encodeURIComponent(postingId)}`, { method: 'DELETE' })

/** `GET /postings/{id}`: the posting's pool row, the stored posting, its score (null without
 * one), the compared examples that still exist, the reason chips and `screening` (a content-guard
 * classifier is configured). */
export type PostingPageData = {
  row: PoolRow
  posting: Posting
  score: { score: number; reasoning: string; example_ids: string[]; scored_at: string } | null
  examples: { posting_id: string; title: string; company: string }[]
  /** A check can read one of the posting's links (false for pasted text, a PDF, or only
   * login-walled or non-public links). */
  checkable: boolean
  reason_chips: ReasonChip[]
  screening: boolean
  /** Why a delete would be refused as the page loaded: a pass or single score computes
   * (`scoring`), an availability check runs (`check`), or neither (`null`). */
  delete_blocked: 'scoring' | 'check' | null
}

/** The answer of a single score: the posting page as `GET /postings/{id}` has it, plus the
 * counter and next-pass figures as `GET /pool` has them. */
export type ScoreAnswer = PostingPageData & { counter: Counter; next_pass: NextPass }

/** Scores one posting now (`POST /postings/{id}/score`, synchronous: it answers once the judge
 * has). Rejects with `ApiError`: 404 unknown posting; 409 with `error` `scoring in progress`,
 * `excluded`, `held` or `unscreened`; 502 `scoring failed`; 500 or 0 (unreachable) otherwise. */
export const postScore = (postingId: string) =>
  api<ScoreAnswer>(`/postings/${encodeURIComponent(postingId)}/score`, { method: 'POST' })

/** Where a running pass stands: its `phase` and, from the start of scoring on, the count as
 * `score: {done, total}` (`null` while it checks). `done` counts every posting scored or failed;
 * `total` shrinks when a posting drops out of the pass (flagged while a question waited). */
export type PassProgress = {
  phase: 'checking' | 'scoring' | 'storing'
  score: { done: number; total: number } | null
}

/** `GET /pool/passes/{id}`: a scoring pass and the postings it asks about. `progress` is `null`
 * until the first report; `cancel_requested` is true while it runs on after a cancel; `scored`
 * counts the scored results (what a cancelled, ended pass stored). */
export type PassState = {
  pass_id: string
  status: 'running' | 'awaiting_answer' | 'done' | 'aborted' | 'cancelled' | 'failed'
  started_at: string | null
  error: string | null
  progress: PassProgress | null
  cancel_requested: boolean
  scored: number
  unscreened: { posting_id: string; title: string; company: string }[]
}

/** `GET /availability/checks/{id}`: an availability check. `done` counts the postings handled and
 * `total` those the check covers. `cancel_requested` is true from a cancel on, also on a check that
 * then ends `done` because the cancel came with its last posting, so the view follows `status`.
 * `counts` tallies what was stored (a posting the user set meanwhile is in none; a closed posting
 * the check could not reach counts `unknown` and stays closed); `still_closed` is how many of
 * `counts.closed` were closed before the check; `closed` lists only the postings the check newly
 * closed. `error` is a code, never shown. */
export type CheckState = {
  check_id: string
  status: 'running' | 'done' | 'cancelled' | 'failed'
  error: string | null
  total: number
  done: number
  cancel_requested: boolean
  counts: { available: number; closed: number; unknown: number }
  still_closed: number
  closed: { posting_id: string; title: string; company: string }[]
}

/** A stored posting whose application `status` differs from what the import list says
 * (`list_status`); the app never overwrote it. */
export type ImportConflict = {
  posting_id: string
  title: string
  company: string
  status: Status
  list_status: Status
}

/** What a list's status value stands for in the app; `skip` leaves the entry out. */
export type ImportChoice = Status | 'skip'

/** The confirmed meaning of a list's columns (`POST /imports` form field `mapping`, as JSON):
 * the columns holding the status and the user's own assessment (null: none) and `values`, each
 * status value of the status column as the list writes it → its `ImportChoice`. */
export type ImportMapping = {
  status_column: string | null
  assessment_column: string | null
  values: Record<string, ImportChoice>
}

/** `POST /imports/preview`: the `tables` with a link column (`entries` rows each), the distinct
 * `values` of every other column that has at most 30 (column name → values, case-sensitive) and
 * the `mapping` stored by the last import, or null. */
export type ImportPreview = {
  tables: { name: string; columns: string[]; entries: number }[]
  values: Record<string, string[]>
  mapping: ImportMapping | null
}

/** One entry of a finished import that is not in the app: its `row` (cells without the link,
 * joined by " · "), its `url` (null without one), what happened and the English `reason`. */
export type NotImported = {
  row: string
  url: string | null
  outcome: 'skipped_status' | 'skipped_gone' | 'failed'
  reason: string
}

/** `GET /imports/{id}`: progress of a list import and, at the end, the report. Besides the counts
 * it lists every entry `not_imported` and names the `conflicts` (title and company, no URL), in
 * list order, already settled ones left out, and the `tables_left_out` (name, number of entries)
 * that lacked the mapping's status column. `error` is a code, never shown. */
export type ImportState = {
  import_id: string
  status: 'running' | 'done' | 'failed'
  error: string | null
  total: number
  done: number
  counts: { imported: number; duplicate: number; skipped_status: number; skipped_gone: number; failed: number }
  not_imported: NotImported[]
  conflicts: ImportConflict[]
  tables_left_out: { name: string; entries: number }[]
}

/** `POST /alert-mails/preview` body: the pasted mail's `html` part (null when the clipboard had
 * none) and its plain `text`. */
export type AlertMailBody = { html: string | null; text: string }

/** One posting the finder found in a mail, links already cleaned. `duplicate` names the stored
 * posting the link matches, `login_walled` marks a host the app never fetches, and `ambiguous`
 * a link several different postings share. `offered_in` (mailbox pick list only) names the mail
 * of the check that offers the same link first; this copy cannot be picked. */
export type AlertEntry = {
  url: string
  title: string
  duplicate: { posting_id: string; title: string } | null
  login_walled: boolean
  ambiguous: boolean
  offered_in?: { key: string; sender: string; subject: string }
}

/** `POST /alert-mails/preview`: the postings found (at most 100, `truncated` when there were more),
 * the finder that read the mail (`read_by`: rule names or `model`), the hosts of links no rule
 * read, `held` (the content guard held the mail), `model_skipped` (a reason when the model could
 * not run, e.g. `screening off`) and `screening` (a classifier is configured). */
export type AlertPreview = {
  entries: AlertEntry[]
  read_by: string[]
  unread_hosts: { host: string; links: number }[]
  held: boolean
  model_skipped: string | null
  screening: boolean
  truncated: boolean
}

/** One entry of an alert run: `state` is where it is; a stored or duplicate entry has its
 * `posting_id`, a duplicate its `duplicate_by`, a closed one (gone, and no other source holds the
 * posting) its `attempts`, a failed one its `attempts` or an English `reason` (not shown).
 * A failed entry is `unclear` when its closed answer was disputed by refused requests. An entry
 * whose link an earlier entry already put through intake carries that entry's outcome and
 * `same_as`, its index: the link was fetched once. */
export type AlertRunEntry = {
  url: string
  title: string
  state: 'waiting' | 'running' | 'stored' | 'duplicate' | 'closed' | 'failed'
  posting_id?: string
  duplicate_by?: 'url' | 'text' | 'similar_text'
  attempts?: Attempt[]
  reason?: string
  unclear?: boolean
  same_as?: number
}

/** `GET /alert-mails/runs/{id}`: progress of an alert run. `error` is a code, never shown. */
export type AlertRunState = {
  run_id: string
  status: 'running' | 'done' | 'failed'
  error: string | null
  total: number
  done: number
  entries: AlertRunEntry[]
}

/** One entry of the `POST /postings/batch` answer, in the order the links were sent. A failed
 * link has `detail` (English, not shown) and, when fetching was tried, its `attempts`. A closed
 * link (gone, and no other source holds the posting) has them too. */
export type BatchResult =
  | { url: string; outcome: 'stored' | 'duplicate'; posting_id: string }
  | { url: string; outcome: 'closed' | 'failed'; detail: string; attempts?: Attempt[] }

/** `POST /postings` answer for a stored (201) or duplicate (200) posting. */
export type IntakeAnswer = {
  posting_id: string
  posting: Posting
  duplicate: boolean
  duplicate_by: 'url' | 'text' | 'similar_text' | null
  attempts: Attempt[] | null
  screening: boolean
}

/** The folder choice of the mailbox: every folder but the system folders, or exactly `names`. */
export type MailboxFolders = { all: true; names?: undefined } | { names: string[]; all?: undefined }

/** `GET /mailbox` and the answer of `PUT /mailbox`: the account without its password. `password`
 * says whether one is `stored`, `missing` or `unreadable` (the key cannot open it, or there is
 * none); `key_configured` is false when no usable key for the password exists. `since` is the
 * start date (null before the first check), `last_check_at` the end of the last finished check.
 * `check_id` names the running check, else the one whose pick list is not finished, else null.
 * An unconfigured mailbox has empty `host` and `user`, port 993, all folders and 200 mails. */
export type MailboxAccount = {
  configured: boolean
  host: string
  port: number
  user: string
  folders: MailboxFolders
  max_mails: number
  since: string | null
  last_check_at: string | null
  password: 'stored' | 'missing' | 'unreadable'
  key_configured: boolean
  check_id: string | null
}

/** `PUT /mailbox` body. An absent or empty `password` keeps the stored one (unless host, port or
 * user changed, which forgets it); an absent `folders` or `max_mails` keeps the stored value. */
export type MailboxBody = {
  host: string
  port: number
  user: string
  password?: string
  folders?: MailboxFolders
  max_mails?: number
}

/** One folder of `POST /mailbox/folders`; a `system` folder (trash, junk, sent, drafts, all mail,
 * flagged, important) is left out of „Alle Ordner“. */
export type MailboxFolder = { name: string; system: boolean }

/** What the finder found in one mailbox mail (the shape of `AlertPreview` without `screening`). */
export type MailboxPreview = Omit<AlertPreview, 'screening'>

/** The headers of a mail a check reports, for display only: its `folder`, the `sender` and
 * `subject` (blank when missing) and its `date` (ISO). */
export type MailboxMailHead = { folder: string; sender: string; subject: string; date: string }

/** A mail of a check's pick list. `key` is its position in the check, URL-safe. `oversized` is a
 * mail too large to read unasked: its `preview` stays null until `POST …/mails/{key}/read`
 * answers it. `reading` is true while that read runs (maybe in another tab); `read_failed`
 * (`screening failed` or `finder failed`) is left by a failed read, which may be retried. */
export type MailboxMail = MailboxMailHead & {
  key: string
  oversized: boolean
  reading: boolean
  read_failed: string | null
  preview: MailboxPreview | null
}

/** `GET /mailbox/checks/{id}`. `status` is `running`, `done`, `failed` or `finished` (the pick
 * list was finished, replaced or dropped by an account change). `reason` names a failed check's
 * cause (`unreachable`, `certificate`, `login`, `folder`, `protocol`, `no key`, `no password`,
 * `password unreadable`); `error` is the exception type of a crashed worker (never shown).
 * `interrupted` is the reason a `done` check lost its connection after reading some mails.
 * `total` mails are to be read and `read` are processed, `remaining` unhandled mails wait for the
 * next check. `mails` is the pick list; `failed` (with `reason` `screening failed` or `finder
 * failed`), `held` and `not_screened` are reports; `missing_folders` names chosen folders the
 * server no longer has. */
export type MailboxCheckState = {
  check_id: string
  status: 'running' | 'done' | 'failed' | 'finished'
  reason: string | null
  error: string | null
  interrupted: string | null
  cancel_requested: boolean
  cancelled: boolean
  total: number
  read: number
  remaining: number
  mails: MailboxMail[]
  failed: (MailboxMailHead & { reason: string })[]
  held: MailboxMailHead[]
  not_screened: MailboxMailHead[]
  missing_folders: string[]
}
