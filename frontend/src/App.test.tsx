import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import { stubApi } from '@/test-api'
import { POOL } from '@/test-fixtures'
import { axe } from '@/test-axe'
import App from './App.tsx'

afterEach(() => {
  window.location.hash = ''
  vi.unstubAllGlobals()
})

function nav() {
  return within(screen.getByRole('navigation', { name: 'Hauptnavigation' }))
}

test('opens on the pool view', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<App />)
  expect(screen.getByRole('heading', { level: 1, name: 'Deine Anzeigen' })).toBeVisible()
  expect(nav().getByRole('link', { name: 'Anzeigen' })).toHaveAttribute('aria-current', 'page')
  expect(await screen.findByRole('list', { name: 'Anzeigen' })).toBeVisible()
})

test('an unknown or old hash falls back to the pool', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  window.location.hash = '#/bewerten'
  render(<App />)
  expect(screen.getByRole('heading', { level: 1, name: 'Deine Anzeigen' })).toBeVisible()
  expect(nav().getByRole('link', { name: 'Anzeigen' })).toHaveAttribute('aria-current', 'page')
  await screen.findByRole('list', { name: 'Anzeigen' })
})

test('the navigation switches between the views', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<App />)
  await userEvent.click(nav().getByRole('link', { name: 'Anzeige hinzufügen' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Anzeige hinzufügen' })).toBeVisible()
  expect(nav().getByRole('link', { name: 'Anzeige hinzufügen' }))
    .toHaveAttribute('aria-current', 'page')
  await userEvent.click(nav().getByRole('link', { name: 'Fragen' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Fragen zu deinen Anzeigen' }))
    .toBeVisible()
  expect(nav().getByRole('link', { name: 'Anzeigen' })).not.toHaveAttribute('aria-current')
})

test('the import is the source "Liste" of "Anzeige hinzufügen", and the pool reloads when it is opened again', async () => {
  let loads = 0
  stubApi({ 'GET /pool': () => {
    loads += 1
    return { body: POOL }
  }, 'GET /policy-pack/login-wall-hosts': { body: { hosts: [] } } })
  render(<App />)
  await screen.findByRole('list', { name: 'Anzeigen' })
  expect(nav().queryByRole('link', { name: 'Liste importieren' })).toBeNull()
  await userEvent.click(nav().getByRole('link', { name: 'Anzeige hinzufügen' }))
  const sources = screen.getByRole('group', { name: 'Quelle der Anzeige' })
  await userEvent.click(within(sources).getByRole('button', { name: 'Liste' }))
  expect(window.location.hash).toBe('#/importieren')
  expect(within(sources).getByRole('button', { name: 'Liste' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByLabelText('Liste als Markdown-Datei')).toBeVisible()
  expect(screen.queryByLabelText('Link zur Anzeige')).not.toBeVisible()
  expect(nav().getByRole('link', { name: 'Anzeige hinzufügen' })).toHaveAttribute('aria-current', 'page')
  await userEvent.click(within(sources).getByRole('button', { name: 'PDF' }))
  expect(window.location.hash).toBe('#/hinzufuegen')
  expect(screen.getByLabelText('Anzeige als PDF')).toBeVisible()
  expect(loads).toBe(1)
  await userEvent.click(nav().getByRole('link', { name: 'Anzeigen' }))
  await vi.waitFor(() => expect(loads).toBe(2))
})

test('a reload keeps the open view', () => {
  window.location.hash = '#/fragen'
  render(<App />)
  expect(screen.getByRole('heading', { level: 1, name: 'Fragen zu deinen Anzeigen' })).toBeVisible()
})

test('a posting route shows the page with the decoded ID and keeps Anzeigen current', async () => {
  stubApi({ 'GET /pool': { body: POOL },
            'GET /postings/a%20b%2Fc': { status: 404, body: { error: 'not found', detail: '' } } })
  window.location.hash = '#/anzeigen/a%20b%2Fc'
  render(<App />)
  expect(await screen.findByText('Diese Anzeige gibt es nicht (mehr).')).toBeVisible()
  expect(nav().getByRole('link', { name: 'Anzeigen' })).toHaveAttribute('aria-current', 'page')
  expect(screen.queryByRole('heading', { level: 1, name: 'Deine Anzeigen' })).toBeNull()
  await userEvent.click(screen.getByRole('link', { name: 'Zurück zur Liste' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Deine Anzeigen' })).toBeVisible()
  expect(screen.queryByText('Diese Anzeige gibt es nicht (mehr).')).toBeNull()
})

test('switching views keeps the conversation', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'GET /policy-pack/login-wall-hosts': { body: { hosts: [] } },
            'POST /agent/messages': { body: { reply: 'Regel no-on-call.', tool_calls: [] } } })
  window.location.hash = '#/fragen'
  render(<App />)
  await userEvent.type(screen.getByLabelText('Deine Frage'), 'Warum?{Enter}')
  await screen.findByText('Regel no-on-call.')
  await userEvent.click(nav().getByRole('link', { name: 'Anzeigen' }))
  await screen.findByRole('list', { name: 'Anzeigen' })
  await userEvent.click(nav().getByRole('link', { name: 'Fragen' }))
  expect(await screen.findByText('Regel no-on-call.')).toBeVisible()
})

test('the shell has no accessibility violations', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  const { container } = render(<App />)
  await screen.findByRole('list', { name: 'Anzeigen' })
  expect(await axe(container)).toHaveNoViolations()
})

test('an intake result and the posting page editor can be open at once, each label reaching its own field', async () => {
  const posting = { title: 'Data Analyst (m/w/d)', company: 'Grünwerk Solar', location_raw: 'Kiel',
    source_type: 'url', urls: ['https://jobs.example.com/1'], text: 'Wir suchen …' }
  const other = { ...posting, title: 'Berater (m/w/d)' }
  stubApi({ 'GET /pool': { body: POOL },
            'GET /policy-pack/login-wall-hosts': { body: { hosts: [] } },
            'POST /postings': { status: 201, body: { posting_id: 'p-1', posting, duplicate: false,
                                                      duplicate_by: null, attempts: [], screening: true } },
            'GET /postings/p2': { body: { row: POOL.rows[1], posting: other, score: null, examples: [],
                                          reason_chips: POOL.reason_chips } } })
  window.location.hash = '#/hinzufuegen'
  const { container } = render(<App />)
  await userEvent.type(screen.getByLabelText('Link zur Anzeige'), 'https://jobs.example.com/1')
  await userEvent.click(screen.getByRole('button', { name: 'Hinzufügen' }))
  await screen.findByRole('heading', { name: 'Anzeige hinzugefügt' })
  window.location.hash = '#/anzeigen/p2'
  await userEvent.click(await screen.findByRole('button', { name: 'Bearbeiten' }))
  const titles = screen.getAllByLabelText('Titel')
  expect(titles.map((field) => (field as HTMLInputElement).value))
    .toEqual(['Data Analyst (m/w/d)', 'Berater (m/w/d)'])
  const ids = Array.from(container.querySelectorAll('[id]'), (element) => element.id)
  expect(new Set(ids).size).toBe(ids.length)
  expect(await axe(container)).toHaveNoViolations()
})

// Contrast in both themes is checked on the tokens (contrast.test.ts), since jsdom applies no
// stylesheet; this pass covers structure, names and roles of every view inside the shell.
test.each([['#/pool', 'Deine Anzeigen'], ['#/hinzufuegen', 'Anzeige hinzufügen'],
           ['#/importieren', 'Anzeige hinzufügen'], ['#/fragen', 'Fragen zu deinen Anzeigen']])('view %s has no accessibility violations',
  async (hash, title) => {
    stubApi({ 'GET /pool': { body: POOL },
              'GET /policy-pack/login-wall-hosts': { body: { hosts: ['linkedin.com'] } } })
    window.location.hash = hash
    const { container } = render(<App />)
    await screen.findByRole('heading', { level: 1, name: title })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(await axe(container)).toHaveNoViolations()
  })
