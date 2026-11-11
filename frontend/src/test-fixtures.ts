import type { Counter, Pool, PoolRow, RatingBody, Strength } from '@/api'

/** A pool row: an open, scored posting unless `extra` says otherwise. */
export const row = (posting_id: string, title: string, extra: Partial<PoolRow> = {}): PoolRow => ({
  posting_id, title, company: 'Grünwerk Solar', location_raw: 'Kiel', added_at: '2026-10-10T07:12:00+00:00',
  state: 'scored', unscreened: false, rules: [], categories: [], score: 6, score_problem: null, label: null, status: 'open',
  origin: null, exploration: false, ...extra,
})

/** A stored label; `strength` null is a plain yes or no, the way the server sends it. */
export const label = (verdict: 'positive' | 'negative' | null, chips: string[] = [],
  strength: Strength | null = null) =>
  ({ verdict, strength, chips, note: null, rated_at: '2026-10-12T08:00:00+00:00' })

/** A pool in server order: a rated positive and negative posting, scores, an exploration pick,
 * an unscored, excluded, held and unreadable-score posting, and three imports (origin set): one
 * open without preference, an applied and a done one. */
export const POOL: Pool = {
  rows: [
    row('p1', 'Data Analyst (m/w/d)', { score: 8, label: label('positive', ['great-stack']) }),
    row('p2', 'Data Engineer (m/w/d)', { score: 7, company: 'Nordblatt' }),
    row('p3', 'Datenjournalist (m/w/d)', { score: 3, exploration: true }),
    row('n1', 'Neue Stelle (m/w/d)', { state: 'unscored', score: null }),
    row('p4', 'Junior Controller (m/w/d)', { score: 2, label: label('negative', ['too-junior']) }),
    row('sales', 'Vertrieb Innendienst (m/w/d)', { state: 'excluded', score: null, rules: ['keine-vertriebsjobs'] }),
    row('held', 'Analyst (m/w/d)', { state: 'held', score: null, categories: ['instructions_for_ai'] }),
    row('broken', 'Buchhalter (m/w/d)', { state: 'unscored', score: null, score_problem: 'scores/broken.json ist nicht lesbar' }),
    row('imp1', 'Importierte Stelle (m/w/d)', { label: label(null), origin: { table: 'jobs_alt', fit: 'gut', status: 'offen' } }),
    row('app1', 'Projektleiter (m/w/d)', { score: 9, status: 'applied', label: label('positive'), origin: { table: 'jobs_alt', fit: null, status: null } }),
    row('done1', 'Berater (m/w/d)', { score: 5, status: 'done', origin: { table: 'jobs_alt', fit: null, status: null } }),
  ],
  counter: { corrections: 3, rated: 12, rate: 0.25, hint: 'fits', since: '2026-10-14T19:00:00+00:00' },
  settings: { correction_threshold: 10, correction_rate: 0.3 },
  next_pass: { count: 12, rescore: false },
  reason_chips: [{ id: 'great-stack', label: 'great stack', polarity: 'positive' },
                 { id: 'too-junior', label: 'too junior', polarity: 'negative' }],
  screening: true,
}

/** What `PUT /postings/{id}/rating` answers for a body, the way the server resolves it: the given
 * verdict, else the polarity of the first chip that has one (422 when none does), and the given
 * strength or null (422 for a strength without a given verdict). `base` is the posting's row,
 * `counter` the counter to answer with. */
export function ratingAnswer(base: PoolRow, body: RatingBody, counter: Counter = POOL.counter) {
  if (body.strength && !body.verdict) return { status: 422, body: { error: 'invalid rating', detail: 'strength needs a verdict' } }
  const polarity = body.chips.map((id) => POOL.reason_chips.find((chip) => chip.id === id)?.polarity).find(Boolean)
  const verdict = body.verdict ?? polarity
  if (!verdict) return { status: 422, body: { error: 'invalid rating', detail: 'a verdict is missing' } }
  return { body: { row: { ...base, label: { verdict, strength: body.strength ?? null, chips: body.chips, note: body.note ?? null, rated_at: '2026-10-15T08:00:00+00:00' } },
                   counter, next_pass: POOL.next_pass } }
}

/** `POOL` with `changes` applied on top. */
export const poolWith = (changes: Partial<Pool>): Pool => ({ ...POOL, ...changes })
