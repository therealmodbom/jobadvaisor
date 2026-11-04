import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import { axe } from '@/test-axe'
import { pending, stubApi } from '@/test-api'
import { IntakeView } from './IntakeView'

const URL = 'https://jobs.example.com/postings/48213'
const HOSTS = { 'GET /policy-pack/login-wall-hosts': { body: { hosts: ['linkedin.com', 'xing.com'] } } }
const POSTING = {
  title: 'Data Analyst (m/w/d)', company: 'Grünwerk Solar', location_raw: 'Kiel',
  source_type: 'url', urls: [URL], text: 'Wir suchen …',
}

function stored(posting: object = {}, screening = true) {
  return { status: 201, body: { posting_id: 'p-1', posting: { ...POSTING, ...posting },
                                duplicate: false, duplicate_by: null, attempts: [], screening } }
}

async function submitUrl() {
  await userEvent.type(screen.getByLabelText('Link zur Anzeige'), URL)
  await userEvent.click(screen.getByRole('button', { name: 'Hinzufügen' }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

test('a running intake shows progress and takes no second submission', async () => {
  const calls = stubApi({ ...HOSTS, 'POST /postings': pending })
  render(<IntakeView />)
  await submitUrl()
  expect(screen.getByRole('status')).toHaveTextContent('Anzeige wird hinzugefügt')
  const button = screen.getByRole('button', { name: 'Wird hinzugefügt…' })
  expect(button).toBeDisabled()
  await userEvent.click(button)
  expect(calls.filter((call) => call.method === 'POST')).toHaveLength(1)
  expect(calls.at(-1)!.body).toEqual({ url: URL })
})

test('a failed link lists the attempts and offers text and PDF', async () => {
  stubApi({ ...HOSTS, 'POST /postings': { status: 422, body: {
    error: 'posting not found', detail: 'no attempt yielded the posting',
    attempts: [{ step: 'plain', url: URL, outcome: 'login form' },
               { step: 'rendered', url: URL, outcome: 'login form' }] } } })
  render(<IntakeView />)
  await submitUrl()
  const alert = await screen.findByRole('alert')
  expect(within(alert).getByText(/Einfacher Abruf/)).toBeVisible()
  expect(within(alert).getByText(/Abruf im Browser/)).toBeVisible()
  await userEvent.click(within(alert).getByRole('button', { name: 'Text einfügen' }))
  expect(screen.getByLabelText('Anzeigentext')).toBeVisible()
})

const URL_B = 'https://jobs.example.com/postings/dead'
const URL_C = 'https://jobs.example.com/postings/50001'
const BATCH = { 'POST /postings/batch': { body: { results: [
  { url: URL, outcome: 'stored', posting_id: 'p-1' },
  { url: URL_B, outcome: 'failed', detail: 'no attempt yielded the posting',
    attempts: [{ step: 'plain', url: URL_B, outcome: 'http 404' },
               { step: 'rendered', url: URL_B, outcome: 'http 404' }] },
  { url: URL_C, outcome: 'duplicate', posting_id: 'p-2' },
] } } }

async function submitLines(...lines: string[]) {
  await userEvent.type(screen.getByLabelText('Link zur Anzeige'), lines.join('{Enter}'))
  await userEvent.click(screen.getByRole('button', { name: 'Hinzufügen' }))
}

test('several links go out in one batch, one per line, blank lines dropped', async () => {
  const calls = stubApi({ ...HOSTS, ...BATCH })
  render(<IntakeView />)
  await submitLines(` ${URL} `, '', URL_B, URL_C)
  await screen.findByRole('list', { name: 'Ergebnis je Link' })
  expect(calls.filter((call) => call.method === 'POST')).toEqual([
    { method: 'POST', path: '/postings/batch', body: { urls: [URL, URL_B, URL_C] } }])
})

test('each link shows its outcome, and a failed one the attempts with the text and PDF options', async () => {
  stubApi({ ...HOSTS, ...BATCH })
  render(<IntakeView />)
  await submitLines(URL, URL_B, URL_C)
  const list = await screen.findByRole('list', { name: 'Ergebnis je Link' })
  const items = within(list).getAllByRole('listitem').filter((item) => item.parentElement === list)
  expect(items).toHaveLength(3)
  expect(within(items[0]).getByText('Hinzugefügt')).toBeVisible()
  expect(within(items[0]).getByRole('link', { name: 'Anzeige ansehen' }))
    .toHaveAttribute('href', '#/anzeigen/p-1')
  expect(within(items[1]).getByText('Nicht gelesen')).toBeVisible()
  expect(within(items[1]).getByText(/Einfacher Abruf/)).toBeVisible()
  expect(within(items[1]).getByText(/Abruf im Browser/)).toBeVisible()
  expect(within(items[2]).getByText('Schon gespeichert')).toBeVisible()
  await userEvent.click(within(items[1]).getByRole('button', { name: 'Text einfügen' }))
  expect(screen.getByLabelText('Anzeigentext')).toBeVisible()
})

test('a running batch shows progress and takes no second submission', async () => {
  const calls = stubApi({ ...HOSTS, 'POST /postings/batch': pending })
  render(<IntakeView />)
  await submitLines(URL, URL_B)
  expect(screen.getByRole('status')).toHaveTextContent('Anzeige wird hinzugefügt')
  await userEvent.click(screen.getByRole('button', { name: 'Wird hinzugefügt…' }))
  expect(calls.filter((call) => call.method === 'POST')).toHaveLength(1)
})

test('a failed batch request keeps the typed links and offers a retry', async () => {
  stubApi({ ...HOSTS, 'POST /postings/batch': { status: 500, body: { error: 'internal error' } } })
  render(<IntakeView />)
  await submitLines(URL, URL_B)
  expect(await screen.findByRole('alert')).toHaveTextContent('Anzeige konnte nicht hinzugefügt werden')
  expect(screen.getByLabelText('Link zur Anzeige')).toHaveValue(`${URL}\n${URL_B}`)
  expect(screen.getByRole('button', { name: 'Erneut versuchen' })).toBeVisible()
})

test('a corrected field is saved through PATCH', async () => {
  const calls = stubApi({ ...HOSTS, 'POST /postings': stored(),
    'PATCH /postings/p-1': ({ body }) => ({ body: { posting_id: 'p-1',
                                                    posting: { ...POSTING, ...(body as object) } } }) })
  render(<IntakeView />)
  await submitUrl()
  const company = await screen.findByLabelText('Firma')
  expect(company).toHaveValue('Grünwerk Solar')
  await userEvent.clear(company)
  await userEvent.type(company, 'Grünwerk Solar GmbH')
  await userEvent.click(screen.getByRole('button', { name: 'Korrekturen speichern' }))
  expect(await screen.findByText('Korrekturen gespeichert')).toBeVisible()
  expect(calls.at(-1)).toEqual({ method: 'PATCH', path: '/postings/p-1',
                                 body: { company: 'Grünwerk Solar GmbH' } })
})

test('an emptied field is not reported as saved', async () => {
  const calls = stubApi({ ...HOSTS, 'POST /postings': stored() })
  render(<IntakeView />)
  await submitUrl()
  await userEvent.clear(await screen.findByLabelText('Firma'))
  await userEvent.click(screen.getByRole('button', { name: 'Korrekturen speichern' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Titel, Firma und Ort dürfen nicht leer sein')
  expect(screen.queryByText('Korrekturen gespeichert')).toBeNull()
  expect(calls.filter((call) => call.method === 'PATCH')).toEqual([])
})

test('a flagged posting names its categories and can be released', async () => {
  const guard = { flagged: true, categories: ['instructions_for_ai'], checked_by: 'mistral',
                  checked_at: '2026-10-12T10:00:00Z' }
  const calls = stubApi({ ...HOSTS, 'POST /postings': stored({ guard }),
    'PATCH /postings/p-1': { body: { posting_id: 'p-1', posting: { ...POSTING,
      guard: { ...guard, released_at: '2026-10-12T10:01:00Z' } } } } })
  render(<IntakeView />)
  await submitUrl()
  expect(await screen.findByText(/Anweisungen an eine KI/)).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Anzeige freigeben' }))
  expect(await screen.findByText(/Freigegeben/)).toBeVisible()
  expect(calls.at(-1)).toEqual({ method: 'PATCH', path: '/postings/p-1', body: { release: true } })
})

test('screening off is said plainly', async () => {
  stubApi({ ...HOSTS, 'POST /postings': stored({}, false) })
  render(<IntakeView />)
  await submitUrl()
  expect(await screen.findByText(/Inhaltsprüfung ist aus/)).toBeVisible()
})

test('the login-walled host list is edited and saved', async () => {
  const calls = stubApi({ ...HOSTS,
    'PUT /policy-pack/login-wall-hosts': ({ body }) => ({ body }) })
  render(<IntakeView />)
  const list = await screen.findByRole('list', { name: 'Seiten mit Login-Pflicht' })
  expect(within(list).getByText('xing.com')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'xing.com entfernen' }))
  await userEvent.type(screen.getByLabelText('Neue Seite'), ' https://WWW.Jobs.Example.com/x ')
  await userEvent.click(screen.getByRole('button', { name: 'Seite hinzufügen' }))
  expect(screen.getByText('Ungespeicherte Änderungen')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Liste speichern' }))
  expect(await screen.findByText(/Gespeichert. Der nächste Link nutzt diese Liste./)).toBeVisible()
  expect(calls.at(-1)).toEqual({ method: 'PUT', path: '/policy-pack/login-wall-hosts',
                                 body: { hosts: ['linkedin.com', 'jobs.example.com'] } })
})

test('the batch results have no accessibility violations', async () => {
  stubApi({ ...HOSTS, ...BATCH })
  const { container } = render(<IntakeView />)
  await submitLines(URL, URL_B, URL_C)
  await screen.findByRole('list', { name: 'Ergebnis je Link' })
  expect(await axe(container)).toHaveNoViolations()
})

test('the intake view has no accessibility violations', async () => {
  stubApi({ ...HOSTS, 'POST /postings': stored() })
  const { container } = render(<IntakeView />)
  await submitUrl()
  await screen.findByLabelText('Firma')
  expect(await axe(container)).toHaveNoViolations()
})
