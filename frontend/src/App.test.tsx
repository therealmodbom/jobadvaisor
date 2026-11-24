import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import { stubApi } from '@/test-api'
import { NO_MAILBOX, POOL } from '@/test-fixtures'
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

test('deleting a posting from its page returns to a pool that no longer lists it', async () => {
  let deleted = false
  stubApi({
    'GET /pool': () => ({ body: { ...POOL, rows: POOL.rows.filter((entry) => !(deleted && entry.posting_id === 'p1')) } }),
    'GET /postings/p1': { body: { row: POOL.rows[0], posting: { title: 'Data Analyst (m/w/d)', company: 'Grünwerk Solar', location_raw: 'Kiel',
      source_type: 'url', urls: [], text: 'Text' }, score: null, examples: [], checkable: true,
      reason_chips: POOL.reason_chips, screening: true, delete_blocked: null } },
    'DELETE /postings/p1': () => { deleted = true; return { status: 204 } },
  })
  render(<App />)
  await userEvent.click(await screen.findByRole('link', { name: 'Data Analyst (m/w/d)' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Anzeige löschen' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Endgültig löschen' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Deine Anzeigen' })).toBeVisible()
  expect(window.location.hash).toBe('#/pool')
  await vi.waitFor(() => expect(screen.queryByRole('heading', { level: 3, name: 'Data Analyst (m/w/d)' })).toBeNull())
  expect(screen.getByRole('heading', { level: 3, name: 'Data Engineer (m/w/d)' })).toBeVisible()
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


test('the header offers "Einstellungen" as a link after the backup control, from every view', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'GET /policy-pack/login-wall-hosts': { body: { hosts: [] } } })
  window.location.hash = '#/hinzufuegen'
  render(<App />)
  const header = screen.getByRole('banner')
  const backup = await within(header).findByRole('button', { name: /Gesichert/ })
  const settings = within(header).getByRole('link', { name: 'Einstellungen' })
  expect(backup.compareDocumentPosition(settings) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(settings).not.toHaveAttribute('aria-current')
})

test('the gear opens the settings page, marks itself current and leaves no navigation item current', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'GET /policy-pack/login-wall-hosts': { body: { hosts: [] } } })
  window.location.hash = '#/hinzufuegen'
  render(<App />)
  await userEvent.click(screen.getByRole('link', { name: 'Einstellungen' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Einstellungen' })).toBeVisible()
  expect(screen.getByRole('link', { name: 'Einstellungen' })).toHaveAttribute('aria-current', 'page')
  expect(nav().queryByRole('link', { current: 'page' })).toBeNull()
  expect(document.title).toBe('Einstellungen – JobAdvAIsor')
  expect(screen.queryByRole('heading', { level: 1, name: 'Anzeige hinzufügen' })).toBeNull()
})

test('the sections are listed on the page, "Scoren" is the default and each has its address', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'GET /mailbox': { body: NO_MAILBOX } })
  window.location.hash = '#/einstellungen'
  render(<App />)
  const sections = within(screen.getByRole('navigation', { name: 'Bereiche der Einstellungen' }))
  expect(sections.getByRole('link', { name: 'Scoren' })).toHaveAttribute('aria-current', 'page')
  expect(sections.getByRole('link', { name: 'Scoren' })).toHaveAttribute('href', '#/einstellungen/scoren')
  expect(sections.getByRole('link', { name: 'Postfach' })).toHaveAttribute('href', '#/einstellungen/postfach')
  expect(await screen.findByLabelText('Korrekturen bis zum Hinweis')).toBeVisible()
  await userEvent.click(sections.getByRole('link', { name: 'Postfach' }))
  expect(await screen.findByRole('heading', { level: 2, name: 'Postfach' })).toBeVisible()
  expect(sections.getByRole('link', { name: 'Postfach' })).toHaveAttribute('aria-current', 'page')
  expect(screen.queryByLabelText('Korrekturen bis zum Hinweis')).toBeNull()
})

