import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { AlertRunState } from '@/api'
import { stubApi } from '@/test-api'
import { runStore, useAlertRun } from '@/lib/alert-run'
import { POLL_MS } from '@/lib/run'
import { countOf, LIST_POLL_MS, notifyUnsettledLinks, useUnsettledLinks, type UnsettledLink } from '@/lib/unsettled-links'

const link = (n: number, over: Partial<UnsettledLink> = {}): UnsettledLink => ({
  url: `https://jobs.example.com/${n}`, title: `Stelle ${n}`, source: 'mailbox', state: 'unread', tries: 1,
  added_at: '2026-11-27T08:00:00Z', last_tried_at: '2026-11-27T08:05:00Z', attempts: [], reason: null,
  in_run: false, ...over,
})

const run = (done: number, status: AlertRunState['status'] = 'running'): AlertRunState => ({
  run_id: 'r1', status, error: null, cancel_requested: false, total: 3, done,
  entries: [1, 2, 3].map((n) => ({ url: `https://jobs.example.com/${n}`, title: `Stelle ${n}`,
                                    state: n <= done ? 'stored' as const : 'waiting' as const })),
})

const heard = vi.fn()
const store = runStore('jobadvaisor.test-run', 'jobadvaisor.test-run-base')

beforeEach(() => {
  sessionStorage.clear()
  heard.mockClear()
  window.addEventListener('unsettled-links-changed', heard)
})

afterEach(() => {
  window.removeEventListener('unsettled-links-changed', heard)
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

const reads = (calls: { method: string; path: string }[]) =>
  calls.filter((call) => call.method === 'GET' && call.path === '/unsettled-links').length

// ---- useUnsettledLinks ----

test('the list is read on mount, with the computing run, and the badge counts the rows not in a run', async () => {
  stubApi({ 'GET /unsettled-links': { body: { links: [link(1), link(2, { state: 'waiting', in_run: true })], run_id: 'r1' } } })
  const { result } = renderHook(() => useUnsettledLinks())
  expect(result.current).toEqual({ kind: 'loading' })
  await waitFor(() => expect(result.current.kind).toBe('ready'))
  expect(result.current).toMatchObject({ runId: 'r1' })
  expect(countOf(result.current)).toBe(1)
})

test('an unreadable file gives the unreadable state with the problem, and no count', async () => {
  stubApi({ 'GET /unsettled-links': { status: 503, body: { error: 'unsettled links unreadable', detail: 'unsettled-links.json: bad' } } })
  const { result } = renderHook(() => useUnsettledLinks())
  await waitFor(() => expect(result.current).toEqual({ kind: 'unreadable', detail: 'unsettled-links.json: bad' }))
  expect(countOf(result.current)).toBe(0)
})

test('any other failure is its own state, and a list already read stays when a re-read fails', async () => {
  let fail = true
  stubApi({ 'GET /unsettled-links': () => fail ? { status: 500, body: { error: 'boom' } } : { body: { links: [link(1)], run_id: null } } })
  const { result } = renderHook(() => useUnsettledLinks())
  await waitFor(() => expect(result.current).toEqual({ kind: 'failed' }))
  fail = false
  act(() => notifyUnsettledLinks())
  await waitFor(() => expect(result.current.kind).toBe('ready'))
  fail = true
  act(() => notifyUnsettledLinks())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
  expect(result.current.kind).toBe('ready')
})

test('the list is read again on the window event', async () => {
  const calls = stubApi({})
  renderHook(() => useUnsettledLinks())
  await waitFor(() => expect(reads(calls)).toBe(1))
  act(() => notifyUnsettledLinks())
  await waitFor(() => expect(reads(calls)).toBe(2))
})

test('while a run computes the list is read again every few seconds, so a run of another device ending frees the buttons; without a run it is not', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  let runId: string | null = 'other'
  const calls = stubApi({ 'GET /unsettled-links': () => ({
    body: { links: [link(1, runId ? { state: 'waiting', in_run: true } : {})], run_id: runId } }) })
  const { result } = renderHook(() => useUnsettledLinks())
  await act(async () => { await vi.advanceTimersByTimeAsync(0) })
  expect(result.current).toMatchObject({ runId: 'other' })
  expect(countOf(result.current)).toBe(0)
  await act(async () => { await vi.advanceTimersByTimeAsync(LIST_POLL_MS) })
  expect(reads(calls)).toBe(2)
  runId = null
  await act(async () => { await vi.advanceTimersByTimeAsync(LIST_POLL_MS) })
  expect(result.current).toMatchObject({ runId: null })
  expect(countOf(result.current)).toBe(1)
  await act(async () => { await vi.advanceTimersByTimeAsync(LIST_POLL_MS * 3) })
  expect(reads(calls)).toBe(3)
  expect(heard).not.toHaveBeenCalled()
})

test('the list is read again when the tab becomes the shown source, not while it stays shown', async () => {
  const calls = stubApi({})
  const { rerender } = renderHook(({ active }) => useUnsettledLinks(active), { initialProps: { active: false } })
  await waitFor(() => expect(reads(calls)).toBe(1))
  rerender({ active: true })
  await waitFor(() => expect(reads(calls)).toBe(2))
  rerender({ active: true })
  rerender({ active: false })
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
  expect(reads(calls)).toBe(2)
})

test('a tab shown from the start reads once, not twice', async () => {
  const calls = stubApi({})
  renderHook(() => useUnsettledLinks(true))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
  expect(reads(calls)).toBe(1)
})

// ---- useAlertRun notifies ----

test('a view without a run says nothing at mount', () => {
  stubApi({})
  renderHook(() => useAlertRun(store))
  expect(heard).not.toHaveBeenCalled()
})

test('a run notifies when it starts and when it attaches, and a refused start attaches to the computing run', async () => {
  stubApi({
    'POST /alert-mails/runs': { status: 202, body: { run_id: 'r1' } },
    'GET /alert-mails/runs/r1': { body: run(0) },
  })
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  const { result } = renderHook(() => useAlertRun(store))
  await act(async () => { await result.current.start([{ url: 'https://jobs.example.com/1', title: 'Stelle 1', force: false }]) })
  expect(heard).toHaveBeenCalledTimes(1)
  act(() => result.current.attach('r2'))
  expect(heard).toHaveBeenCalledTimes(2)
})

test('a start refused with 409 shows the computing run and notifies', async () => {
  stubApi({
    'POST /alert-mails/runs': { status: 409, body: { error: 'alert run in progress', detail: '', run_id: 'r9' } },
    'GET /alert-mails/runs/r9': { body: { ...run(0), run_id: 'r9' } },
  })
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  const { result } = renderHook(() => useAlertRun(store))
  await act(async () => { await result.current.start([{ url: 'https://jobs.example.com/1', title: 'Stelle 1', force: false }]) })
  expect(result.current.runId).toBe('r9')
  expect(heard).toHaveBeenCalledTimes(1)
})

test('a run notifies after each poll that shows more ended entries and once when it is no longer running', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  const answers = [run(0), run(1), run(1), run(3, 'done')]
  let polled = 0
  stubApi({ 'GET /alert-mails/runs/r1': () => ({ body: answers[Math.min(polled++, answers.length - 1)] }) })
  const { result } = renderHook(() => useAlertRun(store))
  act(() => result.current.attach('r1', [{ url: 'https://jobs.example.com/1', title: 'Stelle 1' }]))
  await act(async () => { await vi.advanceTimersByTimeAsync(0) }) // the poll at once: done 0
  expect(heard).toHaveBeenCalledTimes(1) // the attach only
  await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS) }) // done 1
  expect(heard).toHaveBeenCalledTimes(2)
  await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS) }) // done 1 again
  expect(heard).toHaveBeenCalledTimes(2)
  await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS) }) // done 3, ended: one notice for both reasons
  expect(heard).toHaveBeenCalledTimes(3)
  await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS * 3) })
  expect(heard).toHaveBeenCalledTimes(3)
})

