import type { PoolRow } from '@/api'

/** A score range over the steps -1 ("ohne Score") and 0 to 10, both ends inclusive. */
export type ScoreRange = { from: number; to: number }

/** The step "ohne Score": below every score. */
export const NO_SCORE = -1

/** The highest score. */
export const TOP_SCORE = 10

/** The full range, "ohne Score" to `TOP_SCORE`: it hides no row. */
export const FULL_RANGE: ScoreRange = { from: NO_SCORE, to: TOP_SCORE }

/** Whether `row` lies in `range`. Only a `scored` row has a score (an excluded or held row can
 * carry a stored one, but the view shows its reason instead). The step "ohne Score" selects the
 * `unscored` rows, the ones a scoring pass would still score. */
export function inRange(row: PoolRow, range: ScoreRange): boolean {
  if (range.from <= FULL_RANGE.from && range.to >= FULL_RANGE.to) return true
  if (row.state === 'scored' && row.score !== null) return row.score >= range.from && row.score <= range.to
  return row.state === 'unscored' && range.from <= NO_SCORE
}

/** The sort choices, in the order the select lists them; `rank` is the server's ranking. */
export const SORTS = [
  { id: 'rank', label: 'Rangfolge' },
  { id: 'score-desc', label: 'Score: höchster zuerst' },
  { id: 'score-asc', label: 'Score: niedrigster zuerst' },
  { id: 'rating-desc', label: 'Deine Bewertung: beste zuerst' },
  { id: 'rating-asc', label: 'Deine Bewertung: schlechteste zuerst' },
  { id: 'added-desc', label: 'Hinzugefügt: neueste zuerst' },
  { id: 'added-asc', label: 'Hinzugefügt: älteste zuerst' },
] as const

/** One of the `SORTS` ids. */
export type Sort = (typeof SORTS)[number]['id']

/** Rating order, best first: strong yes, plain yes, weak yes, weak no, plain no, strong no. */
const RATINGS = ['positive:strong', 'positive:', 'positive:weak', 'negative:weak', 'negative:', 'negative:strong']

/** The sort key of `row` for `key`, or `null` when it has no value for it: no score (only a
 * `scored` row has one) or no verdict. A rating's key is its index in `RATINGS`. */
function keyOf(row: PoolRow, key: 'score' | 'rating' | 'added'): number | null {
  if (key === 'added') return Date.parse(row.added_at)
  if (key === 'score') return row.state === 'scored' ? row.score : null
  const verdict = row.label?.verdict
  return verdict ? RATINGS.indexOf(`${verdict}:${row.label?.strength ?? ''}`) : null
}

/** `rows` (in ranking order) ordered by `sort`, as a new array. Rows without a value for the key
 * come last in both directions; ties keep their input order (the sort is stable). */
export function sortRows(rows: PoolRow[], sort: Sort): PoolRow[] {
  if (sort === 'rank') return [...rows]
  const [key, direction] = sort.split('-') as ['score' | 'rating' | 'added', 'asc' | 'desc']
  // A rating's index counts best first, so its "beste zuerst" is the ascending index order.
  const sign = (direction === 'desc') === (key !== 'rating') ? 1 : -1
  return [...rows].sort((a, b) => {
    const [x, y] = [keyOf(a, key), keyOf(b, key)]
    if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1
    return sign * (y - x)
  })
}
