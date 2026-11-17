import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import type { PassState, PoolRow, RatingAnswer, RatingBody } from '@/api'
import { axe } from '@/test-axe'
import { type Call, pending, stubApi } from '@/test-api'
import { label, POOL, poolWith, ratingAnswer, row as makeRow } from '@/test-fixtures'
import { POLL_MS, PoolView } from './PoolView'

const pass = (changes: Partial<PassState>): PassState => ({
  pass_id: 'ps1', status: 'running', started_at: null, error: null, total: 12, done: 0, unscreened: [], ...changes })

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  sessionStorage.clear()
})

/** Titles of the listed rows, in order. */
async function titles() {
  const list = await screen.findByRole('list', { name: 'Anzeigen' })
  return within(list).getAllByRole('heading', { level: 3 }).map((heading) => heading.textContent)
}

const row = (title: string) => within(screen.getByRole('heading', { name: title }).closest('li')!)

/** Advance the fake poll timer and let the pending answers settle. */
const tick = () => act(() => vi.advanceTimersByTimeAsync(POLL_MS))

test('the default filter lists the open rows in server order', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  expect(await titles()).toEqual(['Data Analyst (m/w/d)', 'Data Engineer (m/w/d)', 'Datenjournalist (m/w/d)',
    'Neue Stelle (m/w/d)', 'Junior Controller (m/w/d)', 'Vertrieb Innendienst (m/w/d)', 'Analyst (m/w/d)',
    'Buchhalter (m/w/d)', 'Importierte Stelle (m/w/d)'])
  expect(screen.getByRole('button', { name: 'Offen' })).toHaveAttribute('aria-pressed', 'true')
})

test('a row shows score, rating, status, link and the exploration mark', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  const first = row('Data Analyst (m/w/d)')
  expect(first.getByText('8')).toBeVisible()
  expect(first.getByText('Bewertet: Ja')).toBeVisible()
  expect(first.getByText('great stack')).toBeVisible()
  expect(first.getByRole('combobox', { name: /Status/ })).toHaveValue('open')
  expect(first.getByRole('link', { name: 'Data Analyst (m/w/d)' })).toHaveAttribute('href', '#/anzeigen/p1')
  expect(first.queryByText('Stichprobe')).toBeNull()
  expect(row('Datenjournalist (m/w/d)').getByText('Stichprobe')).toBeVisible()
  expect(row('Junior Controller (m/w/d)').getByText('Bewertet: Nein')).toBeVisible()
  expect(row('Neue Stelle (m/w/d)').getByText('noch kein Score')).toBeVisible()
  expect(row('Vertrieb Innendienst (m/w/d)').getByText('ausgeschlossen: keine-vertriebsjobs')).toBeVisible()
  expect(row('Analyst (m/w/d)').getByText('zurückgehalten: Anweisungen an eine KI')).toBeVisible()
  expect(row('Buchhalter (m/w/d)').getByText(/Score unlesbar/)).toBeVisible()
  expect(row('Buchhalter (m/w/d)').getByText(/scores\/broken\.json ist nicht lesbar/)).toBeInTheDocument()
})

test('each row shows when it was added, above its title, and the order stays as sent', async () => {
  stubApi({ 'GET /pool': { body: poolWith({ rows: [
    makeRow('new', 'Neuere Stelle (m/w/d)', { added_at: '2026-11-12T13:05:00+00:00' }),
    makeRow('old', 'Ältere Stelle (m/w/d)', { added_at: '2026-11-12T08:41:00+00:00' })] }) } })
  render(<PoolView />)
  expect(await titles()).toEqual(['Neuere Stelle (m/w/d)', 'Ältere Stelle (m/w/d)'])
  const second = row('Ältere Stelle (m/w/d)')
  const line = second.getByText('Hinzugefügt 12.11.2026, 09:41')
  expect(line).toBeVisible()
  expect(row('Neuere Stelle (m/w/d)').getByText('Hinzugefügt 12.11.2026, 14:05')).toBeVisible()
  const heading = screen.getByRole('heading', { name: 'Ältere Stelle (m/w/d)' })
  expect(heading).toHaveAccessibleName('Ältere Stelle (m/w/d)')
  expect(line.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(line.closest('time')).toHaveAttribute('datetime', '2026-11-12T08:41:00.000Z')
})

test.each([
  ['Noch nicht bewertet', ['Data Engineer (m/w/d)', 'Datenjournalist (m/w/d)', 'Neue Stelle (m/w/d)',
    'Vertrieb Innendienst (m/w/d)', 'Analyst (m/w/d)', 'Buchhalter (m/w/d)', 'Importierte Stelle (m/w/d)']],
  ['Bewertet', ['Data Analyst (m/w/d)', 'Junior Controller (m/w/d)']],
  ['Beworben', ['Projektleiter (m/w/d)']],
  ['Erledigt', ['Berater (m/w/d)']],
])('filter %s shows the right rows', async (name, expected) => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  await userEvent.click(screen.getByRole('button', { name }))
  expect(await titles()).toEqual(expected)
})

test('the Herkunft filter shows the imported rows of every status and hides the rest', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  await userEvent.click(screen.getByRole('button', { name: 'Herkunft' }))
  expect(await titles()).toEqual(['Importierte Stelle (m/w/d)', 'Projektleiter (m/w/d)', 'Berater (m/w/d)'])
})

test('an imported row shows where it came from, next to the exploration mark when both apply', async () => {
  stubApi({ 'GET /pool': { body: poolWith({ rows: [
    makeRow('i1', 'Alt-Stelle (m/w/d)', { origin: { table: 'jobs_alt', fit: 'gut', status: null }, exploration: true }),
    makeRow('p1', 'Neue Stelle (m/w/d)')] }) } })
  render(<PoolView />)
  await titles()
  const imported = row('Alt-Stelle (m/w/d)')
  expect(imported.getByText('Importiert aus jobs_alt')).toBeVisible()
  expect(imported.getByText('Stichprobe')).toBeVisible()
  expect(row('Neue Stelle (m/w/d)').queryByText(/Importiert aus/)).toBeNull()
})

test('the text filter matches title or company, ignoring case', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  await userEvent.type(screen.getByLabelText('Titel oder Firma'), 'NORDBLATT')
  expect(await titles()).toEqual(['Data Engineer (m/w/d)'])
  await userEvent.clear(screen.getByLabelText('Titel oder Firma'))
  await userEvent.type(screen.getByLabelText('Titel oder Firma'), 'journalist')
  expect(await titles()).toEqual(['Datenjournalist (m/w/d)'])
  await userEvent.type(screen.getByLabelText('Titel oder Firma'), 'xyz')
  expect(await screen.findByText('Keine Anzeige passt zu diesem Filter')).toBeVisible()
})

test('the counter shows corrections, share and the fitting hint', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  const label = 'Korrekturen seit der letzten Bewertung der Anzeigen:'
  expect(await screen.findByText(new RegExp(label))).toHaveTextContent(`${label} 3`)
  expect(screen.getByText('Anteil: 25 %')).toBeVisible()
  expect(screen.getByText('Ranking passt gut')).toBeVisible()
})

test('below ten ratings the share is not shown and a rescore hint is', async () => {
  stubApi({ 'GET /pool': { body: poolWith({ counter: { ...POOL.counter, rate: null, hint: 'rescore' } }) } })
  render(<PoolView />)
  expect(await screen.findByText('Anteil ab 10 Bewertungen')).toBeVisible()
  expect(screen.getByText('neue Bewertung sinnvoll')).toBeVisible()
})

test('the pass button shows the count and is disabled with an explanation at 0', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  const { unmount } = render(<PoolView />)
  expect(await screen.findByRole('button', { name: 'Neue Anzeigen bewerten (12)' })).toBeEnabled()
  unmount()
  stubApi({ 'GET /pool': { body: poolWith({ next_pass: { count: 0, rescore: false } }) } })
  render(<PoolView />)
  const button = await screen.findByRole('button', { name: 'Neue Anzeigen bewerten (0)' })
  expect(button).toBeDisabled()
  expect(button).toHaveAccessibleDescription('Es gibt keine neuen Anzeigen zu bewerten.')
})

test('a rescore hint with nothing to score explains the disabled button', async () => {
  stubApi({ 'GET /pool': { body: poolWith({ counter: { ...POOL.counter, hint: 'rescore' },
                                            next_pass: { count: 0, rescore: false } }) } })
  render(<PoolView />)
  const button = await screen.findByRole('button', { name: 'Neue Anzeigen bewerten (0)' })
  expect(button).toBeDisabled()
  expect(button).toHaveAccessibleDescription(/Es gibt nichts zu bewerten: Alle Anzeigen sind ausgeschlossen oder zurückgehalten\./)
})

