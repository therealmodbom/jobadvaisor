import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import { stubApi } from '@/test-api'
import { axe } from '@/test-axe'
import { POOL } from '@/test-fixtures'
import App from './App.tsx'

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  delete (document as { visibilityState?: unknown }).visibilityState
  window.location.hash = ''
})

const FAILED = { status: 500, body: { error: 'internal error', detail: '' } }
type Answer = { status?: number; body: unknown }

/** Serves `/health` with the given answers in order, the last one for every later request;
 * returns the number of `/health` requests so far. */
function serve(...answers: Answer[]) {
  let requests = 0
  stubApi({ 'GET /pool': { body: POOL },
            'GET /health': () => answers[Math.min(requests++, answers.length - 1)] })
  return () => requests
}

/** A healthy answer of a backend running `version`. */
const ok = (version: string): Answer =>
  ({ body: { status: 'ok', checks: { data_repo: 'ok' }, version } })

/** The answer of a backend whose data repository does not load: a 503 that still names its
 * `version`. */
const failing = (version: string): Answer =>
  ({ status: 503, body: { status: 'fail', checks: { data_repo: 'pool.json: invalid' }, version } })

/** The tab becoming visible (or hidden) again, as a browser reports it. */
async function tab(state: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true })
  await act(async () => { document.dispatchEvent(new Event('visibilitychange')) })
}

/** Lets a finished request's state update land, so an assertion that nothing changed is not
 * made before the change could have happened. */
const settle = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })

const footer = () => screen.getByRole('contentinfo')
const banner = () => screen.queryByText(/Diese Seite ist veraltet/)

test('a local build shows dev for both sides and the origin of the page', async () => {
  serve(ok('dev'))
  render(<App />)
  await screen.findByText(/Backend dev/)
  expect(footer()).toHaveTextContent(`Frontend dev · Backend dev · ${window.location.origin}`)
  expect(banner()).toBeNull()
})

test('a release shows its tag for both sides and no banner', async () => {
  vi.stubEnv('VITE_APP_VERSION', 'v0.1.0')
  serve(ok('v0.1.0'))
  render(<App />)
  expect(await screen.findByText(/Backend v0\.1\.0/)).toBeVisible()
  expect(footer()).toHaveTextContent('Frontend v0.1.0')
  expect(banner()).toBeNull()
})

test('an unreachable backend on load shows an unknown server version and no banner', async () => {
  vi.stubEnv('VITE_APP_VERSION', 'v0.1.0')
  const requests = serve(FAILED)
  render(<App />)
  await vi.waitFor(() => expect(requests()).toBe(1))
  await settle()
  expect(footer()).toHaveTextContent('Backend unbekannt')
  expect(banner()).toBeNull()
})

test('a different backend version shows the banner with both versions and a reload button', async () => {
  vi.stubEnv('VITE_APP_VERSION', 'v0.1.0')
  serve(ok('v0.2.0'))
  render(<App />)
  expect(await screen.findByText(/Diese Seite ist veraltet/)).toHaveTextContent(
    'Diese Seite ist veraltet: Sie läuft mit v0.1.0, das Backend mit v0.2.0.')
  expect(screen.getByRole('button', { name: 'Neu laden' })).toBeVisible()
})

test('the reload button reloads the page', async () => {
  vi.stubEnv('VITE_APP_VERSION', 'v0.1.0')
  serve(ok('v0.2.0'))
  const reload = vi.fn()
  vi.stubGlobal('location', { ...window.location, reload })
  render(<App />)
  await userEvent.click(await screen.findByRole('button', { name: 'Neu laden' }))
  expect(reload).toHaveBeenCalledOnce()
})

test('the version is fetched again when the tab becomes visible, not when it is hidden', async () => {
  vi.stubEnv('VITE_APP_VERSION', 'v0.1.0')
  const requests = serve(ok('v0.1.0'), ok('v0.2.0'))
  render(<App />)
  await screen.findByText(/Backend v0\.1\.0/)
  await tab('hidden')
  expect(requests()).toBe(1)
  await tab('visible')
  expect(await screen.findByText(/Diese Seite ist veraltet/)).toBeVisible()
  expect(requests()).toBe(2)
})

