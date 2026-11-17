import { describe, expect, it } from 'vitest'
import { row, label } from '@/test-fixtures'
import { FULL_RANGE, inRange, type Range } from '@/lib/pool-order'

const scored = (id: string, score: number) => row(id, id, { score })
const ids = (rows: { posting_id: string }[]) => rows.map((entry) => entry.posting_id)

describe('inRange', () => {
  const rows = [
    scored('s0', 0), scored('s5', 5), scored('s6', 6), scored('s7', 7), scored('s9', 9), scored('s10', 10),
    row('unscored', 'u', { state: 'unscored', score: null }),
    row('unscored-rated', 'u', { state: 'unscored', score: null, label: label('positive') }),
    row('problem', 'u', { state: 'unscored', score: null, score_problem: 'unreadable' }),
    row('excluded', 'x', { state: 'excluded', score: 8 }),
    row('held', 'h', { state: 'held', score: 8 }),
  ]
  const keep = (range: Range) => ids(rows.filter((entry) => inRange(entry, range)))

  it('keeps every row in the full range, excluded and held included', () => {
    expect(keep(FULL_RANGE)).toEqual(ids(rows))
  })
  it('keeps scores 7 to 9 and drops 6, 10, unscored, excluded and held rows with a stored 8', () => {
    expect(keep({ from: 7, to: 9 })).toEqual(['s7', 's9'])
  })
  it('treats 0 as a score', () => {
    expect(keep({ from: 0, to: 0 })).toEqual(['s0'])
  })
  it('selects only the unscored rows for "ohne Score" to "ohne Score"', () => {
    expect(keep({ from: -1, to: -1 })).toEqual(['unscored', 'unscored-rated', 'problem'])
  })
  it('keeps unscored rows and scores up to 5 for "ohne Score" to 5', () => {
    expect(keep({ from: -1, to: 5 })).toEqual(['s0', 's5', 'unscored', 'unscored-rated', 'problem'])
  })
})