test('a pass shows its progress, then reloads the pool when done', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  let polls = 0
  let reloads = 0
  const calls = stubApi({
    'GET /pool': () => {
      reloads += 1
      return { body: reloads === 1 ? POOL : poolWith({ next_pass: { count: 0, rescore: false } }) }
    },
    'POST /pool/passes': { status: 202, body: { pass_id: 'ps1' } },
    'GET /pool/passes/ps1': () => ({ body: pass(++polls === 1 ? { done: 4 } : { status: 'done', done: 12 }) }),
  })
  render(<PoolView />)
  const button = await screen.findByRole('button', { name: 'Neue Anzeigen bewerten (12)' })
  await act(async () => button.click())
  expect(button).toBeDisabled()
  await tick()
  expect(screen.getByText('Bewertung läuft: 4 von 12')).toBeVisible()
  // The counts change every poll, so they stay out of the live region.
  expect(screen.getByText('Bewertung läuft: 4 von 12').closest('[role="status"]')).toBeNull()
  await tick()
  expect(screen.queryByText(/Bewertung läuft/)).toBeNull()
  expect(await screen.findByRole('button', { name: 'Neue Anzeigen bewerten (0)' })).toBeDisabled()
  expect(calls.filter((call) => call.path === '/pool')).toHaveLength(2)
  expect(sessionStorage.length).toBe(0)
})

test('a stored pass resumes polling after a reload', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem('jobadvaisor.pool-pass', 'ps1')
  stubApi({ 'GET /pool': { body: POOL }, 'GET /pool/passes/ps1': { body: pass({ done: 7 }) } })
  render(<PoolView />)
  await screen.findByRole('button', { name: /Neue Anzeigen bewerten/ })
  await tick()
  expect(screen.getByText('Bewertung läuft: 7 von 12')).toBeVisible()
})

test('starting while another pass runs says so', async () => {
  stubApi({ 'GET /pool': { body: POOL },
            'POST /pool/passes': { status: 409, body: { error: 'pass in progress', detail: 'x' } } })
  render(<PoolView />)
  await userEvent.click(await screen.findByRole('button', { name: 'Neue Anzeigen bewerten (12)' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Es läuft schon eine andere Bewertung')
})

const QUESTION = pass({ status: 'awaiting_answer', unscreened: [
  { posting_id: 'u1', title: 'Ungeprüfte Stelle (m/w/d)', company: 'Nordblatt' }] })

async function openQuestion(answers: Record<string, unknown> = {}) {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem('jobadvaisor.pool-pass', 'ps1')
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'GET /pool/passes/ps1': { body: QUESTION },
                          'POST /pool/passes/ps1/unscreened': { status: 202, body: { pass_id: 'ps1' } }, ...answers })
  const view = render(<PoolView />)
  await screen.findByRole('button', { name: /Neue Anzeigen bewerten/ })
  await tick()
  return { calls, ...view }
}

test('the unscreened question names the postings and sends continue', async () => {
  const { calls } = await openQuestion()
  expect(screen.getByText('Ungeprüfte Stelle (m/w/d)')).toBeVisible()
  expect(screen.getByText(/Nordblatt/, { selector: 'li' })).toBeVisible()
  await act(async () => screen.getByRole('button', { name: 'Trotzdem bewerten' }).click())
  expect(calls.find((call) => call.path.endsWith('/unscreened'))!.body).toEqual({ continue: true })
  expect(screen.queryByRole('button', { name: 'Trotzdem bewerten' })).toBeNull()
})

test('the unscreened question sends abort and the pass then shows as aborted', async () => {
  let aborted = false
  const { calls } = await openQuestion({
    'GET /pool/passes/ps1': () => ({ body: aborted ? pass({ status: 'aborted' }) : QUESTION }),
    'POST /pool/passes/ps1/unscreened': () => {
      aborted = true
      return { status: 202, body: { pass_id: 'ps1' } }
    } })
  await act(async () => screen.getByRole('button', { name: 'Abbrechen' }).click())
  expect(calls.find((call) => call.path.endsWith('/unscreened'))!.body).toEqual({ continue: false })
  await tick()
  expect(screen.getByText('Die Bewertung wurde abgebrochen.')).toBeVisible()
})

test('an aborted pass is announced', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem('jobadvaisor.pool-pass', 'ps1')
  stubApi({ 'GET /pool': { body: POOL }, 'GET /pool/passes/ps1': { body: pass({ status: 'aborted' }) } })
  render(<PoolView />)
  await screen.findByRole('button', { name: /Neue Anzeigen bewerten/ })
  await tick()
  expect(screen.getByText('Die Bewertung wurde abgebrochen.')).toBeVisible()
  expect(screen.getByRole('button', { name: /Neue Anzeigen bewerten/ })).toBeEnabled()
})

test('a failed pass shows an error with retry that starts a new pass', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem('jobadvaisor.pool-pass', 'ps1')
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'GET /pool/passes/ps1': { body: pass({ status: 'failed', error: 'labels/p1.json: kaputt' }) },
                          'POST /pool/passes': { status: 202, body: { pass_id: 'ps2' } } })
  render(<PoolView />)
  await screen.findByRole('button', { name: /Neue Anzeigen bewerten/ })
  await tick()
  expect(screen.getByRole('heading', { name: 'Die Bewertung ist fehlgeschlagen' })).toBeVisible()
  expect(screen.getByText(/labels\/p1\.json: kaputt/)).toBeVisible()
  expect(screen.getByText(/kaputte Datei/)).toBeVisible()
  expect(screen.queryByText(/Server erreichbar/)).toBeNull()
  await act(async () => screen.getByRole('button', { name: 'Erneut versuchen' }).click())
  expect(calls.some((call) => call.method === 'POST' && call.path === '/pool/passes')).toBe(true)
})

test('settings save the share as 0 to 1 and reload the pool', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'PUT /pool/settings': { body: { settings: POOL.settings } } })
  render(<PoolView />)
  await userEvent.click(await screen.findByText('Einstellungen'))
  expect(screen.getByLabelText('Anteil bis zum Hinweis (in %)')).toHaveValue(30)
  await userEvent.clear(screen.getByLabelText('Korrekturen bis zum Hinweis'))
  await userEvent.type(screen.getByLabelText('Korrekturen bis zum Hinweis'), '5')
  await userEvent.clear(screen.getByLabelText('Anteil bis zum Hinweis (in %)'))
  await userEvent.type(screen.getByLabelText('Anteil bis zum Hinweis (in %)'), '25')
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  await vi.waitFor(() => expect(calls.filter((call) => call.path === '/pool')).toHaveLength(2))
  expect(calls.find((call) => call.method === 'PUT')!.body).toEqual({ correction_threshold: 5, correction_rate: 0.25 })
})

test.each([['0', '30', /ganze Zahl ab 1/], ['2.5', '30', /ganze Zahl ab 1/], ['5', '101', /von 0 bis 100/], ['5', '', /von 0 bis 100/]])(
  'settings reject %s / %s inline and send nothing', async (threshold, percent, message) => {
    const calls = stubApi({ 'GET /pool': { body: POOL } })
    render(<PoolView />)
    await userEvent.click(await screen.findByText('Einstellungen'))
    await userEvent.clear(screen.getByLabelText('Korrekturen bis zum Hinweis'))
    await userEvent.type(screen.getByLabelText('Korrekturen bis zum Hinweis'), threshold)
    await userEvent.clear(screen.getByLabelText('Anteil bis zum Hinweis (in %)'))
    if (percent) await userEvent.type(screen.getByLabelText('Anteil bis zum Hinweis (in %)'), percent)
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(calls.some((call) => call.method === 'PUT')).toBe(false)
  })

test('a failed settings save keeps the input and offers a retry', async () => {
  let fail = true
  const calls = stubApi({ 'GET /pool': { body: POOL },
                          'PUT /pool/settings': () => (fail ? { status: 500 } : { body: { settings: POOL.settings } }) })
  render(<PoolView />)
  await userEvent.click(await screen.findByText('Einstellungen'))
  await userEvent.clear(screen.getByLabelText('Korrekturen bis zum Hinweis'))
  await userEvent.type(screen.getByLabelText('Korrekturen bis zum Hinweis'), '7')
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  expect(await screen.findByText('Die Einstellungen wurden nicht gespeichert.')).toBeVisible()
  expect(screen.getByLabelText('Korrekturen bis zum Hinweis')).toHaveValue(7)
  fail = false
  await userEvent.click(screen.getByRole('button', { name: 'Erneut versuchen' }))
  await vi.waitFor(() => expect(calls.filter((call) => call.method === 'PUT')).toHaveLength(2))
})

test('changing the status sends the PATCH and the row leaves the default view', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'PATCH /postings/p2': { body: {} } })
  render(<PoolView />)
  await titles()
  await userEvent.selectOptions(row('Data Engineer (m/w/d)').getByRole('combobox'), 'applied')
  await vi.waitFor(() => expect(screen.queryByRole('heading', { name: 'Data Engineer (m/w/d)' })).toBeNull())
  expect(calls.find((call) => call.method === 'PATCH')!.body).toEqual({ status: 'applied' })
  await userEvent.click(screen.getByRole('button', { name: 'Beworben' }))
  expect(await titles()).toEqual(['Data Engineer (m/w/d)', 'Projektleiter (m/w/d)'])
})

test('the status control shows saving, and a failure offers a retry', async () => {
  let attempts = 0
  stubApi({ 'GET /pool': { body: POOL },
            'PATCH /postings/p2': () => (++attempts === 1 ? { status: 500 } : { body: {} }) })
  render(<PoolView />)
  await titles()
  await userEvent.selectOptions(row('Data Engineer (m/w/d)').getByRole('combobox'), 'done')
  const failed = await screen.findByText('Der Status wurde nicht gespeichert.')
  expect(row('Data Engineer (m/w/d)').getByRole('combobox')).toHaveValue('open')
  await userEvent.click(within(failed).getByRole('button', { name: 'Erneut versuchen' }))
  await vi.waitFor(() => expect(screen.queryByRole('heading', { name: 'Data Engineer (m/w/d)' })).toBeNull())
})

