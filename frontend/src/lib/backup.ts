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
  const [refusal, setRefusal] = useState<string | null>(null)
  const [pressFailed, setPressFailed] = useState<string | null>(null)
  // Counts finished requests, so the polling timer is armed again after every one of them.
  const [settled, setSettled] = useState(0)
  const mounted = useRef(true)

  const refresh = useCallback(() => {
    api<BackupStatus>('/backup').then((answer) => {
      if (!mounted.current) return
      setStatus(answer)
      setUnavailable(null)
    }, (error) => {
      if (!mounted.current) return
      if (error instanceof ApiError && error.status === 409 && error.error === 'backup unavailable') {
        setStatus(null)
        setUnavailable(error.detail)
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

  const press = useCallback(() => {
    setRefusal(null)
    setPressFailed(null)
    api<{ status: BackupStatus }>('/backup', { method: 'POST' }).then((answer) => {
      if (!mounted.current) return
      setStatus(answer.status)
      setUnavailable(null)
      setSettled((count) => count + 1)
    }, (error) => {
      if (!(error instanceof ApiError) || !mounted.current) return
      if (error.status === 409 && error.error === 'backup refused') setRefusal(error.detail)
      else if (error.status === 409 && error.error === 'backup unavailable') {
        setStatus(null)
        setUnavailable(error.detail)
      } else if (!(error.status === 409 && error.error === 'backup running')) {
        setPressFailed(error.status === 0 ? 'Der Server ist nicht erreichbar.'
          : `Der Server hat mit einem Fehler geantwortet (${error.status}${error.detail ? `: ${error.detail}` : ''}).`)
      }
      refresh() // a backup already running, or any other change since the last status
    })
  }, [refresh])

  return { status, unavailable, refusal, pressFailed, press }
}
