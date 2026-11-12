import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { api } from '@/api'
import { stubApi } from '@/test-api'
import { useBackupStatus, type BackupStatus } from '@/lib/backup'

const QUIET: BackupStatus = {
  pending: false, uncommitted: 0, unpushed: 0, branch: 'main', remote: 'origin/main',
  operation: null, running: false, progress: null, last_result: null,
  last_success: '2026-11-12T09:12:00Z', last_failure: null,
}
const PENDING: BackupStatus = { ...QUIET, pending: true, uncommitted: 3 }
const RUNNING: BackupStatus = {
  ...PENDING, running: true, progress: { step: 'pushing', files: 3, percent: 60 },
}

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  delete (document as { visibilityState?: unknown }).visibilityState
})

/** Serves `GET /backup` with the given bodies in order, the last one for every later request;
 * returns the calls the stub received. */
function serve(...bodies: unknown[]) {
  let requests = 0
  const calls = stubApi({ 'GET /backup': () => ({ body: bodies[Math.min(requests++, bodies.length - 1)] }) })
  return () => calls.filter((call) => call.method === 'GET' && call.path === '/backup').length
}

const flush = () => act(async () => { await vi.advanceTimersByTimeAsync(0) })
const advance = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms) })

async function tab(state: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true })
  await act(async () => { document.dispatchEvent(new Event('visibilitychange')) })
}

test('the status is fetched on mount', async () => {
  const requests = serve(PENDING)
  const { result } = renderHook(() => useBackupStatus())
  expect(result.current.status).toBeNull()
  await flush()
  expect(requests()).toBe(1)
  expect(result.current.status).toEqual(PENDING)
  expect(result.current.unavailable).toBeNull()
})

test('the status is fetched again every 15 seconds while the tab is visible', async () => {
  const requests = serve(QUIET)
  renderHook(() => useBackupStatus())
  await flush()
  await advance(14_000)
  expect(requests()).toBe(1)
  await advance(1_000)
  expect(requests()).toBe(2)
  await advance(15_000)
  expect(requests()).toBe(3)
})

test('a running backup is fetched every second, and back to 15 seconds once it ends', async () => {
  const requests = serve(RUNNING, RUNNING, QUIET)
  const { result } = renderHook(() => useBackupStatus())
  await flush()
  await advance(1_000)
  expect(requests()).toBe(2)
  await advance(1_000)
  expect(requests()).toBe(3)
  expect(result.current.status?.running).toBe(false)
  await advance(14_000)
  expect(requests()).toBe(3)
  await advance(1_000)
  expect(requests()).toBe(4)
})

test('a hidden tab does not poll, and becoming visible fetches at once and polls again', async () => {
  const requests = serve(QUIET)
  renderHook(() => useBackupStatus())
  await flush()
  await tab('hidden')
  expect(requests()).toBe(1)
  await advance(60_000)
  expect(requests()).toBe(1)
  await tab('visible')
  await flush()
  expect(requests()).toBe(2)
  await advance(15_000)
  expect(requests()).toBe(3)
})

test('a failed fetch leaves the last status in place and polling goes on', async () => {
  let requests = 0
  stubApi({ 'GET /backup': () => requests++ === 0
    ? { body: PENDING } : { status: 500, body: { error: 'internal error', detail: '' } } })
  const { result } = renderHook(() => useBackupStatus())
  await flush()
  await advance(15_000)
  expect(requests).toBe(2)
  expect(result.current.status).toEqual(PENDING)
  await advance(15_000)
  expect(requests).toBe(3)
})

test('a successful write to the backend refetches the status at once, a read does not', async () => {
  let gets = 0
  stubApi({
    'GET /backup': () => { gets++; return { body: QUIET } },
    'PUT /postings/p1/rating': { body: {} },
    'GET /pool': { body: {} },
  })
  renderHook(() => useBackupStatus())
  await flush()
  expect(gets).toBe(1)
  await act(async () => { await api('/pool') })
  await flush()
  expect(gets).toBe(1)
  await act(async () => { await api('/postings/p1/rating', { method: 'PUT', json: {} }) })
  await flush()
  expect(gets).toBe(2)
})