test('the saving state shows while the PATCH is pending', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'PATCH /postings/p2': pending() })
  render(<PoolView />)
  await titles()
  await userEvent.selectOptions(row('Data Engineer (m/w/d)').getByRole('combobox'), 'done')
  expect(await screen.findByText('wird gespeichert…')).toBeVisible()
})

test('an empty pool offers to add postings', async () => {
  stubApi({ 'GET /pool': { body: poolWith({ rows: [] }) } })
  render(<PoolView />)
  expect(await screen.findByText('Noch keine Anzeigen gespeichert')).toBeVisible()
  expect(screen.getByRole('link', { name: 'Anzeige hinzufügen' })).toHaveAttribute('href', '#/hinzufuegen')
})

test('a failed load shows an error with retry', async () => {
  let fail = true
  stubApi({ 'GET /pool': () => (fail ? { status: 500 } : { body: POOL }) })
  render(<PoolView />)
  expect(await screen.findByText('Anzeigen konnten nicht geladen werden')).toBeVisible()
  fail = false
  await userEvent.click(screen.getByRole('button', { name: 'Erneut versuchen' }))
  expect(await titles()).toHaveLength(9)
})

test('the pool view has no accessibility violations', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  const { container } = render(<PoolView />)
  await titles()
  expect(await axe(container)).toHaveNoViolations()
})

test('the unscreened question has no accessibility violations', async () => {
  const { container } = await openQuestion()
  vi.useRealTimers()
  expect(await axe(container)).toHaveNoViolations()
})

test('failed polls show a notice with retry after three failures, and retry resumes polling', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem('jobadvaisor.pool-pass', 'ps1')
  let down = true
  const calls = stubApi({ 'GET /pool': { body: POOL },
                          'GET /pool/passes/ps1': () => (down ? { status: 500 } : { body: pass({ status: 'done' }) }) })
  render(<PoolView />)
  await screen.findByRole('button', { name: /Neue Anzeigen bewerten/ })
  await tick()
  await tick()
  expect(screen.queryByText('Der Stand der Bewertung ist gerade nicht abrufbar')).toBeNull()
  await tick()
  expect(screen.getByText('Der Stand der Bewertung ist gerade nicht abrufbar')).toBeVisible()
  expect(screen.getByRole('button', { name: /Neue Anzeigen bewerten/ })).toBeDisabled()
  const polls = calls.filter((call) => call.path === '/pool/passes/ps1').length
  await tick()
  expect(calls.filter((call) => call.path === '/pool/passes/ps1')).toHaveLength(polls)
  down = false
  await act(async () => screen.getByRole('button', { name: 'Erneut versuchen' }).click())
  await tick()
  expect(screen.queryByText('Der Stand der Bewertung ist gerade nicht abrufbar')).toBeNull()
  expect(await screen.findByRole('button', { name: /Neue Anzeigen bewerten/ })).toBeEnabled()
})

test('a failed reload keeps the list and shows a retry above it', async () => {
  let reloads = 0
  stubApi({ 'GET /pool': () => (++reloads === 2 ? { status: 500 } : { body: POOL }),
            'PUT /pool/settings': { body: { settings: POOL.settings } } })
  render(<PoolView />)
  await userEvent.click(await screen.findByText('Einstellungen'))
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  expect(await screen.findByText(/konnten nicht neu geladen werden/)).toBeVisible()
  expect(await titles()).toHaveLength(9)
  await userEvent.click(screen.getByRole('button', { name: 'Erneut versuchen' }))
  await vi.waitFor(() => expect(screen.queryByText(/konnten nicht neu geladen werden/)).toBeNull())
})

test('an empty filter result offers to reset the filters', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  await userEvent.click(screen.getByRole('button', { name: 'Erledigt' }))
  await userEvent.type(screen.getByLabelText('Titel oder Firma'), 'xyz')
  await userEvent.click(await screen.findByRole('button', { name: 'Filter zurücksetzen' }))
  expect(screen.getByLabelText('Titel oder Firma')).toHaveValue('')
  expect(screen.getByRole('button', { name: 'Offen' })).toHaveAttribute('aria-pressed', 'true')
  expect(await titles()).toHaveLength(9)
})

test('an older pool load arriving late does not overwrite a newer one', async () => {
  let release: (answer: { body: unknown }) => void = () => {}
  let loads = 0
  stubApi({ 'GET /pool': () => (++loads === 1
    ? (new Promise((resolve) => { release = resolve }) as never) : { body: POOL }) })
  const { rerender } = render(<PoolView active />)
  rerender(<PoolView active={false} />)
  rerender(<PoolView active />)
  expect(await titles()).toHaveLength(9)
  await act(async () => release({ body: poolWith({ rows: [] }) }))
  expect(await titles()).toHaveLength(9)
})

// --- rating from the pool -----------------------------------------------------------------

const ENGINEER = 'Data Engineer (m/w/d)'
const AFTER = { ...POOL.counter, corrections: 4, hint: 'rescore' as const }
/** The rating route of posting `id`, answering the way the server resolves a body. */
const rateRoute = (id: string, counter = AFTER) => (call: { body: unknown }) =>
  ratingAnswer(POOL.rows.find((entry) => entry.posting_id === id)!, call.body as RatingBody, counter)
const puts = (calls: Call[]) => calls.filter((call) => call.method === 'PUT' && call.path.endsWith('/rating'))
const button = (name: string) => screen.getByRole('button', { name })
/** Expects the shown correction counter to read `count`: only a stored answer changes it. */
const corrections = (count: number) =>
  expect(screen.getByText(/Korrekturen seit der letzten Bewertung/)).toHaveTextContent(`der Anzeigen: ${count}`)

test('a chip on a posting without a verdict gives it the derived verdict and the counter follows', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': rateRoute('p2') })
  render(<PoolView />)
  await titles()
  await userEvent.click(within(screen.getByRole('list', { name: 'Anzeigen' })).getAllByRole('button', { name: 'great stack' })[0])
  expect(puts(calls)[0].body).toEqual({ chips: ['great-stack'], note: null })
  expect(await row(ENGINEER).findByText('Bewertet: Ja')).toBeVisible()
  expect(screen.getByText('neue Bewertung sinnvoll')).toBeVisible()
  expect(screen.getByText(/Korrekturen seit der letzten Bewertung der Anzeigen:/)).toHaveTextContent('4')
})

test('chips of both polarities stay selectable, whatever the verdict', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': rateRoute('p2') })
  render(<PoolView />)
  await titles()
  await userEvent.click(button('great stack'))
  await row(ENGINEER).findByText('Bewertet: Ja')
  expect(button('too junior')).toBeEnabled()
  await userEvent.click(button('too junior'))
  await vi.waitFor(() => expect(puts(calls)).toHaveLength(2))
  expect(puts(calls)[1].body).toEqual({ verdict: 'positive', chips: ['great-stack', 'too-junior'], note: null })
  await vi.waitFor(() => expect(button('too junior')).toHaveAttribute('aria-pressed', 'true'))
  expect(button('great stack')).toHaveAttribute('aria-pressed', 'true')
})

test('a verdict given explicitly is not changed by a chip, by mouse or by Shift+digit', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': rateRoute('p2') })
  render(<PoolView />)
  await titles()
  await userEvent.click(button(`Nein, auf keinen Fall: ${ENGINEER}`))
  await vi.waitFor(() => expect(button(`Nein, auf keinen Fall: ${ENGINEER}`)).toHaveAttribute('aria-pressed', 'true'))
  await userEvent.click(button('great stack'))
  await vi.waitFor(() => expect(puts(calls)).toHaveLength(2))
  expect(puts(calls)[1].body).toEqual({ verdict: 'negative', strength: 'strong', chips: ['great-stack'], note: null })
  await userEvent.keyboard('{Shift>}2{/Shift}')
  await vi.waitFor(() => expect(puts(calls)).toHaveLength(3))
  expect(puts(calls)[2].body).toEqual({ verdict: 'negative', strength: 'strong', chips: ['great-stack', 'too-junior'], note: null })
  expect(button(`Nein, auf keinen Fall: ${ENGINEER}`)).toHaveAttribute('aria-pressed', 'true')
  expect(button(`Ja, auf jeden Fall: ${ENGINEER}`)).toHaveAttribute('aria-pressed', 'false')
})

test('Shift+digit on a posting without a verdict sends no verdict', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': rateRoute('p2') })
  render(<PoolView />)
  await titles()
  await userEvent.keyboard('{Shift>}1{/Shift}')
  await vi.waitFor(() => expect(puts(calls)).toHaveLength(1))
  expect(puts(calls)[0].body).toEqual({ chips: ['great-stack'], note: null })
})

test('a batch from the keyboard: verdict, reasons in focus, Enter to the next unrated posting', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': rateRoute('p2'),
                          'PUT /postings/p3/rating': rateRoute('p3') })
  render(<PoolView />)
  await titles()
  await userEvent.keyboard('1')
  await vi.waitFor(() => expect(document.getElementById('reasons-p2')).toHaveFocus())
  expect(puts(calls)[0].body).toEqual({ verdict: 'positive', strength: 'strong', chips: [], note: null })
  expect(await screen.findByRole('button', { name: `Ja, auf jeden Fall: ${ENGINEER}` })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('button', { name: 'great stack' })).toBeVisible()
  await userEvent.keyboard('{Enter}')
  await vi.waitFor(() => expect(document.getElementById('row-p3')).toHaveFocus())
  await userEvent.keyboard('4')
  await vi.waitFor(() => expect(document.getElementById('reasons-p3')).toHaveFocus())
  expect(puts(calls)[1].body).toEqual({ verdict: 'negative', strength: 'strong', chips: [], note: null })
  await userEvent.keyboard('{Enter}')
  await vi.waitFor(() => expect(document.getElementById('row-n1')).toHaveFocus())
})