test('a failed refetch keeps the last backend version', async () => {
  vi.stubEnv('VITE_APP_VERSION', 'v0.1.0')
  const requests = serve(ok('v0.1.0'), FAILED)
  render(<App />)
  await screen.findByText(/Backend v0\.1\.0/)
  await tab('visible')
  await vi.waitFor(() => expect(requests()).toBe(2))
  await settle()
  expect(footer()).toHaveTextContent('Backend v0.1.0')
  expect(banner()).toBeNull()
})

test('a failed refetch leaves the banner in place', async () => {
  vi.stubEnv('VITE_APP_VERSION', 'v0.1.0')
  const requests = serve(ok('v0.2.0'), FAILED)
  render(<App />)
  await screen.findByText(/Diese Seite ist veraltet/)
  await tab('visible')
  await vi.waitFor(() => expect(requests()).toBe(2))
  await settle()
  expect(banner()).toBeVisible()
  expect(footer()).toHaveTextContent('Backend v0.2.0')
})

test('the banner goes when a refetch returns the frontend version again', async () => {
  vi.stubEnv('VITE_APP_VERSION', 'v0.1.0')
  serve(ok('v0.2.0'), ok('v0.1.0'))
  render(<App />)
  await screen.findByText(/Diese Seite ist veraltet/)
  await tab('visible')
  await vi.waitFor(() => expect(banner()).toBeNull())
  expect(footer()).toHaveTextContent('Backend v0.1.0')
})

test('the banner does not drop what a view holds', async () => {
  vi.stubEnv('VITE_APP_VERSION', 'v0.1.0')
  serve(ok('v0.1.0'), ok('v0.2.0'))
  window.location.hash = '#/fragen'
  render(<App />)
  const question = screen.getByLabelText('Deine Frage')
  await userEvent.type(question, 'Warum?')
  await tab('visible')
  await screen.findByText(/Diese Seite ist veraltet/)
  expect(screen.getByLabelText('Deine Frage')).toHaveValue('Warum?')
})

test('the shell with the banner and the footer has no accessibility violations', async () => {
  vi.stubEnv('VITE_APP_VERSION', 'v0.1.0')
  serve(ok('v0.2.0'))
  const { container } = render(<App />)
  await screen.findByText(/Diese Seite ist veraltet/)
  expect(await axe(container)).toHaveNoViolations()
})

test('a failing check still shows the backend version, and no status', async () => {
  vi.stubEnv('VITE_APP_VERSION', 'v0.1.0')
  serve(failing('v0.1.0'))
  render(<App />)
  await screen.findByText(/Backend v0\.1\.0/)
  expect(footer()).not.toHaveTextContent(/fail|pool\.json/)
  expect(banner()).toBeNull()
})

test('a failing check with a different version shows the banner', async () => {
  vi.stubEnv('VITE_APP_VERSION', 'v0.1.0')
  serve(failing('v0.2.0'))
  render(<App />)
  expect(await screen.findByText(/Diese Seite ist veraltet/)).toHaveTextContent('v0.2.0')
})

test('a failing check removes the banner when its version equals the frontend version', async () => {
  vi.stubEnv('VITE_APP_VERSION', 'v0.1.0')
  serve(ok('v0.2.0'), failing('v0.1.0'))
  render(<App />)
  await screen.findByText(/Diese Seite ist veraltet/)
  await tab('visible')
  await vi.waitFor(() => expect(banner()).toBeNull())
  expect(footer()).toHaveTextContent('Backend v0.1.0')
})

test('a 503 without a version counts as a failed fetch', async () => {
  vi.stubEnv('VITE_APP_VERSION', 'v0.1.0')
  const requests = serve({ status: 503, body: { error: 'unavailable', detail: '' } })
  render(<App />)
  await vi.waitFor(() => expect(requests()).toBe(1))
  await settle()
  expect(footer()).toHaveTextContent('Backend unbekannt')
  expect(banner()).toBeNull()
})

test('an answer without a version counts as a failed fetch', async () => {
  vi.stubEnv('VITE_APP_VERSION', 'v0.1.0')
  const requests = serve({ body: {} })
  render(<App />)
  await vi.waitFor(() => expect(requests()).toBe(1))
  await settle()
  expect(footer()).toHaveTextContent('Backend unbekannt')
  expect(banner()).toBeNull()
})
