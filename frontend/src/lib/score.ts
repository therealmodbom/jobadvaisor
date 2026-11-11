import { useCallback, useRef, useState } from 'react'
import { ApiError, postScore, type ScoreAnswer } from '@/api'

/** The state of one posting's score click: `computing` while the request runs, `problem` after a
 * failure, else null. `busy` (another score or a pass holds the slot) and `failed` (the judge, the
 * index or the classifier failed, the server was unreachable, or a proxy answered without the API's
 * body) may pass, so the button offers a retry label; `broken` (the API's own 500 `internal error`,
 * such as a failed store) gets its own message and the button keeps its normal label: a click
 * scores again, which is the way to retry the spec asks for, but nothing promises the second
 * attempt will pass. */
export type ScoreCall = { computing: boolean; problem: 'busy' | 'failed' | 'broken' | null }

const IDLE: ScoreCall = { computing: false, problem: null }

/** The `error` codes of a 409 that no retry changes: the posting is excluded, held or never checked. */
const REFUSED = ['excluded', 'held', 'unscreened']

/** Scoring single postings on demand (`POST /postings/{id}/score`) for the posting page and the
 * pool rows. `run(postingId)` sends the click: a second click on a posting still computing sends
 * nothing; `call(postingId)` is that posting's `ScoreCall`; `clearBusy()` drops the `busy` problems. `onAnswer` gets the 200 answer. A
 * refusal no retry can change (409 `excluded`, `held` or `unscreened`, or 404) calls `onRefused`
 * so the view reloads and shows the posting as it is now; every other failure sets a `problem`
 * (see `ScoreCall`). */
export function useScore(onAnswer: (answer: ScoreAnswer) => void, onRefused: () => void) {
  const [calls, setCalls] = useState<Record<string, ScoreCall>>({})
  const sending = useRef(new Set<string>())
  const set = (postingId: string, call: ScoreCall) => setCalls((current) => ({ ...current, [postingId]: call }))

  async function run(postingId: string) {
    if (sending.current.has(postingId)) return
    sending.current.add(postingId)
    set(postingId, { computing: true, problem: null })
    try {
      const answer = await postScore(postingId)
      set(postingId, IDLE)
      onAnswer(answer)
    } catch (error) {
      const code = error instanceof ApiError ? error.error : ''
      if (error instanceof ApiError && (error.status === 404 || REFUSED.includes(code))) {
        set(postingId, IDLE)
        onRefused()
      } else {
        set(postingId, { computing: false, problem: code === 'scoring in progress' ? 'busy'
          : code === 'internal error' ? 'broken' : 'failed' })
      }
    } finally {
      sending.current.delete(postingId)
    }
  }
  /** Forgets the `busy` problems, for when the slot they were about may be free (a pass has
   * ended); `failed` and `broken` ones and calls still computing stay. Stable across renders. */
  const clearBusy = useCallback(() => setCalls((current) => Object.fromEntries(
    Object.entries(current).filter(([, call]) => call.problem !== 'busy'))), [])
  return { call: (postingId: string) => calls[postingId] ?? IDLE, run, clearBusy }
}
