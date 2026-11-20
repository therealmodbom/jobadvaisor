import { useEffect, useRef, useState } from 'react'
import { api, ApiError, type CheckState } from '@/api'
import { POLL_FAILURES, POLL_MS } from '@/lib/run'

const CHECK_KEY = 'jobadvaisor.pool-check'

/** The check ID kept across a reload (and, until the report is dismissed, after the check ended,
 * so the report comes back too); storage may be blocked, so every access is guarded. */
const storedCheck = {
  get: () => {
    try {
      return localStorage.getItem(CHECK_KEY)
    } catch {
      return null
    }
  },
  set: (id: string | null) => {
    try {
      if (id) localStorage.setItem(CHECK_KEY, id)
      else localStorage.removeItem(CHECK_KEY)
    } catch { /* storage blocked: a reload simply does not resume */ }
  },
}

/** What a started check looks like before its first poll. */
const started = (check_id: string, total: number): CheckState => ({
  check_id, status: 'running', error: null, total, done: 0, cancel_requested: false,
  counts: { available: 0, closed: 0, unknown: 0 }, still_closed: 0, closed: [],
})

/** The availability check: starts it, polls it while it runs, and keeps its ID across a reload
 * until the report is dismissed. `onDone` runs when a check ends (done, cancelled or failed), so
 * the pool can load again. `check` is the last state read (null: none yet, or none kept);
 * `running` is true from the start until the state says otherwise; `stopping` is true from the
 * accepted cancel request on, so a poll that started before it cannot enable the button again.
 * A start refused with 409 follows the check that runs. `lost` is true when the server no longer
 * knows the check (404); `notice` holds the failure text of a start or cancel request, and
 * `pollFailed` is true after `POLL_FAILURES` failed polls in a row, until `retryPoll`. `dismiss`
 * drops the report (and the stored ID). The view keys everything off `check.status`, never off
 * `cancel_requested` alone: a cancel that races the last posting ends `done`. */
export function useCheck(onDone: () => void) {
  const [checkId, setCheckId] = useState<string | null>(storedCheck.get)
  const [check, setCheck] = useState<CheckState | null>(null)
  const [notice, setNotice] = useState('')
  const [lost, setLost] = useState(false)
  const [pollFailed, setPollFailed] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const sending = useRef(false)
  const running = checkId !== null && (check === null || check.status === 'running')

  useEffect(() => {
    if (!checkId || !running || pollFailed) return
    let failures = 0
    let stale = false
    const timer = setInterval(() => {
      api<CheckState>(`/availability/checks/${checkId}`).then((next) => {
        if (stale) return
        failures = 0
        setCheck(next)
        if (next.status === 'failed') storedCheck.set(null)
        if (next.status !== 'running') onDone()
      }, (error) => {
        if (stale) return
        if (error instanceof ApiError && error.status === 404) {
          storedCheck.set(null)
          setCheckId(null)
          setCheck(null)
          setLost(true)
        } else if (++failures >= POLL_FAILURES) {
          clearInterval(timer)
          setPollFailed(true)
        }
      })
    }, POLL_MS)
    return () => {
      stale = true
      clearInterval(timer)
    }
  }, [checkId, running, pollFailed, onDone])

  /** Run one request; `sending` makes a double click send one. A failure shows `failure`. */
  async function send(request: () => Promise<void>, failure: string) {
    if (sending.current) return
    sending.current = true
    setNotice('')
    try {
      await request()
    } catch {
      setNotice(failure)
    } finally {
      sending.current = false
    }
  }
  /** Follow the check `id`, as far as known with `first` as its state. */
  function follow(id: string, first: CheckState | null) {
    storedCheck.set(id)
    setCheck(first)
    setPollFailed(false)
    setCancelling(false)
    setLost(false)
    setCheckId(id)
  }
  const start = () => send(async () => {
    try {
      const answer = await api<{ check_id: string; total: number }>('/availability/checks', { method: 'POST' })
      follow(answer.check_id, started(answer.check_id, answer.total))
    } catch (error) {
      const other = error instanceof ApiError && error.status === 409 ? error.body.check_id : null
      if (typeof other !== 'string') throw error
      follow(other, null)
    }
  }, 'Die Prüfung konnte nicht gestartet werden. Ist der Server erreichbar?')
  // A 409 means the check ended in between and a 404 that the server forgot it: the next poll shows that.
  const cancel = () => send(async () => {
    try {
      await api(`/availability/checks/${checkId}/cancel`, { method: 'POST' })
      setCancelling(true)
    } catch (error) {
      if (!(error instanceof ApiError && (error.status === 409 || error.status === 404))) throw error
    }
  }, 'Das Prüfen konnte nicht abgebrochen werden. Versuch es noch einmal.')
  function dismiss() {
    storedCheck.set(null)
    setCheckId(null)
    setCheck(null)
    setLost(false)
    setNotice('')
  }
  return { check, running, stopping: running && (cancelling || (check?.cancel_requested ?? false)),
           notice, lost, pollFailed, retryPoll: () => setPollFailed(false), start, cancel, dismiss }
}
