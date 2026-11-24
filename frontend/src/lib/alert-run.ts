import { useEffect, useState } from 'react'
import { api, ApiError, type AlertRunEntry, type AlertRunState } from '@/api'
import { POLL_FAILURES, POLL_MS } from '@/lib/run'

/** The base of a stored-anyway run: the original run, and each stored-anyway run with the row it
 * replaces, oldest first. */
type RunBase = { id: string; overlays: { run: string; index: number }[] }

/** Where a view keeps its alert run across a reload (`sessionStorage`, which storage may block,
 * so every access is guarded). Each view that shows runs has its own keys. */
export type RunStore = {
  get: () => string | null
  /** For the run of a stored-anyway entry: the original run, and each stored-anyway run with the row it replaces, oldest first. */
  getBase: () => RunBase | null
  /** Keeps run `id` (`null` drops it), and with `base` the report its single row belongs to. */
  set: (id: string | null, base?: RunBase) => void
}

/** The store of a view: the run's ID under `runKey`, its stored-anyway base under `baseKey`. */
export function runStore(runKey: string, baseKey: string): RunStore {
  return {
    get: () => {
      try {
        return sessionStorage.getItem(runKey)
      } catch {
        return null
      }
    },
    getBase: () => {
      try {
        const base = JSON.parse(sessionStorage.getItem(baseKey) ?? 'null')
        return base && Array.isArray(base.overlays) ? base : null
      } catch {
        return null
      }
    },
    set: (id, base) => {
      try {
        if (id) sessionStorage.setItem(runKey, id)
        else sessionStorage.removeItem(runKey)
        if (id && base) sessionStorage.setItem(baseKey, JSON.stringify(base))
        else sessionStorage.removeItem(baseKey)
      } catch { /* storage blocked: a reload simply does not resume */ }
    },
  }
}

/** One entry to add: `force` stores a text duplicate anyway. */
export type RunEntry = { url: string; title: string; force: boolean }
/** The row of a text duplicate stored anyway, and the report it belongs to. */
export type RunRowRef = { index: number; base: AlertRunEntry[] }

/** The state of one alert run of a view, kept in `store` across a reload. `runId` is the run it
 * shows (null: none); `progress` its last state (null: not read yet); `running` is true until the
 * state says otherwise; `pollFailed` after `POLL_FAILURES` failed polls in a row (`retryPoll`
 * resumes); `gone` when the server no longer knows the run (it restarted, 404); `forced` the
 * report a stored-anyway run of one row belongs to; `starting` and `startError` belong to
 * `start`, which POSTs `entries` as a run (or, with `row`, a run of one text duplicate stored
 * anyway) and shows it at once. A 409 attaches to the computing run. `attach` shows run `id`
 * (from `entries`, when they are known), `clear` drops the run. */
export function useAlertRun(store: RunStore) {
  const [runId, setRunId] = useState<string | null>(store.get)
  const [progress, setProgress] = useState<AlertRunState | null>(null)
  const [pollFailed, setPollFailed] = useState(false)
  const [gone, setGone] = useState(false)
  const [forced, setForced] = useState<RunRowRef | null>(null)
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState(false)

  const running = runId !== null && (progress === null || progress.status === 'running')

  useEffect(() => {
    // After a reload: rebuild the original report and put each stored-anyway run's row back into it.
    const base = store.getBase()
    if (!base || base.overlays.length === 0) return
    let stale = false
    Promise.all([base.id, ...base.overlays.map((overlay) => overlay.run)]
      .map((id) => api<AlertRunState>(`/alert-mails/runs/${id}`))).then(([original, ...forcedRuns]) => {
      if (stale) return
      const entries = [...original.entries]
      base.overlays.forEach((overlay, i) => {
        if (forcedRuns[i].entries[0]) entries[overlay.index] = forcedRuns[i].entries[0]
      })
      setForced({ index: base.overlays[base.overlays.length - 1].index, base: entries })
    }, () => {})
    return () => { stale = true }
  }, [store])

  useEffect(() => {
    if (!runId || !running || pollFailed) return
    let failures = 0
    let stale = false
    const poll = () => api<AlertRunState>(`/alert-mails/runs/${runId}`).then((next) => {
      if (stale) return
      failures = 0
      setProgress(next)
    }, (error) => {
      if (stale) return
      if (error instanceof ApiError && error.status === 404) {
        store.set(null)
        setRunId(null)
        setProgress(null)
        setForced(null)
        setGone(true)
      } else if (++failures >= POLL_FAILURES) {
        clearInterval(timer)
        setPollFailed(true)
      }
    })
    const timer = setInterval(poll, POLL_MS)
    poll() // at once, so a reload does not show a finished run as running for an interval
    return () => {
      stale = true
      clearInterval(timer)
    }
  }, [runId, running, pollFailed, store])

  /** Shows run `id`, as far as known with `entries` as its waiting rows. */
  function attach(id: string, entries?: { url: string; title: string }[]) {
    store.set(id)
    setProgress(entries ? { run_id: id, status: 'running', error: null, total: entries.length, done: 0,
                            entries: entries.map((entry) => ({ url: entry.url, title: entry.title, state: 'waiting' as const })) }
                         : null)
    setForced(null)
    setPollFailed(false)
    setGone(false)
    setRunId(id)
  }

  /** Drops the run, its stored ID and every notice about it. */
  function clear() {
    store.set(null)
    setRunId(null)
    setProgress(null)
    setForced(null)
    setGone(false)
    setStartError(false)
  }

  /** Starts a run of `entries`, as the first run of a view or, with `row`, a run of one text duplicate stored anyway. */
  async function start(entries: RunEntry[], row?: RunRowRef) {
    if (starting || running) return
    setStarting(true)
    setStartError(false)
    try {
      const { run_id: id } = await api<{ run_id: string }>('/alert-mails/runs', { method: 'POST', json: { entries } })
      const prior = row ? store.getBase() : null
      store.set(id, row && runId ? { id: prior?.id ?? runId,
                                     overlays: [...(prior?.overlays ?? []), { run: id, index: row.index }] } : undefined)
      setForced(row ?? null)
      setPollFailed(false)
      setProgress({ run_id: id, status: 'running', error: null, total: entries.length, done: 0,
                    entries: entries.map((entry) => ({ url: entry.url, title: entry.title, state: row ? 'running' : 'waiting' })) })
      setRunId(id)
    } catch (error) {
      if (error instanceof ApiError && error.status === 409 && typeof error.body.run_id === 'string') {
        store.set(error.body.run_id)
        setProgress(null)
        setForced(null)
        setPollFailed(false)
        setRunId(error.body.run_id)
      } else {
        setStartError(true)
      }
    } finally {
      setStarting(false)
    }
  }

  return { runId, progress, running, pollFailed, gone, forced, starting, startError,
           start, attach, clear, retryPoll: () => setPollFailed(false) }
}

/** The hook's state, as `AlertRunView` takes it. */
export type AlertRun = ReturnType<typeof useAlertRun>
