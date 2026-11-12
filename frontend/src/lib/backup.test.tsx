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

test('a press refused for the branch names why and clears on the next press', async () => {
  let refuse = true
  stubApi({
    'GET /backup': { body: PENDING },
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