// --- the four levels ----------------------------------------------------------------------

const LEVELS = [
  ['Ja, auf jeden Fall', '1', 'positive', 'strong'],
  ['Ja, vielleicht', '2', 'positive', 'weak'],
  ['Nein, eher nicht', '3', 'negative', 'weak'],
  ['Nein, auf keinen Fall', '4', 'negative', 'strong'],
] as const

test.each(LEVELS)('the button "%s" stores its level and shows it as chosen alone', async (name, _key, verdict, strength) => {
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': rateRoute('p2') })
  render(<PoolView />)
  await titles()
  await userEvent.click(button(`${name}: ${ENGINEER}`))
  await vi.waitFor(() => expect(button(`${name}: ${ENGINEER}`)).toHaveAttribute('aria-pressed', 'true'))
  expect(puts(calls)[0].body).toEqual({ verdict, strength, chips: [], note: null })
  expect(LEVELS.filter(([other]) => other !== name)
    .map(([other]) => button(`${other}: ${ENGINEER}`).getAttribute('aria-pressed'))).toEqual(['false', 'false', 'false'])
})

test.each(LEVELS)('the key for "%s" rates the selected posting at its level', async (name, key, verdict, strength) => {
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': rateRoute('p2') })
  render(<PoolView />)
  await titles()
  await userEvent.keyboard(key)
  await vi.waitFor(() => expect(puts(calls)).toHaveLength(1))
  expect(puts(calls)[0].body).toEqual({ verdict, strength, chips: [], note: null })
  expect(await screen.findByRole('button', { name: `${name}: ${ENGINEER}` })).toHaveAttribute('aria-pressed', 'true')
})

test('a chip and a note after a level resend its strength', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': rateRoute('p2') })
  render(<PoolView />)
  await titles()
  await userEvent.click(button(`Ja, vielleicht: ${ENGINEER}`))
  await vi.waitFor(() => expect(button(`Ja, vielleicht: ${ENGINEER}`)).toHaveAttribute('aria-pressed', 'true'))
  await userEvent.click(button('too junior'))
  await vi.waitFor(() => expect(puts(calls)).toHaveLength(2))
  expect(puts(calls)[1].body).toEqual({ verdict: 'positive', strength: 'weak', chips: ['too-junior'], note: null })
  await userEvent.type(screen.getByLabelText(/^Notiz/), 'Remote')
  await userEvent.tab()
  await vi.waitFor(() => expect(puts(calls)).toHaveLength(3))
  expect(puts(calls)[2].body).toEqual({ verdict: 'positive', strength: 'weak', chips: ['too-junior'], note: 'Remote' })
})

test('choosing the level already shown sends nothing, another level replaces it', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': rateRoute('p2') })
  render(<PoolView />)
  await titles()
  await userEvent.click(button(`Nein, eher nicht: ${ENGINEER}`))
  await vi.waitFor(() => expect(button(`Nein, eher nicht: ${ENGINEER}`)).toHaveAttribute('aria-pressed', 'true'))
  await userEvent.click(button(`Nein, eher nicht: ${ENGINEER}`))
  expect(puts(calls)).toHaveLength(1)
  await userEvent.click(button(`Nein, auf keinen Fall: ${ENGINEER}`))
  await vi.waitFor(() => expect(puts(calls)).toHaveLength(2))
  expect(puts(calls)[1].body).toEqual({ verdict: 'negative', strength: 'strong', chips: [], note: null })
})

test('a stored level shows as chosen, a stored label without strength shows a plain Ja', async () => {
  const stored = (verdict: 'positive' | 'negative', strength: 'weak' | 'strong' | null) => label(verdict, [], strength)
  stubApi({ 'GET /pool': { body: poolWith({ rows: [
    makeRow('a', 'Weak Yes', { label: stored('positive', 'weak') }),
    makeRow('b', 'Plain No', { label: stored('negative', null) })] }) } })
  render(<PoolView />)
  await titles()
  expect(within(screen.getByRole('heading', { name: 'Weak Yes' }).closest('li')!)
    .getByRole('button', { name: 'Ja, vielleicht: Weak Yes' })).toHaveAttribute('aria-pressed', 'true')
  const plain = row('Plain No')
  expect(plain.getByText('Bewertet: Nein')).toBeVisible()
  expect(plain.queryAllByRole('button', { pressed: true })).toHaveLength(0)
})

test('the four level buttons sit in one line below the description, score and status', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  const line = button(`Ja, auf jeden Fall: ${ENGINEER}`).parentElement!
  expect(line).toHaveClass('flex', 'flex-wrap')
  expect([...line.children].map((child) => child.getAttribute('aria-label')?.split(':')[0])).toEqual(
    ['Ja, auf jeden Fall', 'Ja, vielleicht', 'Nein, eher nicht', 'Nein, auf keinen Fall'])
  const below = line.parentElement!.parentElement!
  expect(below.parentElement).toBe(row(ENGINEER).getByRole('combobox', { name: /Status/ }).closest('li'))
  expect(below).toHaveClass('basis-full')
  const status = row(ENGINEER).getByRole('combobox', { name: /Status/ })
  expect(status.compareDocumentPosition(below) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})

test('the keys 1 to 4 typed into the note or the filter rate nothing', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  await userEvent.type(screen.getByLabelText(/^Notiz/), '1234')
  await userEvent.type(screen.getByLabelText('Titel oder Firma'), '1234')
  expect(puts(calls)).toHaveLength(0)
})

test('the shortcuts are shown in the view', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  const legend = within(screen.getByRole('region', { name: 'Tastatur' }))
  for (const [name, key] of [['Ja, auf jeden Fall', '1'], ['Ja, vielleicht', '2'], ['Nein, eher nicht', '3'], ['Nein, auf keinen Fall', '4']]) {
    expect(legend.getByText(name).previousElementSibling).toHaveTextContent(key)
  }
  expect(legend.queryByText('Interessant')).toBeNull()
  expect(legend.getByText('Weiter zur nächsten unbewerteten Anzeige')).toBeVisible()
})

test('typing shortcut keys in the note or the filter field triggers nothing', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  await userEvent.type(screen.getByLabelText(/^Notiz/), '12nj{Enter}')
  expect(screen.getByLabelText(/^Notiz/)).toHaveValue('12nj\n')
  await userEvent.type(screen.getByLabelText('Titel oder Firma'), '12')
  expect(puts(calls)).toHaveLength(0)
  expect(screen.getByLabelText('Titel oder Firma')).toHaveValue('12')
})

test('n focuses the note and Escape returns to the title', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  await userEvent.keyboard('n')
  expect(screen.getByLabelText(/^Notiz/)).toHaveFocus()
  expect(screen.getByLabelText(/^Notiz/)).toHaveValue('')
  await userEvent.keyboard('{Escape}')
  expect(document.getElementById('row-p2')).toHaveFocus()
})

test('a note is stored with the verdict when it loses focus', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': rateRoute('p2') })
  render(<PoolView />)
  await titles()
  await userEvent.click(button(`Ja, auf jeden Fall: ${ENGINEER}`))
  await userEvent.type(screen.getByLabelText(/^Notiz/), 'Remote  ')
  await userEvent.tab()
  await vi.waitFor(() => expect(puts(calls)).toHaveLength(2))
  expect(puts(calls)[1].body).toEqual({ verdict: 'positive', strength: 'strong', chips: [], note: 'Remote' })
})

test('the note is a multi-line field and its lines are stored together', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': rateRoute('p2') })
  render(<PoolView />)
  await titles()
  await userEvent.click(button(`Ja, auf jeden Fall: ${ENGINEER}`))
  const note = screen.getByLabelText(/^Notiz/)
  expect(note.tagName).toBe('TEXTAREA')
  await userEvent.type(note, 'Zeile 1{Enter}Zeile 2')
  await userEvent.tab()
  await vi.waitFor(() => expect(puts(calls)).toHaveLength(2))
  expect(puts(calls)[1].body).toEqual({ verdict: 'positive', strength: 'strong', chips: [], note: 'Zeile 1\nZeile 2' })
})

test('text pasted while no text field has focus lands in the note of the selected posting', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': rateRoute('p2') })
  render(<PoolView />)
  await titles()
  await userEvent.click(button(`Ja, vielleicht: ${ENGINEER}`))
  await vi.waitFor(() => expect(document.getElementById('reasons-p2')).toHaveFocus())
  fireEvent.paste(document.activeElement!, { clipboardData: { getData: () => 'Eingefügt' } })
  const note = screen.getByLabelText(/^Notiz/)
  await vi.waitFor(() => expect(note).toHaveFocus())
  expect(note).toHaveValue('Eingefügt')
  // a second paste with another element in focus is appended on a new line
  ;(document.activeElement as HTMLElement).blur()
  fireEvent.paste(document.body, { clipboardData: { getData: () => 'Zweite Zeile' } })
  await vi.waitFor(() => expect(screen.getByLabelText(/^Notiz/)).toHaveValue('Eingefügt\nZweite Zeile'))
})