test('a failed write does not refetch the status', async () => {
  let gets = 0
  stubApi({
    'GET /backup': () => { gets++; return { body: QUIET } },
    'PUT /postings/p1/rating': { status: 422, body: { error: 'invalid rating', detail: '' } },
  })
  renderHook(() => useBackupStatus())
  await flush()
  await act(async () => { await api('/postings/p1/rating', { method: 'PUT', json: {} }).catch(() => {}) })
  await flush()
  expect(gets).toBe(1)
})

test('an unavailable backup clears the status and gives the reason', async () => {
  stubApi({ 'GET /backup': { status: 409, body: {
    error: 'backup unavailable', detail: '/data is not a git repository' } } })
  const { result } = renderHook(() => useBackupStatus())
  await flush()
  expect(result.current.status).toBeNull()
  expect(result.current.unavailable).toBe('/data is not a git repository')
})

test('pressing starts a backup and takes the status the answer carries', async () => {
  let current = PENDING
  const calls = stubApi({
    'GET /backup': () => ({ body: current }),
    'POST /backup': () => { current = RUNNING; return { status: 202, body: { status: RUNNING } } },
  })
  const { result } = renderHook(() => useBackupStatus())
  await flush()
  act(() => result.current.press())
  await flush()
  expect(calls.some((call) => call.method === 'POST' && call.path === '/backup')).toBe(true)
  expect(result.current.status).toEqual(RUNNING)
})

test('a press refused because a backup runs fetches the status instead', async () => {
  let gets = 0
  stubApi({
    'GET /backup': () => ({ body: gets++ === 0 ? PENDING : RUNNING }),
    'POST /backup': { status: 409, body: { error: 'backup running', detail: 'a backup is running' } },
  })
  const { result } = renderHook(() => useBackupStatus())
  await flush()
  act(() => result.current.press())
  await flush()
  expect(result.current.status).toEqual(RUNNING)
  expect(result.current.refusal).toBeNull()
})

test('a press that fails with a server error says so, and the next press clears it', async () => {
  let fail = true
  stubApi({
    'GET /backup': { body: PENDING },
    'POST /backup': () => fail
      ? { status: 500, body: { error: 'internal error', detail: 'RuntimeError: boom' } }
      : { status: 202, body: { status: RUNNING } },
  })
  const { result } = renderHook(() => useBackupStatus())
  await flush()
  act(() => result.current.press())
  await flush()
  expect(result.current.pressFailed).toBe(
    'Sichern ist nicht bestätigt: Der Server hat mit einem Fehler geantwortet (500: RuntimeError: boom).')
  expect(result.current.refusal).toBeNull()
  fail = false
  act(() => result.current.press())
  await flush()
  expect(result.current.pressFailed).toBeNull()
})

test('a press that never reaches the server says so, also when the status cannot be fetched either', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('network down') }))
  const { result } = renderHook(() => useBackupStatus())
  await flush()
  act(() => result.current.press())
  await flush()
  expect(result.current.pressFailed).toBe(
    'Der Server ist nicht erreichbar. Ob das Sichern gestartet wurde, ist unklar.')
  expect(result.current.status).toBeNull()
})

test('an older status that arrives late does not overwrite a newer one', async () => {
  let gets = 0
  let releaseStale: () => void = () => {}
  const stale = new Promise<void>((resolve) => { releaseStale = resolve })
  stubApi({
    'GET /backup': async () => {
      const n = ++gets
      if (n === 2) await stale // the second fetch is slow and answers with what was true before
      return { body: n === 1 || n === 2 ? PENDING : RUNNING }
    },
    'POST /backup': { status: 202, body: { status: RUNNING } },
  })
  const { result } = renderHook(() => useBackupStatus())
  await flush()
  await tab('visible') // starts the slow fetch
  act(() => result.current.press())
  await flush()
  expect(result.current.status).toEqual(RUNNING)
  releaseStale()
  await flush()
  expect(result.current.status).toEqual(RUNNING)
})

