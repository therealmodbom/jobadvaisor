import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, type MailboxAccount, type MailboxCheckState, type MailboxMail } from '@/api'
import { POLL_FAILURES, POLL_MS } from '@/lib/run'

const CHECK_KEY = 'jobadvaisor.mailbox-check'

/** The last check's ID kept across a reload, so its report (a check without a pick list is not
 * named by `GET /mailbox`) comes back until it is dismissed or the next check starts. Storage may
 * be blocked, so every access is guarded. */
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

/** The mailbox source's state: the account (`GET /mailbox`, read once `active` is true for the
 * first time, and again when a check ends, so the start date and the time of the last check
 * follow) and the check. The check is the one stored in this browser, else the one `GET /mailbox`
 * names (running, or with an unfinished pick list), so a reload or a second tab finds it; a
 * stored one that reads `finished` gives way to that one. While a check runs, or a mail of its
 * pick list is being read elsewhere, it is polled. `check` is the last state read (null: none
 * yet); `running` is true from the start until the state says otherwise; `stopping` from the
 * accepted cancel on; `lost` when the server forgot a running check (404); `notice` holds the
 * failure text of a start or cancel request; `pollFailed` is true after `POLL_FAILURES` failed
 * polls in a row, until `retryPoll`. `start(since)` starts a check (a 409 follows the check that
 * runs), `cancel` asks the running one to stop, `dismiss` drops the report, `refresh` reads the
 * check again, `setMail` replaces a mail of its pick list (after reading an oversized mail) and
 * `dismiss` forgets the check, once its report is hidden or its pick list finished. */
export function useMailbox(active: boolean) {
  const [account, setAccount] = useState<MailboxAccount | null>(null)
  const [accountFailed, setAccountFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [checkId, setCheckId] = useState<string | null>(storedCheck.get)
  const [check, setCheck] = useState<MailboxCheckState | null>(null)
  const [notice, setNotice] = useState('')
  const [lost, setLost] = useState(false)
  const [pollFailed, setPollFailed] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [wanted, setWanted] = useState(active)
  const sending = useRef(false)
  /** Whether the last state read said `running`, for the notice about a check the server forgot. */
  const wasRunning = useRef(false)
  const running = checkId !== null && (check === null || check.status === 'running')
  const polling = checkId !== null && (check === null || check.status === 'running' || check.mails.some((mail) => mail.reading))

  if (active && !wanted) setWanted(true)

  /** Follow the check `id`, as far as known from the next poll on. */
  const follow = useCallback((id: string | null) => {
    storedCheck.set(id)
    setCheck(null)
    setPollFailed(false)
    setCancelling(false)
    setLost(false)
    setCheckId(id)
  }, [])

  /** Read the account; with `adopt` and no check at hand, follow the one it names. */
  const load = useCallback((adopt = false) => api<MailboxAccount>('/mailbox').then((next) => {
    setAccount(next)
    setAccountFailed(false)
    if (adopt && next.check_id && !storedCheck.get()) follow(next.check_id)
  }, () => setAccountFailed(true)), [follow])

  useEffect(() => {
    if (wanted) void load(true)
  }, [wanted, attempt, load])

  useEffect(() => {
    if (!checkId || !polling || pollFailed) return
    let failures = 0
    let stale = false
    const poll = () => api<MailboxCheckState>(`/mailbox/checks/${checkId}`).then((next) => {
      if (stale) return
      failures = 0
      if (next.status === 'finished') {
        // Finished or replaced elsewhere: the check `GET /mailbox` names, if any, takes its place.
        storedCheck.set(null)
        setCheckId(null)
        setCheck(null)
        void load(true)
      } else {
        setCheck(next)
      }
    }, (error) => {
      if (stale) return
      if (error instanceof ApiError && error.status === 404) {
        // The server forgot it: only a check seen running is worth a notice.
        storedCheck.set(null)
        setLost(wasRunning.current)
        setCheckId(null)
        setCheck(null)
        void load(true)
      } else if (++failures >= POLL_FAILURES) {
        clearInterval(timer)
        setPollFailed(true)
      }
    })
    const timer = setInterval(poll, POLL_MS)
    poll() // at once, so a reload does not wait an interval for the state
    return () => {
      stale = true
      clearInterval(timer)
    }
  }, [checkId, polling, pollFailed, load])

  const status = check?.status
  useEffect(() => { wasRunning.current = status === 'running' }, [status])
  useEffect(() => {
    if (status && status !== 'running') void load()
  }, [status, checkId, load])

  /** Run one request; `sending` makes a double click send one. A failure shows `failure`. */
  async function send(request: () => Promise<void>, failure: string) {
    if (sending.current) return
    sending.current = true
    setNotice('')
    try {
      await request()
    } catch (error) {
      setNotice(error instanceof ApiError && error.error === 'read in progress'
        ? 'Eine zu große Mail wird gerade gelesen. Versuch es danach noch einmal.' : failure)
    } finally {
      sending.current = false
    }
  }

  const start = (since: string | null) => send(async () => {
    try {
      const answer = await api<{ check_id: string }>('/mailbox/checks', { method: 'POST', json: since ? { since } : undefined })
      follow(answer.check_id)
    } catch (error) {
      const other = error instanceof ApiError && error.status === 409 ? error.body.check_id : null
      if (typeof other !== 'string') {
        if (error instanceof ApiError && error.error === 'not configured') void load()
        throw error
      }
      follow(other)
    }
  }, 'Die Prüfung konnte nicht gestartet werden. Ist der Server erreichbar?')

  // A 409 means the check ended in between and a 404 that the server forgot it: the next poll shows that.
  const cancel = () => send(async () => {
    try {
      await api(`/mailbox/checks/${checkId}/cancel`, { method: 'POST' })
      setCancelling(true)
    } catch (error) {
      if (!(error instanceof ApiError && (error.status === 409 || error.status === 404))) throw error
    }
  }, 'Das Prüfen konnte nicht abgebrochen werden. Versuch es noch einmal.')

  /** Read the check again now (after a refused request that says it changed elsewhere). */
  const refresh = useCallback(async () => {
    if (!checkId) return
    try {
      const next = await api<MailboxCheckState>(`/mailbox/checks/${checkId}`)
      if (next.status === 'finished') {
        follow(null)
        void load(true)
      } else {
        setCheck(next)
      }
    } catch { /* the next poll or action tells */ }
  }, [checkId, follow, load])

  /** Replace the mail with `mail.key` in the pick list. */
  const setMail = (mail: MailboxMail) => setCheck((now) => now && { ...now, mails: now.mails.map((one) => one.key === mail.key ? mail : one) })

  return {
    account, accountFailed, retryAccount: () => { setAccountFailed(false); setAttempt(attempt + 1) },
    checkId, check, running, stopping: running && (cancelling || (check?.cancel_requested ?? false)),
    notice, lost, pollFailed, retryPoll: () => setPollFailed(false),
    start, cancel, refresh, setMail, load,
    dismiss: () => { follow(null); setNotice('') },
  }
}
