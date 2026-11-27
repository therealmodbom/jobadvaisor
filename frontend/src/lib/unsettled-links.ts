import { useEffect, useRef, useState } from 'react'
import { api, ApiError, type Attempt } from '@/api'

/** One row of `GET /unsettled-links`: a link an alert run could not settle. `state` is its outcome
 * (`waiting`: a computing run still has to fetch it, `in_run` says the same), `tries` the runs
 * that fetched it, `attempts` the last try's steps (no addresses) and `reason` the last try's
 * English reason when no attempt was made (never shown). */
export type UnsettledLink = {
  url: string
  title: string
  source: 'mailbox' | 'paste'
  state: 'waiting' | 'unread' | 'unclear' | 'not_reached'
  tries: number
  added_at: string
  last_tried_at: string | null
  attempts: Omit<Attempt, 'url'>[]
  reason: string | null
  in_run: boolean
}

/** What a view knows of the list: not read yet, the rows with `run_id` (the computing alert run,
 * else null), the file unreadable (503, `detail` is the loader's English problem), or the server
 * not answering. */
export type UnsettledState =
  | { kind: 'loading' }
  | { kind: 'ready'; links: UnsettledLink[]; runId: string | null }
  | { kind: 'unreadable'; detail: string }
  | { kind: 'failed' }

/** Whether `error` is the 503 `unsettled links unreadable` of a route that needs the list file
 * (the list, a removal, a run start, the finish of a pick list): the file is invalid, and nothing
 * was started or marked. */
export function isUnreadable(error: unknown): boolean {
  return error instanceof ApiError && error.status === 503 && error.error === 'unsettled links unreadable'
}

const EVENT = 'unsettled-links-changed'

/** Tells every `useUnsettledLinks` to read the list again; called when a run's state moves and
 * after a removal. */
export function notifyUnsettledLinks() {
  window.dispatchEvent(new Event(EVENT))
}

/** How often the list is read again while an alert run computes, so a run another device started
 * frees the retry buttons once it ends. */
export const LIST_POLL_MS = 5000

/** The unsettled links, read on mount, whenever `active` turns true (the tab was opened), on
 * `notifyUnsettledLinks`, and every `LIST_POLL_MS` while the list names a computing run. A re-read
 * keeps the rows it shows until the answer arrives, and only the latest answer counts. A 503
 * `unsettled links unreadable` gives `unreadable`; any other failure keeps a list already read and
 * otherwise gives `failed`. */
export function useUnsettledLinks(active = false): UnsettledState {
  const [state, setState] = useState<UnsettledState>({ kind: 'loading' })
  const wasActive = useRef(active)
  const readAgain = useRef(() => {})
  const runId = state.kind === 'ready' ? state.runId : null
  useEffect(() => {
    if (!runId) return
    const timer = window.setInterval(() => readAgain.current(), LIST_POLL_MS)
    return () => window.clearInterval(timer)
  }, [runId])
  useEffect(() => {
    let stale = false
    let latest = 0
    const read = () => {
      const mine = ++latest
      api<{ links: UnsettledLink[]; run_id: string | null }>('/unsettled-links').then(
        (answer) => { if (!stale && mine === latest) setState({ kind: 'ready', links: answer.links, runId: answer.run_id }) },
        (error) => {
          if (stale || mine !== latest) return
          if (isUnreadable(error)) {
            setState({ kind: 'unreadable', detail: (error as ApiError).detail })
          } else {
            setState((now) => now.kind === 'ready' ? now : { kind: 'failed' })
          }
        })
    }
    readAgain.current = read
    read()
    window.addEventListener(EVENT, read)
    return () => { stale = true; window.removeEventListener(EVENT, read) }
  }, [])
  useEffect(() => {
    if (active && !wasActive.current) notifyUnsettledLinks()
    wasActive.current = active
  }, [active])
  return state
}

/** The number a badge shows: the links that need attention (not waiting in a computing run), or 0
 * while the list is loading, unreadable or unavailable. */
export function countOf(state: UnsettledState): number {
  return state.kind === 'ready' ? state.links.filter((link) => !link.in_run).length : 0
}