test('the backup POST itself does not fetch the status a second time', async () => {
  let gets = 0
  stubApi({
    'GET /backup': () => { gets++; return { body: PENDING } },
    'POST /backup': { status: 202, body: { status: RUNNING } },
  })
  const { result } = renderHook(() => useBackupStatus())
  await flush()
  act(() => result.current.press())
  await flush()
  expect(gets).toBe(1)
})

test('a refusal goes once the status no longer shows its cause', async () => {
  let branch = 'other'
  stubApi({
    'GET /backup': () => ({ body: { ...PENDING, branch } }),
    'POST /backup': { status: 409, body: { error: 'backup refused', detail: 'on branch other' } },
  })
  const { result } = renderHook(() => useBackupStatus())
  await flush()
  act(() => result.current.press())
  await flush()
  expect(result.current.refusal).toBe('on branch other')
  branch = 'main'
  await advance(15_000) // the next poll sees the branch back on main
  expect(result.current.refusal).toBeNull()
})

test('a refusal is not wiped by a status fetched before the press', async () => {
  let refused = false
  let release: () => void = () => {}
  const held = new Promise<void>((resolve) => { release = resolve })
  stubApi({
    'GET /backup': async () => {
      if (refused) await held // the status after the refusal is still on its way
      return { body: { ...PENDING, branch: refused ? 'other' : 'main' } }
    },
    'POST /backup': () => {
      refused = true // the branch changed on the server after the last poll
      return { status: 409, body: { error: 'backup refused', detail: 'on branch other' } }
    },
  })
  const { result } = renderHook(() => useBackupStatus())
  await flush()
  act(() => result.current.press())
  await flush()
  expect(result.current.refusal).toBe('on branch other') // the old `main` status does not wipe it
  release()
  await flush()
  expect(result.current.refusal).toBe('on branch other')
})

test('a first fetch that fails gives a reason in place of the button, and a later one clears it', async () => {
  let fail = true
  stubApi({
    'GET /backup': () => fail ? { status: 500, body: { error: 'internal error', detail: '' } }
      : { body: QUIET },
  })
  const { result } = renderHook(() => useBackupStatus())
  await flush()
  expect(result.current.status).toBeNull()
  expect(result.current.unavailable).toBe('Der Backup-Status ließ sich nicht abrufen.')
  fail = false
  await advance(15_000)
  expect(result.current.unavailable).toBeNull()
  expect(result.current.status).toEqual(QUIET)
})

test('an answer that is no status (for instance the page itself) counts as a failed fetch', async () => {
  serve({})
  const { result } = renderHook(() => useBackupStatus())
  await flush()
  expect(result.current.status).toBeNull()
  expect(result.current.unavailable).toBe('Der Backup-Status ließ sich nicht abrufen.')
})

test('a later answer that is no status keeps the last status', async () => {
  serve(QUIET, {})
  const { result } = renderHook(() => useBackupStatus())
  await flush()
  await advance(15_000)
  expect(result.current.status).toEqual(QUIET)
  expect(result.current.unavailable).toBeNull()
})

test('a press failure goes once a backup runs', async () => {
  let running = false
  stubApi({
    'GET /backup': () => ({ body: running ? RUNNING : PENDING }),
    'POST /backup': { status: 500, body: { error: 'internal error', detail: '' } },
  })
  const { result } = renderHook(() => useBackupStatus())
  await flush()
  act(() => result.current.press())
  await flush()
  expect(result.current.pressFailed).not.toBeNull()
  running = true
  await advance(15_000)
  expect(result.current.pressFailed).toBeNull()
})

test('a press refused for the branch names why and clears on the next press', async () => {
  let refuse = true
  stubApi({
    'GET /backup': { body: { ...PENDING, branch: 'other' } },
    'POST /backup': () => refuse
      ? { status: 409, body: { error: 'backup refused', detail: 'on branch other' } }
      : { status: 202, body: { status: RUNNING } },
  })
  const { result } = renderHook(() => useBackupStatus())
  await flush()
  act(() => result.current.press())
  await flush()
  expect(result.current.refusal).toBe('on branch other')
  refuse = false
  act(() => result.current.press())
  await flush()
  expect(result.current.refusal).toBeNull()
})
