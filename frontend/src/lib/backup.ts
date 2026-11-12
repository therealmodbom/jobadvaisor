import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, WRITE_DONE } from '@/api'

/** The step a running backup is at, in order. */
export type BackupStep = 'staging' | 'committing' | 'pushing'

/** What a running backup reports: the step, the number of staged files and the share of the
 * push git reports as done (`null` until it reports one, and for a push too small to). */
export type BackupProgress = { step: BackupStep; files: number; percent: number | null }

/** The last backup that finished: when, what it did and the commit it ended on. `committed` means
 * nothing was pushed because the repository has no remote. */
export type BackupResult = {
  at: string
  result: 'pushed' | 'committed' | 'up_to_date'
  commit: string
}

/** A commit or push that failed: when, at which step, and git's message. */
export type BackupFailure = { at: string; step: 'commit' | 'push'; reason: string }

/** The body of `GET /backup`. */
export type BackupStatus = {
  pending: boolean
  uncommitted: number
  unpushed: number
  branch: string | null
  remote: string | null
  operation: string | null
  running: boolean
  progress: BackupProgress | null
  last_result: BackupResult | null
  last_success: string | null
  last_failure: BackupFailure | null
}

/** How often the status is fetched while the tab is visible: every second while a backup runs. */
export const RUNNING_INTERVAL_MS = 1000
export const IDLE_INTERVAL_MS = 15000

const pad = (n: number) => String(n).padStart(2, '0')

/** A point in time the way the backup line says it: `heute, 09:12`, `gestern, 21:05`, else
 * `3.11., 08:30`, in the browser's time zone. */
export function whenText(iso: string, now: Date = new Date()): string {
  const date = new Date(iso)
  const clock = `${pad(date.getHours())}:${pad(date.getMinutes())}`
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const days = Math.round((day(now) - day(date)) / 86_400_000)
  if (days === 0) return `heute, ${clock}`
  if (days === 1) return `gestern, ${clock}`
  return `${date.getDate()}.${date.getMonth() + 1}., ${clock}`
}

/** What `useBackupStatus` hands to the control. */
export type BackupState = {
  /** The last status fetched, `null` until one has arrived or while the backup is unavailable. */
  status: BackupStatus | null
  /** Why the backup is unavailable (the backend's reason), else `null`. */
  unavailable: string | null
  /** Why the last press was refused (another branch, an operation in progress), else `null`. */
  refusal: string | null
  /** A German sentence when the last press did not reach the backend or failed there (a server
   * error, a lost connection), else `null`: the backup did not start, or the answer is unknown. */
  pressFailed: string | null
  /** Starts a backup; the status follows by itself. */
  press: () => void
}

/** The backup status of the data repository (`GET /backup`), kept current: fetched on mount and
 * whenever the tab becomes visible or the app wrote something, every second while a backup runs
 * and every 15 seconds otherwise while the tab is visible. A failed fetch leaves the last status in
 * place. A 409
 * `backup unavailable` is an answer, not a failure: it clears the status and sets
 * `unavailable`. */
export function useBackupStatus(): BackupState {
  const [status, setStatus] = useState<BackupStatus | null>(null)
  const [unavailable, setUnavailable] = useState<string | null>(null)
  // The refusal's detail, and the number of the press it answers: only a status fetched after
  // that press can show that its cause is gone.
  const [refusal, setRefusal] = useState<{ detail: string; after: number } | null>(null)
  const [statusId, setStatusId] = useState(0) // the request the current status came from
  const [pressFailed, setPressFailed] = useState<string | null>(null)
  // Counts finished requests, so the polling timer is armed again after every one of them.
  const [settled, setSettled] = useState(0)
  const mounted = useRef(true)
  // Every request takes a number when it starts, and an answer is used only if no later request
  // has been used already: a slow older fetch must not overwrite a newer status.
  const issued = useRef(0)
  const applied = useRef(0)
  const fresh = (id: number) => {
    if (!mounted.current || id < applied.current) return false
    applied.current = id
    return true
  }

  const hasStatus = useRef(false)

  const refresh = useCallback(() => {
    const id = ++issued.current
    api<BackupStatus>('/backup').then((answer) => {
      // `api` reads an unparseable body as `{}`: a 200 that is no status (a proxy serving the
      // page) is a failed fetch, not a status to render.
      if (typeof answer?.pending !== 'boolean') throw new Error('not a backup status')
      return answer
    }).then((answer) => {
      if (!fresh(id)) return
      hasStatus.current = true
      setStatus(answer)
      setStatusId(id)
      setUnavailable(null)
    }, (error) => {
      if (!fresh(id)) return
      if (error instanceof ApiError && error.status === 409 && error.error === 'backup unavailable') {
        hasStatus.current = false
        setStatus(null)
        setStatusId(id)
        setUnavailable(error.detail)
      } else if (!hasStatus.current) {
        // No status yet and none to keep: say so, so the header still has its button.
        setUnavailable('Der Backup-Status ließ sich nicht abrufen.')
      }
    }).finally(() => { if (mounted.current) setSettled((count) => count + 1) })
  }, [])

  useEffect(() => {
    mounted.current = true
    refresh()
    const onVisibility = () => { if (document.visibilityState === 'visible') refresh() }
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener(WRITE_DONE, refresh) // a rating or an import is pending now
    return () => {
      mounted.current = false
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener(WRITE_DONE, refresh)
    }
  }, [refresh])

  const running = status?.running === true
  useEffect(() => {
    const timer = window.setTimeout(() => {
      // A hidden tab stops polling; becoming visible fetches, and that arms the timer again.
      if (document.visibilityState !== 'hidden') refresh()
    }, running ? RUNNING_INTERVAL_MS : IDLE_INTERVAL_MS)
    return () => window.clearTimeout(timer)
  }, [settled, running, refresh])

  // A refusal stays until its cause is gone (the branch is `main` again, no operation is stopped),
  // a failed press until a backup runs or the next press.
  // Adjusted while rendering (React's way to derive state from state), not in an effect.
  if (refusal && status && statusId > refusal.after && status.branch === 'main' && !status.operation) {
    setRefusal(null)
  }
  if (pressFailed && status?.running) setPressFailed(null)

  const press = useCallback(() => {
    setRefusal(null)
    setPressFailed(null)
    const id = ++issued.current
    api<{ status: BackupStatus }>('/backup', { method: 'POST' }).then((answer) => {
      if (!fresh(id)) return
      hasStatus.current = true
      setStatus(answer.status)
      setStatusId(id)
      setUnavailable(null)
      setSettled((count) => count + 1)
    }, (error) => {
      if (!(error instanceof ApiError) || !mounted.current) return
      if (error.status === 409 && error.error === 'backup refused') setRefusal({ detail: error.detail, after: id })
      else if (error.status === 409 && error.error === 'backup unavailable') {
        hasStatus.current = false
        setStatus(null)
        setUnavailable(error.detail)
      } else if (!(error.status === 409 && error.error === 'backup running')) {
        // A lost connection can drop the answer of a backup that did start: say it is unknown.
        setPressFailed(error.status === 0
          ? 'Der Server ist nicht erreichbar. Ob das Sichern gestartet wurde, ist unklar.'
          : `Sichern ist nicht bestätigt: Der Server hat mit einem Fehler geantwortet (${error.status}${error.detail ? `: ${error.detail}` : ''}).`)
      }
      refresh() // a backup already running, or any other change since the last status
    })
  }, [refresh])

  return { status, unavailable, refusal: refusal?.detail ?? null, pressFailed, press }
}
