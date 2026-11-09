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
type Answer = { body: { version: string } } | typeof FAILED

/** Serves `/version` with the given answers in order, the last one for every later request;
 * returns the number of `/version` requests so far. */
function serve(...answers: Answer[]) {
  let requests = 0
  stubApi({ 'GET /pool': { body: POOL },
            'GET /version': () => answers[Math.min(requests++, answers.length - 1)] })
  return () => requests
}

const ok = (version: string): Answer => ({ body: { version } })

/** The tab becoming visible (or hidden) again, as a browser reports it. */
async function tab(state: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true })
  await act(async () => { document.dispatchEvent(new Event('visibilitychange')) })
}

const footer = () => screen.getByRole('contentinfo')
const banner = () => screen.queryByText(/Diese Seite ist veraltet/)

test('a local build shows dev for both sides and the origin of the page', async () => {
  serve(ok('dev'))
  render(<App />)
  await screen.findByText(/Server dev/)
  expect(footer()).toHaveTextContent(`Oberfläche dev · Server dev · ${window.location.origin}`)
  expect(banner()).toBeNull()
})

test('a release shows its tag for both sides and no banner', async () => {
  vi.stubEnv('VITE_APP_VERSION', 'v0.1.0')
  serve(ok('v0.1.0'))
  render(<App />)
  expect(await screen.findByText(/Server v0\.1\.0/)).toBeVisible()
  expect(footer()).toHaveTextContent('Oberfläche v0.1.0')
  expect(banner()).toBeNull()
})

test('an unreachable backend on load shows an unknown server version and no banner', async () => {
  vi.stubEnv('VITE_APP_VERSION', 'v0.1.0')
  const requests = serve(FAILED)
  render(<App />)
  await vi.waitFor(() => expect(requests()).toBe(1))
  expect(footer()).toHaveTextContent('Server unbekannt')
  expect(banner()).toBeNull()
})

test('a different backend version shows the banner with both versions and a reload button', async () => {
  vi.stubEnv('VITE_APP_VERSION', 'v0.1.0')
  serve(ok('v0.2.0'))
  render(<App />)
  expect(await screen.findByText(/Diese Seite ist veraltet/)).toHaveTextContent('v0.1.0')
  expect(banner()).toHaveTextContent('v0.2.0')
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
  await screen.findByText(/Server v0\.1\.0/)
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
  await screen.findByText(/Server v0\.1\.0/)
  await tab('visible')
  await vi.waitFor(() => expect(requests()).toBe(2))
  expect(footer()).toHaveTextContent('Server v0.1.0')
  expect(banner()).toBeNull()
})

test('a failed refetch leaves the banner in place', async () => {
  vi.stubEnv('VITE_APP_VERSION', 'v0.1.0')
  const requests = serve(ok('v0.2.0'), FAILED)
  render(<App />)
  await screen.findByText(/Diese Seite ist veraltet/)
  await tab('visible')
  await vi.waitFor(() => expect(requests()).toBe(2))
  expect(banner()).toBeVisible()
  expect(footer()).toHaveTextContent('Server v0.2.0')
})

test('the banner goes when a refetch returns the frontend version again', async () => {
  vi.stubEnv('VITE_APP_VERSION', 'v0.1.0')
  serve(ok('v0.2.0'), ok('v0.1.0'))
  render(<App />)
  await screen.findByText(/Diese Seite ist veraltet/)
  await tab('visible')
  await vi.waitFor(() => expect(banner()).toBeNull())
  expect(footer()).toHaveTextContent('Server v0.1.0')
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