test('a paste into a text field is left to the field', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  const filter = screen.getByLabelText('Titel oder Firma')
  expect(fireEvent.paste(filter, { clipboardData: { getData: () => 'Engineer' } })).toBe(true)
  expect(screen.getByLabelText(/^Notiz/)).toHaveValue('')
  expect(fireEvent.paste(screen.getByLabelText(/^Notiz/), { clipboardData: { getData: () => 'x' } })).toBe(true)
})

test('a note on a posting without verdict or chip waits for one and says so', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': rateRoute('p2') })
  render(<PoolView />)
  await titles()
  await userEvent.type(screen.getByLabelText(/^Notiz/), 'Remote')
  expect(screen.getByText(/gespeichert, sobald du ein Urteil oder einen Grund wählst/)).toBeVisible()
  await userEvent.tab()
  expect(puts(calls)).toHaveLength(0)
  await userEvent.click(button(`Ja, auf jeden Fall: ${ENGINEER}`))
  await vi.waitFor(() => expect(puts(calls)).toHaveLength(1))
  expect(puts(calls)[0].body).toEqual({ verdict: 'positive', strength: 'strong', chips: [], note: 'Remote' })
})

test('rating shows saving, then a failure keeps the input and a retry stores it', async () => {
  let fail = true
  const calls = stubApi({ 'GET /pool': { body: POOL },
    'PUT /postings/p2/rating': (call) => (fail ? { status: 500, body: { error: 'x', detail: '' } } : rateRoute('p2')(call)) })
  render(<PoolView />)
  await titles()
  await userEvent.click(button('great stack'))
  const failure = await screen.findByText(/Die Bewertung wurde nicht gespeichert/)
  expect(button('great stack')).toHaveAttribute('aria-pressed', 'true')
  fail = false
  await userEvent.click(within(failure).getByRole('button', { name: 'Erneut versuchen' }))
  expect(await row(ENGINEER).findByText('Bewertet: Ja')).toBeVisible()
  expect(screen.queryByText(/Die Bewertung wurde nicht gespeichert/)).toBeNull()
  expect(puts(calls).map((call) => call.body)).toEqual(Array(2).fill({ chips: ['great-stack'], note: null }))
})

test('the saving state shows while the rating is pending', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': pending() })
  render(<PoolView />)
  await titles()
  await userEvent.click(button(`Ja, auf jeden Fall: ${ENGINEER}`))
  expect(await screen.findByText('wird gespeichert…')).toBeVisible()
})

test('a chip that gives no verdict on its own says so and keeps the chip', async () => {
  stubApi({ 'GET /pool': { body: poolWith({ reason_chips: [...POOL.reason_chips, { id: 'neutral', label: 'neutral', polarity: null }] }) },
            'PUT /postings/p2/rating': rateRoute('p2') })
  render(<PoolView />)
  await titles()
  await userEvent.click(button('neutral'))
  expect(await screen.findByText(/Dieser Grund legt kein Urteil fest/)).toBeVisible()
  expect(button('neutral')).toHaveAttribute('aria-pressed', 'true')
})

test('Enter chains: a second Enter on the title link advances again instead of opening it', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  await userEvent.keyboard('{Enter}')
  await vi.waitFor(() => expect(document.getElementById('row-p3')).toHaveFocus())
  await userEvent.keyboard('{Enter}')
  await vi.waitFor(() => expect(document.getElementById('row-n1')).toHaveFocus())
})

test('Shift+1 then Shift+2 act on the same posting although the first answer derives a verdict', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': rateRoute('p2'),
                          'PUT /postings/p3/rating': rateRoute('p3') })
  render(<PoolView />)
  await titles()
  await userEvent.keyboard('{Shift>}1{/Shift}')
  await row(ENGINEER).findByText('Bewertet: Ja')
  await userEvent.keyboard('{Shift>}2{/Shift}')
  await vi.waitFor(() => expect(puts(calls)).toHaveLength(2))
  expect(puts(calls).map((call) => call.path)).toEqual(Array(2).fill('/postings/p2/rating'))
  expect(puts(calls)[1].body).toEqual({ verdict: 'positive', chips: ['great-stack', 'too-junior'], note: null })
})

test('two rapid ratings of one posting reach the server in order, the second shows at the end', async () => {
  let release!: () => void
  const gate = new Promise<void>((resolve) => { release = resolve })
  const route = rateRoute('p2')
  const calls = stubApi({ 'GET /pool': { body: POOL },
    'PUT /postings/p2/rating': (call) => (puts(calls).length === 1
      ? (gate.then(() => route(call)) as unknown as ReturnType<typeof route>) : route(call)) })
  render(<PoolView />)
  await titles()
  await userEvent.click(button(`Ja, auf jeden Fall: ${ENGINEER}`))
  await vi.waitFor(() => expect(puts(calls)).toHaveLength(1))
  await userEvent.click(button(`Nein, auf keinen Fall: ${ENGINEER}`))
  await new Promise((resolve) => setTimeout(resolve, 20))
  expect(puts(calls)).toHaveLength(1)
  await act(async () => release())
  await vi.waitFor(() => expect(puts(calls)).toHaveLength(2))
  expect(puts(calls)[1].body).toMatchObject({ verdict: 'negative' })
  await vi.waitFor(() => expect(button(`Nein, auf keinen Fall: ${ENGINEER}`)).toHaveAttribute('aria-pressed', 'true'))
})

test('Enter on a focused title link keeps its own meaning, on a row it chains', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  const link = screen.getByRole('link', { name: ENGINEER })
  link.focus()
  expect(fireEvent.keyDown(link, { key: 'Enter' })).toBe(true)
  expect(fireEvent.keyDown(document.getElementById('row-p2')!, { key: 'Enter' })).toBe(false)
})

test('a mouse press on another row\'s title focuses it without moving the selection, the click selects', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  const link = screen.getByRole('link', { name: 'Datenjournalist (m/w/d)' })
  const user = userEvent.setup()
  await user.pointer({ keys: '[MouseLeft>]', target: link })
  expect(link).toHaveFocus()
  expect(row(ENGINEER).getByLabelText(/^Notiz/)).toBeVisible()
  expect(row('Datenjournalist (m/w/d)').queryByLabelText(/^Notiz/)).toBeNull()
  await user.pointer({ keys: '[/MouseLeft]', target: link })
  expect(row('Datenjournalist (m/w/d)').getByLabelText(/^Notiz/)).toBeVisible()
  expect(row(ENGINEER).queryByLabelText(/^Notiz/)).toBeNull()
})

test('a click elsewhere in a row selects it', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  await userEvent.click(row('Datenjournalist (m/w/d)').getByText(/Grünwerk Solar, Kiel/))
  expect(row('Datenjournalist (m/w/d)').getByLabelText(/^Notiz/)).toBeVisible()
})

test('keyboard focus into a row selects it, also right after a mouse press elsewhere', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  const link = screen.getByRole('link', { name: 'Datenjournalist (m/w/d)' })
  act(() => link.focus())
  expect(row('Datenjournalist (m/w/d)').getByLabelText(/^Notiz/)).toBeVisible()
  fireEvent.pointerDown(link)
  await new Promise((resolve) => setTimeout(resolve, 0))
  act(() => screen.getByRole('link', { name: ENGINEER }).focus())
  expect(row(ENGINEER).getByLabelText(/^Notiz/)).toBeVisible()
})

test('Enter with no further unrated posting says so, every time', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  await userEvent.click(button('Bewertet'))
  ;(document.activeElement as HTMLElement).blur()
  await userEvent.keyboard('{Enter}')
  const first = (await screen.findByText(/Keine weitere unbewertete Anzeige/)).textContent
  await userEvent.keyboard('{Enter}')
  expect(screen.getByText(/Keine weitere unbewertete Anzeige/).textContent).not.toBe(first)
})

test('a stored chip unknown to the policy pack can be removed after the server rejects it', async () => {
  const stored = makeRow('p1', 'Data Analyst (m/w/d)', { label: { verdict: 'positive', chips: ['gone'], note: null, rated_at: '2026-10-12T08:00:00+00:00' } })
  const calls = stubApi({ 'GET /pool': { body: poolWith({ rows: [stored, ...POOL.rows.slice(1)] }) },
    'PUT /postings/p1/rating': (call) => ((call.body as RatingBody).chips.includes('gone')
      ? { status: 422, body: { error: 'invalid rating', detail: 'unknown reason chip: gone' } }
      : ratingAnswer(stored, call.body as RatingBody)) })
  render(<PoolView />)
  await titles()
  await userEvent.click(button('Ja, auf jeden Fall: Data Analyst (m/w/d)'))
  expect(await screen.findByText(/gibt es nicht mehr/)).toBeVisible()
  expect(screen.getByRole('button', { name: 'Erneut versuchen' })).toBeVisible()
  expect(button('gone')).toHaveAttribute('aria-pressed', 'true')
  await userEvent.click(button('gone'))
  await vi.waitFor(() => expect(screen.queryByText(/gibt es nicht mehr/)).toBeNull())
  expect(puts(calls)[1].body).toEqual({ verdict: 'positive', strength: 'strong', chips: [], note: null })
})

