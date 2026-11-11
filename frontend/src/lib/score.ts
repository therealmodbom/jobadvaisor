import { useRef, useState } from 'react'
import { ApiError, postScore, type ScoreAnswer } from '@/api'

/** The state of one posting's score click: `computing` while the request runs, `problem` after a
 * failure worth a retry (`busy`: another score or a pass holds the slot; `failed`: anything else
 * that may pass), else null. */
export type ScoreCall = { computing: boolean; problem: 'busy' | 'failed' | null }

const IDLE: ScoreCall = { computing: false, problem: null }

/** The `error` codes of a 409 that no retry changes: the posting is excluded, held or never checked. */
const REFUSED = ['excluded', 'held', 'unscreened']

/** Scoring single postings on demand (`POST /postings/{id}/score`) for the posting page and the
 * pool rows. `run(postingId)` sends the click: a second click on a posting still computing sends
 * nothing; `call(postingId)` is that posting's `ScoreCall`. `onAnswer` gets the 200 answer. A
 * refusal no retry can change (409 `excluded`, `held` or `unscreened`, or 404) calls `onRefused`
 * so the view reloads and shows the posting as it is now; every other failure sets a `problem`. */
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
        set(postingId, { computing: false, problem: code === 'scoring in progress' ? 'busy' : 'failed' })
      }
    } finally {
      sending.current.delete(postingId)
    }
  }
  return { call: (postingId: string) => calls[postingId] ?? IDLE, run }
}