test('a run kept across a reload notifies at its first poll', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem('jobadvaisor.test-run', 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: run(2) } })
  renderHook(() => useAlertRun(store))
  await act(async () => { await vi.advanceTimersByTimeAsync(0) })
  expect(heard).toHaveBeenCalledTimes(1)
})

test('a run the server forgot notifies, as the list then reads its links as not reached', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem('jobadvaisor.test-run', 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { status: 404, body: { error: 'not found' } } })
  const { result } = renderHook(() => useAlertRun(store))
  await act(async () => { await vi.advanceTimersByTimeAsync(0) })
  expect(result.current.gone).toBe(true)
  expect(heard).toHaveBeenCalledTimes(1)
})

test('a stored-anyway run of a mailbox run sends the source, any other start sends none', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  const calls = stubApi({
    'POST /alert-mails/runs': { status: 202, body: { run_id: 'r1' } },
    'GET /alert-mails/runs/r1': { body: run(0) },
  })
  const entries = [{ url: 'https://jobs.example.com/1', title: 'Stelle 1', force: true }]
  const mailbox = renderHook(() => useAlertRun(store, 'mailbox'))
  await act(async () => { await mailbox.result.current.start(entries, { index: 0, base: run(1).entries }) })
  expect(calls.find((call) => call.method === 'POST')!.body).toEqual({ entries, source: 'mailbox' })
  mailbox.unmount()
  sessionStorage.clear()
  calls.length = 0
  const paste = renderHook(() => useAlertRun(store))
  await act(async () => { await paste.result.current.start(entries) })
  expect(calls.find((call) => call.method === 'POST')!.body).toEqual({ entries })
})