test('untoggling the only chip of an unstored posting resets locally without a request', async () => {
  const calls = stubApi({ 'GET /pool': { body: poolWith({ reason_chips: [...POOL.reason_chips, { id: 'neutral', label: 'neutral', polarity: null }] }) },
                          'PUT /postings/p2/rating': rateRoute('p2') })
  render(<PoolView />)
  await titles()
  await userEvent.click(button('neutral'))
  await screen.findByText(/Dieser Grund legt kein Urteil fest/)
  await userEvent.click(button('neutral'))
  expect(puts(calls)).toHaveLength(1)
  expect(button('neutral')).toHaveAttribute('aria-pressed', 'false')
  expect(screen.queryByText(/Dieser Grund legt kein Urteil fest/)).toBeNull()
})

test('the stored note replaces the draft once the answer arrives', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': (call) => {
    const { body } = ratingAnswer(POOL.rows.find((entry) => entry.posting_id === 'p2')!, call.body as RatingBody, AFTER) as { body: RatingAnswer }
    return { body: { ...body, row: { ...body.row, label: { ...body.row.label!, note: 'vom Server' } } } }
  } })
  render(<PoolView />)
  await titles()
  await userEvent.click(button(`Ja, auf jeden Fall: ${ENGINEER}`))
  await userEvent.type(screen.getByLabelText(/^Notiz/), 'Entwurf')
  await userEvent.click(button('great stack'))
  await vi.waitFor(() => expect(screen.getByLabelText(/^Notiz/)).toHaveValue('vom Server'))
})

test('a posting rated in "Noch nicht bewertet" stays there until the filter changes', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': rateRoute('p2') })
  render(<PoolView />)
  await titles()
  await userEvent.click(button('Noch nicht bewertet'))
  await userEvent.click(button(`Ja, auf jeden Fall: ${ENGINEER}`))
  await vi.waitFor(() => expect(button(`Ja, auf jeden Fall: ${ENGINEER}`)).toHaveAttribute('aria-pressed', 'true'))
  expect(await titles()).toContain(ENGINEER)
  await userEvent.click(button('Bewertet'))
  await userEvent.click(button('Noch nicht bewertet'))
  expect(await titles()).not.toContain(ENGINEER)
})

test('the shortcuts act on the row clicked, and J and K move between rows', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p3/rating': rateRoute('p3') })
  render(<PoolView />)
  await titles()
  await userEvent.keyboard('j')
  await vi.waitFor(() => expect(document.getElementById('row-p3')).toHaveFocus())
  await userEvent.keyboard('2')
  await vi.waitFor(() => expect(puts(calls)).toHaveLength(1))
  expect(calls.find((call) => call.path === '/postings/p3/rating')).toBeDefined()
})

test('a status change is announced and the select stays enabled while saving', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'PATCH /postings/p2': pending() })
  render(<PoolView />)
  await titles()
  const select = row(ENGINEER).getByRole('combobox')
  await userEvent.selectOptions(select, 'applied')
  expect(await screen.findByText('wird gespeichert…')).toBeVisible()
  expect(select).toBeEnabled()
  expect(select).toHaveAttribute('aria-busy', 'true')
})

test('a finished status change tells that the row left the view', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'PATCH /postings/p2': { body: {} } })
  render(<PoolView />)
  await titles()
  await userEvent.selectOptions(row(ENGINEER).getByRole('combobox'), 'applied')
  expect(await screen.findByText(`${ENGINEER}: Status beworben. Die Anzeige ist nicht mehr in dieser Ansicht.`)).toBeInTheDocument()
})

test('the settings form follows the stored settings after a reload', async () => {
  let reloads = 0
  stubApi({ 'GET /pool': () => ({ body: ++reloads === 1 ? POOL : poolWith({ settings: { correction_threshold: 7, correction_rate: 0.5 } }) }),
            'PUT /pool/settings': { body: { settings: POOL.settings } } })
  render(<PoolView />)
  await userEvent.click(await screen.findByText('Einstellungen'))
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  await vi.waitFor(() => expect(screen.getByLabelText('Korrekturen bis zum Hinweis')).toHaveValue(7))
  expect(screen.getByLabelText('Anteil bis zum Hinweis (in %)')).toHaveValue(50)
})

/** The answer of `POST /postings/{id}/score` for `base`: the posting page, of which the pool reads
 * the row, counter, next-pass figures and `screening`. The row carries no `exploration` mark
 * (`posting_page` has none). */
const scoreAnswer = (base: PoolRow, changes: Partial<PoolRow> = {}, rest: object = {}) => ({
  row: { ...base, exploration: false, ...changes }, posting: {}, score: null, examples: [], reason_chips: [],
  screening: true, counter: POOL.counter, next_pass: POOL.next_pass, ...rest })

const NEW = 'Neue Stelle (m/w/d)'
const baseRow = (id: string) => POOL.rows.find((entry) => entry.posting_id === id)!

test('every row has a score button: "Score berechnen" without a score, "Neu berechnen" with one', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  expect(row(NEW).getByRole('button', { name: 'Score berechnen' })).toBeEnabled()
  expect(row('Data Analyst (m/w/d)').getByRole('button', { name: 'Neu berechnen' })).toBeEnabled()
  expect(row('Buchhalter (m/w/d)').getByRole('button', { name: 'Score berechnen' })).toBeEnabled()
})

test('a row score updates the row, the counter and the pass button count', async () => {
  const quiet = poolWith({ next_pass: { count: 0, rescore: false } })
  const calls = stubApi({ 'GET /pool': { body: quiet }, 'POST /postings/n1/score': { body: scoreAnswer(
    baseRow('n1'), { state: 'scored', score: 9 }, { counter: { ...POOL.counter, corrections: 4 },
      next_pass: { count: 8, rescore: true } }) } })
  render(<PoolView />)
  await titles()
  expect(await screen.findByRole('button', { name: 'Neue Anzeigen bewerten (0)' })).toBeDisabled()
  await userEvent.click(row(NEW).getByRole('button', { name: 'Score berechnen' }))
  expect(await row(NEW).findByText('9')).toBeVisible()
  expect(row(NEW).getByRole('button', { name: 'Neu berechnen' })).toBeEnabled()
  expect(screen.getByText(/Korrekturen seit der letzten Bewertung/)).toHaveTextContent('Korrekturen seit der letzten Bewertung der Anzeigen: 4')
  expect(screen.getByRole('button', { name: 'Neue Anzeigen bewerten (8)' })).toBeEnabled()
  expect(calls.filter((call) => call.method === 'POST').map((call) => call.path)).toEqual(['/postings/n1/score'])
})

test('a row that was a "Stichprobe" keeps its mark after its score', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'POST /postings/p3/score': { body: scoreAnswer(baseRow('p3'), { score: 5 }) } })
  render(<PoolView />)
  await titles()
  await userEvent.click(row('Datenjournalist (m/w/d)').getByRole('button', { name: 'Neu berechnen' }))
  expect(await row('Datenjournalist (m/w/d)').findByText('5')).toBeVisible()
  expect(row('Datenjournalist (m/w/d)').getByText('Stichprobe')).toBeVisible()
})

test('a row computes with its own busy button while the others stay usable', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'POST /postings/n1/score': pending })
  render(<PoolView />)
  await titles()
  await userEvent.click(row(NEW).getByRole('button', { name: 'Score berechnen' }))
  expect(await row(NEW).findByRole('button', { name: 'Wird berechnet …' })).toHaveAttribute('aria-disabled', 'true')
  expect(row('Data Analyst (m/w/d)').getByRole('button', { name: 'Neu berechnen' })).toBeEnabled()
})

test('a 409 "scoring in progress" shows its message on the row only and a retry', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'POST /postings/n1/score': { status: 409, body: { error: 'scoring in progress', detail: 'ps1' } } })
  render(<PoolView />)
  await titles()
  await userEvent.click(row(NEW).getByRole('button', { name: 'Score berechnen' }))
  expect(await row(NEW).findByRole('alert')).toHaveTextContent('Es läuft gerade schon ein Scoring. Versuch es gleich noch einmal.')
  expect(row(NEW).getByRole('button', { name: 'Erneut versuchen' })).toBeEnabled()
  expect(row('Data Analyst (m/w/d)').queryByRole('alert')).toBeNull()
})

test('a "scoring in progress" message on a row goes when the pass ends, a failed one on another row stays', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  let polls = 0
  stubApi({ 'GET /pool': { body: POOL }, 'POST /pool/passes': { status: 202, body: { pass_id: 'ps1' } },
    'GET /pool/passes/ps1': () => ({ body: pass(++polls === 1 ? { done: 4 } : { status: 'done', done: 12 }) }),
    'POST /postings/n1/score': { status: 409, body: { error: 'scoring in progress', detail: 'ps1' } },
    'POST /postings/broken/score': { status: 502, body: { error: 'scoring failed', detail: 'x' } } })
  render(<PoolView />)
  const start = await screen.findByRole('button', { name: 'Neue Anzeigen bewerten (12)' })
  await act(async () => start.click())
  await act(async () => row(NEW).getByRole('button', { name: 'Score berechnen' }).click())
  await act(async () => row('Buchhalter (m/w/d)').getByRole('button', { name: 'Score berechnen' }).click())
  expect(await row(NEW).findByRole('alert')).toBeVisible()
  expect(await row('Buchhalter (m/w/d)').findByRole('alert')).toBeVisible()
  await tick()
  await tick()
  await vi.waitFor(() => expect(row(NEW).queryByRole('alert')).toBeNull())
  expect(row(NEW).getByRole('button', { name: 'Score berechnen' })).toBeEnabled()
  expect(row('Buchhalter (m/w/d)').getByRole('alert')).toHaveTextContent('Der Score konnte nicht berechnet werden.')
})