test('the address of the section "Postfach" opens that section', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'GET /mailbox': { body: NO_MAILBOX } })
  window.location.hash = '#/einstellungen/postfach'
  render(<App />)
  expect(await screen.findByRole('heading', { level: 2, name: 'Postfach' })).toBeVisible()
  expect(screen.getByRole('link', { name: 'Postfach' })).toHaveAttribute('aria-current', 'page')
  expect(await screen.findByLabelText('Server')).toBeVisible()
})

test('an unknown section falls back to "Scoren"', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  window.location.hash = '#/einstellungen/gibtsnicht'
  render(<App />)
  expect(await screen.findByLabelText('Korrekturen bis zum Hinweis')).toBeVisible()
})

test('the hint settings are saved on the page from the intake view, and the pool\'s hint follows', async () => {
  let saved = false
  const calls = stubApi({
    'GET /pool': () => ({ body: saved ? { ...POOL, counter: { ...POOL.counter, hint: 'rescore' } } : POOL }),
    'GET /policy-pack/login-wall-hosts': { body: { hosts: [] } },
    'PUT /pool/settings': () => {
      saved = true
      return { body: { settings: { correction_threshold: 2, correction_rate: 0.3 } } }
    } })
  window.location.hash = '#/hinzufuegen'
  render(<App />)
  await userEvent.click(screen.getByRole('link', { name: 'Einstellungen' }))
  expect(await screen.findByLabelText('Korrekturen bis zum Hinweis')).toHaveValue(10)
  expect(screen.getByLabelText('Anteil bis zum Hinweis (in %)')).toHaveValue(30)
  await userEvent.clear(screen.getByLabelText('Korrekturen bis zum Hinweis'))
  await userEvent.type(screen.getByLabelText('Korrekturen bis zum Hinweis'), '2')
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  await vi.waitFor(() => expect(calls.find((call) => call.method === 'PUT')?.body)
    .toEqual({ correction_threshold: 2, correction_rate: 0.3 }))
  await userEvent.click(nav().getByRole('link', { name: 'Anzeigen' }))
  expect(await screen.findByText('neu scoren sinnvoll')).toBeVisible()
})

test('leaving the settings page for the pool reloads the pool', async () => {
  let loads = 0
  stubApi({ 'GET /pool': () => { loads += 1; return { body: POOL } } })
  render(<App />)
  await screen.findByRole('list', { name: 'Anzeigen' })
  await userEvent.click(screen.getByRole('link', { name: 'Einstellungen' }))
  await screen.findByLabelText('Korrekturen bis zum Hinweis')
  const before = loads
  await userEvent.click(nav().getByRole('link', { name: 'Anzeigen' }))
  await vi.waitFor(() => expect(loads).toBeGreaterThan(before))
})

test('the pool\'s rating keys rate on the pool but do nothing while the settings page is open', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL },
                          'PUT /postings/p2/rating': { body: { row: POOL.rows[1], counter: POOL.counter, next_pass: POOL.next_pass } } })
  render(<App />)
  await screen.findByRole('list', { name: 'Anzeigen' })
  await userEvent.click(screen.getByRole('heading', { level: 3, name: 'Data Engineer (m/w/d)' }))
  await userEvent.keyboard('1')
  await vi.waitFor(() => expect(calls.filter((call) => call.path.includes('/rating'))).toHaveLength(1))
  await userEvent.click(screen.getByRole('link', { name: 'Einstellungen' }))
  await screen.findByLabelText('Korrekturen bis zum Hinweis')
  // The gear keeps the keys off while it has focus; the page itself must keep them off too.
  const focused = document.activeElement as HTMLElement
  focused.blur()
  await userEvent.keyboard('1')
  await userEvent.keyboard('j2')
  expect(calls.filter((call) => call.path.includes('/rating'))).toHaveLength(1)
})

test('the settings page has no accessibility violations', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  window.location.hash = '#/einstellungen'
  const { container } = render(<App />)
  await screen.findByLabelText('Korrekturen bis zum Hinweis')
  expect(await axe(container)).toHaveNoViolations()
})
