import type { PoolRow } from '@/api'

/** A score range over the steps -1 ("ohne Score") and 0 to 10, both ends inclusive. */
export type Range = { from: number; to: number }

/** The step "ohne Score": below every score. */
export const NO_SCORE = -1

/** The full range, "ohne Score" to 10: it hides no row. */
export const FULL_RANGE: Range = { from: NO_SCORE, to: 10 }

/** Whether `row` lies in `range`. Only a `scored` row has a score (an excluded or held row can
 * carry a stored one, but the view shows its reason instead). The step "ohne Score" selects the
 * `unscored` rows, the ones a scoring pass would still score. */
export function inRange(row: PoolRow, range: Range): boolean {
  if (range.from <= NO_SCORE && range.to >= 10) return true
  if (row.state === 'scored' && row.score !== null) return row.score >= range.from && row.score <= range.to
  return row.state === 'unscored' && range.from <= NO_SCORE
}