test('excluded, held and unscreened-without-screening rows show the button disabled with the reason', async () => {
  const unchecked = makeRow('u1', 'Ungeprüft (m/w/d)', { state: 'unscored', score: null, unscreened: true })
  stubApi({ 'GET /pool': { body: poolWith({ rows: [...POOL.rows, unchecked], screening: false }) } })
  render(<PoolView />)
  await titles()
  for (const [title, reason] of [
    ['Vertrieb Innendienst (m/w/d)', /Eine Ausschlussregel greift: keine-vertriebsjobs/],
    ['Analyst (m/w/d)', /Der Inhaltsfilter hält diese Anzeige zurück \(Verdacht: Anweisungen an eine KI\)/],
    ['Ungeprüft (m/w/d)', /kein Filter eingerichtet/],
  ] as const) {
    const scope = row(title)
    expect(scope.getByRole('button', { name: 'Score berechnen' })).toBeDisabled()
    expect(scope.getByRole('button', { name: 'Score berechnen' })).toHaveAccessibleDescription(reason)
    expect(scope.getByRole('button', { name: 'Warum nicht verfügbar?' })).toHaveAccessibleDescription(reason)
  }
})

test('an unscreened row is scored when a classifier is configured', async () => {
  const unchecked = makeRow('u1', 'Ungeprüft (m/w/d)', { state: 'unscored', score: null, unscreened: true })
  stubApi({ 'GET /pool': { body: poolWith({ rows: [...POOL.rows, unchecked], screening: true }) } })
  render(<PoolView />)
  await titles()
  expect(row('Ungeprüft (m/w/d)').getByRole('button', { name: 'Score berechnen' })).toBeEnabled()
})

test('a held refusal on the click reloads the pool and the row turns disabled', async () => {
  let loads = 0
  stubApi({ 'GET /pool': () => ({ body: ++loads === 1 ? POOL : poolWith({ rows: POOL.rows.map((entry) =>
    entry.posting_id === 'n1' ? { ...entry, state: 'held', categories: ['instructions_for_ai'] } : entry) }) }),
  'POST /postings/n1/score': { status: 409, body: { error: 'held', detail: 'instructions_for_ai' } } })
  render(<PoolView />)
  await titles()
  await userEvent.click(row(NEW).getByRole('button', { name: 'Score berechnen' }))
  await vi.waitFor(() => expect(row(NEW).getByRole('button', { name: 'Score berechnen' })).toBeDisabled())
  expect(row(NEW).queryByRole('alert')).toBeNull()
})

test('the pool with score buttons has no accessibility violations', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  const { container } = render(<PoolView />)
  await titles()
  expect(await axe(container)).toHaveNoViolations()
})

// --- score range and sort -------------------------------------------------------------------

const DATA_ANALYST = 'Data Analyst (m/w/d)'
const von = () => screen.getByRole('combobox', { name: 'von' })
const bis = () => screen.getByRole('combobox', { name: 'bis' })
const sortSelect = () => screen.getByRole('combobox', { name: 'Sortierung' })
const NO_SCORE = 'ohne Score'

test('the score range lists only the rows within it, combined with the state and the text filter', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  expect(screen.getByRole('group', { name: 'Score' })).toContainElement(von())
  await userEvent.selectOptions(von(), '7')
  await userEvent.selectOptions(bis(), '9')
  expect(await titles()).toEqual([DATA_ANALYST, ENGINEER])
  await userEvent.click(button('Noch nicht bewertet'))
  expect(await titles()).toEqual([ENGINEER])
  await userEvent.click(button('Offen'))
  await userEvent.type(screen.getByLabelText('Titel oder Firma'), 'analyst')
  expect(await titles()).toEqual([DATA_ANALYST])
})

test('"ohne Score" to "ohne Score" lists only the unscored rows', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  await userEvent.selectOptions(bis(), NO_SCORE)
  expect(await titles()).toEqual([NEW, 'Buchhalter (m/w/d)'])
})

test('a range from 0 to 0 lists a row scored 0 and no unscored one', async () => {
  stubApi({ 'GET /pool': { body: poolWith({ rows: [makeRow('z', 'Null (m/w/d)', { score: 0 }), ...POOL.rows] }) } })
  render(<PoolView />)
  await titles()
  await userEvent.selectOptions(von(), '0')
  await userEvent.selectOptions(bis(), '0')
  expect(await titles()).toEqual(['Null (m/w/d)'])
})

test('moving "von" above "bis" pulls "bis" up, and "bis" below "von" pulls "von" down', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  await userEvent.selectOptions(von(), '3')
  await userEvent.selectOptions(bis(), '5')
  await userEvent.selectOptions(von(), '8')
  expect(von()).toHaveValue('8')
  expect(bis()).toHaveValue('8')
  await userEvent.selectOptions(bis(), '2')
  expect(von()).toHaveValue('2')
  expect(bis()).toHaveValue('2')
})

test('focus stays on the select after a range or sort change', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  for (const [select, value] of [[von, '3'], [bis, '6'], [sortSelect, 'added-asc']] as const) {
    await userEvent.selectOptions(select(), value)
    expect(select()).toHaveFocus()
  }
})

test('the sort select offers the ranking and six orders and sorts the list', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  expect(within(sortSelect()).getAllByRole('option').map((option) => option.textContent)).toEqual([
    'Rangfolge', 'Score: höchster zuerst', 'Score: niedrigster zuerst', 'Deine Bewertung: beste zuerst',
    'Deine Bewertung: schlechteste zuerst', 'Hinzugefügt: neueste zuerst', 'Hinzugefügt: älteste zuerst'])
  expect(sortSelect()).toHaveValue('rank')
  await userEvent.selectOptions(sortSelect(), 'Score: höchster zuerst')
  expect((await titles()).slice(0, 3)).toEqual([DATA_ANALYST, ENGINEER, 'Importierte Stelle (m/w/d)'])
})

test('sorted by rating, a row rated here keeps its place until the sort changes', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': rateRoute('p2') })
  render(<PoolView />)
  await titles()
  await userEvent.selectOptions(sortSelect(), 'rating-desc')
  const before = await titles()
  expect(before.slice(0, 3)).toEqual([DATA_ANALYST, 'Junior Controller (m/w/d)', ENGINEER])
  await userEvent.click(button(`Ja, auf jeden Fall: ${ENGINEER}`))
  await vi.waitFor(() => corrections(4)) // the stored answer (the pressed state is optimistic)
  expect(await titles()).toEqual(before)
  await userEvent.selectOptions(sortSelect(), 'rating-asc')
  await userEvent.selectOptions(sortSelect(), 'rating-desc')
  expect((await titles())[0]).toEqual(ENGINEER)
})

test('sorted by rating, a row rated here moves to its place when the state filter changes', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': rateRoute('p2') })
  render(<PoolView />)
  await titles()
  await userEvent.selectOptions(sortSelect(), 'rating-desc')
  const before = await titles()
  await userEvent.click(button(`Ja, auf jeden Fall: ${ENGINEER}`))
  await vi.waitFor(() => corrections(4))
  expect(await titles()).toEqual(before)
  await userEvent.click(button('Bewertet'))
  await userEvent.click(button('Offen'))
  expect((await titles())[0]).toEqual(ENGINEER)
})

test('sorted by score, a row scored here moves to its place when the range changes', async () => {
  stubApi({ 'GET /pool': { body: POOL },
    'POST /postings/p3/score': { body: scoreAnswer(baseRow('p3'), { score: 9 }) } })
  render(<PoolView />)
  await titles()
  await userEvent.selectOptions(sortSelect(), 'score-desc')
  const before = await titles()
  await userEvent.click(row('Datenjournalist (m/w/d)').getByRole('button', { name: 'Neu berechnen' }))
  expect(await row('Datenjournalist (m/w/d)').findByText('9')).toBeVisible()
  expect(await titles()).toEqual(before)
  await userEvent.selectOptions(von(), '0')
  await userEvent.selectOptions(von(), NO_SCORE)
  expect((await titles())[0]).toEqual('Datenjournalist (m/w/d)')
})

test('a new load takes the order afresh: a new row and changed scores are sorted in', async () => {
  let loads = 0
  const fresh = [makeRow('z', 'Neu hinzu (m/w/d)', { score: 10 }),
    ...POOL.rows.map((entry) => (entry.posting_id === 'p3' ? { ...entry, score: 9 } : entry))]
  stubApi({ 'GET /pool': () => ({ body: ++loads === 1 ? POOL : poolWith({ rows: fresh }) }) })
  const { rerender } = render(<PoolView active />)
  await titles()
  await userEvent.selectOptions(sortSelect(), 'score-desc')
  expect((await titles())[0]).toEqual(DATA_ANALYST)
  rerender(<PoolView active={false} />)
  rerender(<PoolView active />)
  await vi.waitFor(async () => expect((await titles()).slice(0, 3))
    .toEqual(['Neu hinzu (m/w/d)', 'Datenjournalist (m/w/d)', DATA_ANALYST]))
})

