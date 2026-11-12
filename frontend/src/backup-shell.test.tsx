import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import type { BackupStatus } from '@/lib/backup'
import { stubApi } from '@/test-api'
import { axe } from '@/test-axe'
import { POOL } from '@/test-fixtures'
import App from './App.tsx'

afterEach(() => {
  vi.unstubAllGlobals()
  window.location.hash = ''
})

const QUIET: BackupStatus = {
  pending: false, uncommitted: 0, unpushed: 0, branch: 'main', remote: 'origin/main',
  operation: null, running: false, progress: null, last_result: null,
  last_success: '2026-11-12T09:12:00Z', last_failure: null,
}
const PENDING: BackupStatus = { ...QUIET, pending: true, uncommitted: 3 }

test('the backup button is in the header of every view', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'GET /backup': { body: PENDING } })
  render(<App />)
  for (const hash of ['#/pool', '#/hinzufuegen', '#/fragen']) {
    await act(async () => { window.location.hash = hash })
    expect(await screen.findByRole('button', { name: 'Sichern (3)' })).toBeVisible()
  }
})

test('the button is quiet when nothing is pending and highlighted when something is', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'GET /backup': { body: QUIET } })
  const { unmount } = render(<App />)
  expect(await screen.findByRole('button', { name: 'Gesichert – jetzt erneut sichern' }))
    .toHaveAttribute('data-variant', 'outline')
  unmount()
  stubApi({ 'GET /pool': { body: POOL }, 'GET /backup': { body: PENDING } })
  render(<App />)
  expect(await screen.findByRole('button', { name: 'Sichern (3)' })).toHaveAttribute('data-variant', 'default')
})

test('pressing the button starts a backup and shows its progress strip under the header', async () => {
  const running: BackupStatus = {
    ...PENDING, running: true, progress: { step: 'pushing', files: 40, percent: 60 } }
  let current = PENDING
  const calls = stubApi({
    'GET /pool': { body: POOL },
    'GET /backup': () => ({ body: current }),
    'POST /backup': () => { current = running; return { status: 202, body: { status: running } } },
  })
  render(<App />)
  await userEvent.click(await screen.findByRole('button', { name: 'Sichern (3)' }))
  const strip = await screen.findByRole('status', { name: 'Fortschritt der Sicherung' })
  expect(strip).toHaveTextContent('Schritt 3 von 3: Pushen zum Remote')
  expect(strip).toHaveTextContent('40 Dateien · 60 %')
  expect(calls.some((call) => call.method === 'POST' && call.path === '/backup')).toBe(true)
  expect(screen.getByRole('banner').compareDocumentPosition(strip)
    & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})

test('an unavailable backup disables the button and the app keeps working', async () => {
  stubApi({
    'GET /pool': { body: POOL },
    'GET /backup': { status: 409, body: { error: 'backup unavailable', detail: '/d is not a git repository' } },
  })
  render(<App />)
  expect(await screen.findByRole('button', { name: 'Sichern' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Warum ist Sichern nicht möglich?' })).toBeVisible()
  expect(await screen.findByText('Data Analyst (m/w/d)')).toBeVisible()
})

test('a failed status fetch leaves the app and its header usable', async () => {
  stubApi({
    'GET /pool': { body: POOL },
    'GET /backup': { status: 500, body: { error: 'internal error', detail: '' } },
  })
  render(<App />)
  expect(await screen.findByText('Data Analyst (m/w/d)')).toBeVisible()
  expect(screen.queryByRole('button', { name: /Sichern|Gesichert/ })).toBeNull()
})

test('the header with the backup control has no accessibility violations', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'GET /backup': { body: PENDING } })
  const { container } = render(<App />)
  await screen.findByRole('button', { name: 'Sichern (3)' })
  expect(await axe(container)).toHaveNoViolations()
})
