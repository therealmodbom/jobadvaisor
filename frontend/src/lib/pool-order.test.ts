import { describe, expect, it } from 'vitest'
import { row, label } from '@/test-fixtures'
import { FULL_RANGE, inRange, sortRows, type ScoreRange } from '@/lib/pool-order'

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
  const keep = (range: ScoreRange) => ids(rows.filter((entry) => inRange(entry, range)))

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

describe('sortRows', () => {
  const ranked = [
    row('a', 'a', { score: 5, added_at: '2026-10-03T00:00:00+00:00', label: label('negative', [], 'weak') }),
    row('b', 'b', { state: 'unscored', score: null, added_at: '2026-10-01T00:00:00+00:00' }),
    row('c', 'c', { score: 9, added_at: '2026-10-02T00:00:00+00:00', label: label('positive') }),
    row('d', 'd', { score: 5, added_at: '2026-10-05T00:00:00+00:00', label: label('positive', [], 'strong') }),
    row('e', 'e', { state: 'excluded', score: 8, added_at: '2026-10-04T00:00:00+00:00', label: label(null) }),
    row('f', 'f', { score: 1, added_at: '2026-10-06T00:00:00+00:00', label: label('positive', [], 'weak') }),
    row('g', 'g', { score: 2, added_at: '2026-10-07T00:00:00+00:00', label: label('negative') }),
    row('h', 'h', { score: 3, added_at: '2026-10-08T00:00:00+00:00', label: label('negative', [], 'strong') }),
  ]

  it('returns the ranking unchanged, as a copy', () => {
    const result = sortRows(ranked, 'rank')
    expect(ids(result)).toEqual(ids(ranked))
    expect(result).not.toBe(ranked)
  })
  it('sorts by score, nulls and excluded last both ways, ties in ranking order', () => {
    expect(ids(sortRows(ranked, 'score-desc'))).toEqual(['c', 'a', 'd', 'h', 'g', 'f', 'b', 'e'])
    expect(ids(sortRows(ranked, 'score-asc'))).toEqual(['f', 'g', 'h', 'a', 'd', 'c', 'b', 'e'])
  })
  it('sorts by rating: strong yes, yes, weak yes, weak no, no, strong no; unrated last both ways', () => {
    expect(ids(sortRows(ranked, 'rating-desc'))).toEqual(['d', 'c', 'f', 'a', 'g', 'h', 'b', 'e'])
    expect(ids(sortRows(ranked, 'rating-asc'))).toEqual(['h', 'g', 'a', 'f', 'c', 'd', 'b', 'e'])
  })
  it('sorts by added date, both ways', () => {
    expect(ids(sortRows(ranked, 'added-desc'))).toEqual(['h', 'g', 'f', 'd', 'e', 'a', 'c', 'b'])
    expect(ids(sortRows(ranked, 'added-asc'))).toEqual(['b', 'c', 'a', 'e', 'd', 'f', 'g', 'h'])
  })
  it('does not change its input', () => {
    const before = ids(ranked)
    sortRows(ranked, 'score-desc')
    expect(ids(ranked)).toEqual(before)
  })
})