/** An answer held back until `release` is called, for a request the user outpaces. */
function late() {
  let release: (answer: { body: unknown; status?: number }) => void = () => {}
  const answer = new Promise<{ body: unknown; status?: number }>((resolve) => { release = resolve })
  return { answer, release }
}

test('a score answering after the range changed does not bring its row back into the range', async () => {
  const held = late()
  stubApi({ 'GET /pool': { body: POOL }, 'POST /postings/n1/score': held.answer })
  render(<PoolView />)
  await titles()
  await userEvent.selectOptions(bis(), NO_SCORE)
  expect(await titles()).toEqual([NEW, 'Buchhalter (m/w/d)'])
  await userEvent.click(row(NEW).getByRole('button', { name: 'Score berechnen' }))
  await userEvent.selectOptions(von(), '7')
  await userEvent.selectOptions(bis(), '9')
  expect(await titles()).toEqual([DATA_ANALYST, ENGINEER])
  await act(async () => held.release({ body: scoreAnswer(baseRow('n1'), { state: 'scored', score: 3 }, { counter: AFTER }) }))
  await vi.waitFor(() => corrections(4))
  expect(await titles()).toEqual([DATA_ANALYST, ENGINEER])
})

test('a rating answering after the range changed does not bring its row back into the range', async () => {
  const held = late()
  stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p3/rating': held.answer })
  render(<PoolView />)
  await titles()
  await userEvent.selectOptions(von(), '3')
  await userEvent.selectOptions(bis(), '3')
  expect(await titles()).toEqual(['Datenjournalist (m/w/d)'])
  await userEvent.click(button('Ja, auf jeden Fall: Datenjournalist (m/w/d)'))
  await userEvent.selectOptions(von(), '7')
  await userEvent.selectOptions(bis(), '9')
  expect(await titles()).toEqual([DATA_ANALYST, ENGINEER])
  const body = { verdict: 'positive' as const, strength: 'strong' as const, chips: [], note: null }
  await act(async () => held.release(ratingAnswer(baseRow('p3'), body, AFTER)))
  await vi.waitFor(() => corrections(4))
  expect(await titles()).toEqual([DATA_ANALYST, ENGINEER])
})

test('sorted by score, a row scored again by its button keeps its place until the sort changes', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL },
    'POST /postings/p3/score': { body: scoreAnswer(baseRow('p3'), { score: 9 }) } })
  render(<PoolView />)
  await titles()
  await userEvent.selectOptions(sortSelect(), 'score-desc')
  const before = await titles()
  await userEvent.click(row('Datenjournalist (m/w/d)').getByRole('button', { name: 'Neu berechnen' }))
  expect(await row('Datenjournalist (m/w/d)').findByText('9')).toBeVisible()
  expect(await titles()).toEqual(before)
  await userEvent.selectOptions(sortSelect(), 'score-asc')
  await userEvent.selectOptions(sortSelect(), 'score-desc')
  expect((await titles())[0]).toEqual('Datenjournalist (m/w/d)')
  expect(calls.filter((call) => call.method === 'POST')).toHaveLength(1)
})

test('under "ohne Score" a row scored here stays with its score until the range changes, the text filter still hides it', async () => {
  stubApi({ 'GET /pool': { body: POOL },
    'POST /postings/n1/score': { body: scoreAnswer(baseRow('n1'), { state: 'scored', score: 9 }) } })
  render(<PoolView />)
  await titles()
  await userEvent.selectOptions(bis(), NO_SCORE)
  expect(await titles()).toEqual([NEW, 'Buchhalter (m/w/d)'])
  await userEvent.click(row(NEW).getByRole('button', { name: 'Score berechnen' }))
  expect(await row(NEW).findByText('9')).toBeVisible()
  expect(await titles()).toEqual([NEW, 'Buchhalter (m/w/d)'])
  await userEvent.type(screen.getByLabelText('Titel oder Firma'), 'buchhalter')
  expect(await titles()).toEqual(['Buchhalter (m/w/d)'])
  await userEvent.clear(screen.getByLabelText('Titel oder Firma'))
  await userEvent.selectOptions(bis(), '10')
  await userEvent.selectOptions(bis(), NO_SCORE)
  expect(await titles()).toEqual(['Buchhalter (m/w/d)'])
})

test('a finished pass reloads the pool and the scored rows leave "ohne Score", except one rated here before', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  let reloads = 0
  const scoredNow = { state: 'scored' as const, score: 5 }
  stubApi({
    'GET /pool': () => ({ body: ++reloads === 1 ? POOL : poolWith({ rows: POOL.rows.map((entry) =>
      ['n1', 'broken'].includes(entry.posting_id) ? { ...entry, ...scoredNow } : entry) }) }),
    'PUT /postings/n1/rating': rateRoute('n1'),
    'POST /pool/passes': { status: 202, body: { pass_id: 'ps1' } },
    'GET /pool/passes/ps1': { body: pass({ status: 'done', done: 12 }) },
  })
  render(<PoolView />)
  await titles()
  await act(async () => { fireEvent.change(bis(), { target: { value: String(-1) } }) })
  expect(await titles()).toEqual([NEW, 'Buchhalter (m/w/d)'])
  await act(async () => button(`Ja, auf jeden Fall: ${NEW}`).click())
  await vi.waitFor(() => corrections(4))
  await act(async () => button('Neue Anzeigen bewerten (12)').click())
  await tick()
  await vi.waitFor(() => expect(reloads).toBe(2))
  await vi.waitFor(() => expect(screen.queryByText('Buchhalter (m/w/d)')).toBeNull())
  expect(await titles()).toEqual([NEW])
})

test('the pool with the score range and sort controls has no accessibility violations', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  const { container } = render(<PoolView />)
  await titles()
  expect(screen.getByRole('group', { name: 'Score' })).toBeVisible()
  expect(sortSelect()).toBeVisible()
  await userEvent.selectOptions(von(), '3')
  await userEvent.selectOptions(sortSelect(), 'score-desc')
  expect(await axe(container)).toHaveNoViolations()
})

test('J, K and Enter follow the sorted order', async () => {
  const rows = [
    makeRow('d', 'Vierte (m/w/d)', { added_at: '2026-10-04T08:00:00+00:00', label: label('positive') }),
    makeRow('a', 'Dritte (m/w/d)', { added_at: '2026-10-03T08:00:00+00:00' }),
    makeRow('c', 'Zweite (m/w/d)', { added_at: '2026-10-02T08:00:00+00:00', label: label('negative') }),
    makeRow('b', 'Erste (m/w/d)', { added_at: '2026-10-01T08:00:00+00:00' }),
  ]
  stubApi({ 'GET /pool': { body: poolWith({ rows }) } })
  render(<PoolView />)
  await titles()
  await userEvent.selectOptions(sortSelect(), 'added-asc')
  expect(await titles()).toEqual(['Erste (m/w/d)', 'Zweite (m/w/d)', 'Dritte (m/w/d)', 'Vierte (m/w/d)'])
  sortSelect().blur() // the shortcuts are off while the select has focus
  await userEvent.keyboard('j')
  await vi.waitFor(() => expect(document.getElementById('row-c')).toHaveFocus())
  await userEvent.keyboard('{Enter}')
  await vi.waitFor(() => expect(document.getElementById('row-a')).toHaveFocus())
  await userEvent.keyboard('k')
  await vi.waitFor(() => expect(document.getElementById('row-c')).toHaveFocus())
})

test('keys typed into the range and sort selects trigger no shortcut', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  for (const select of [von, bis, sortSelect]) {
    select().focus()
    await userEvent.keyboard('2j')
  }
  expect(puts(calls)).toHaveLength(0)
  expect(document.activeElement).toBe(sortSelect())
})

test('"Filter zurücksetzen" resets the range as well and keeps the sort', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  await userEvent.selectOptions(sortSelect(), 'added-asc')
  await userEvent.selectOptions(von(), '0')
  await userEvent.selectOptions(bis(), '0')
  await userEvent.click(await screen.findByRole('button', { name: 'Filter zurücksetzen' }))
  expect(await titles()).toHaveLength(9)
  expect(von()).toHaveValue('-1')
  expect(bis()).toHaveValue('10')
  expect(sortSelect()).toHaveValue('added-asc')
})

test('a status change still removes a row rated here from the list it no longer fits', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': rateRoute('p2'), 'PATCH /postings/p2': { body: {} } })
  render(<PoolView />)
  await titles()
  await userEvent.click(button('Noch nicht bewertet'))
  await userEvent.click(button(`Ja, auf jeden Fall: ${ENGINEER}`))
  await vi.waitFor(() => expect(button(`Ja, auf jeden Fall: ${ENGINEER}`)).toHaveAttribute('aria-pressed', 'true'))
  await userEvent.selectOptions(row(ENGINEER).getByRole('combobox', { name: /Status/ }), 'applied')
  await vi.waitFor(() => expect(screen.queryByText(ENGINEER)).toBeNull())
})

test('a "Stichprobe" row sorted by score sits by its score and keeps its mark', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  await userEvent.selectOptions(sortSelect(), 'score-desc')
  const listed = await titles()
  expect(listed.slice(0, 5)).toEqual([DATA_ANALYST, ENGINEER, 'Importierte Stelle (m/w/d)', 'Datenjournalist (m/w/d)', 'Junior Controller (m/w/d)'])
  expect(row('Datenjournalist (m/w/d)').getByText('Stichprobe')).toBeVisible()
})
