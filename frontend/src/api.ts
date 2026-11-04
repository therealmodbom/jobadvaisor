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

/** Calls the backend at `path`. `json` is sent as a JSON body, `form` as multipart form data.
 * Resolves the parsed answer; rejects with `ApiError` for an error status or no connection. */
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

/** One pool row (`GET /pool` `rows`), in rank order. */
export type PoolRow = {
  posting_id: string
  title: string
  company: string
  location_raw: string
  added_at: string
  state: 'scored' | 'unscored' | 'excluded' | 'held'
  rules: string[]
  categories: string[]
  score: number | null
  score_problem: string | null
  label: Label | null
  status: Status
  origin: { table: string; fit: string | null; status: string | null } | null
  exploration: boolean
}

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

/** `GET /pool`. */
export type Pool = {
  rows: PoolRow[]
  counter: Counter
  settings: PoolSettings
  next_pass: { count: number; rescore_unrated: boolean }
  reason_chips: ReasonChip[]
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
export type RatingAnswer = { row: PoolRow; counter: Counter; next_pass: Pool['next_pass'] }

/** Stores the rating of `postingId` at once. Rejects with `ApiError` (404 unknown posting, 422
 * unknown chip or no verdict to derive, 0 unreachable). */
export const putRating = (postingId: string, body: RatingBody) =>
  api<RatingAnswer>(`/postings/${encodeURIComponent(postingId)}/rating`, { method: 'PUT', json: body })

/** `GET /postings/{id}`: the posting's pool row, the stored posting, its score (null without
 * one), the compared examples that still exist and the reason chips. */
export type PostingPageData = {
  row: PoolRow
  posting: Posting
  score: { score: number; reasoning: string; example_ids: string[]; scored_at: string } | null
  examples: { posting_id: string; title: string; company: string }[]
  reason_chips: ReasonChip[]
}

/** `GET /pool/passes/{id}`: progress of a scoring pass and the postings it asks about. */
export type PassState = {
  pass_id: string
  status: 'running' | 'awaiting_answer' | 'done' | 'aborted' | 'failed'
  started_at: string | null
  error: string | null
  total: number
  done: number
  unscreened: { posting_id: string; title: string; company: string }[]
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

/** One entry of the `POST /postings/batch` answer, in the order the links were sent. A failed
 * link has `detail` (English, not shown) and, when fetching was tried, its `attempts`. */
export type BatchResult =
  | { url: string; outcome: 'stored' | 'duplicate'; posting_id: string }
  | { url: string; outcome: 'failed'; detail: string; attempts?: Attempt[] }

/** `POST /postings` answer for a stored (201) or duplicate (200) posting. */
export type IntakeAnswer = {
  posting_id: string
  posting: Posting
  duplicate: boolean
  duplicate_by: 'url' | 'text' | 'similar_text' | null
  attempts: Attempt[] | null
  screening: boolean
}
