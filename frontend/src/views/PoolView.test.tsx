import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import type { CheckState, PassProgress, PassState, Pool, PoolRow, RatingAnswer, RatingBody } from '@/api'
import { axe } from '@/test-axe'
import { type Call, pending, stubApi } from '@/test-api'
import { label, POOL, poolWith, ratingAnswer, row as makeRow } from '@/test-fixtures'
import { SettingsLink } from '@/components/settings'
import { POLL_MS, PoolView, SWAP_LOCK_MS } from './PoolView'

const pass = (changes: Partial<PassState>): PassState => ({
  pass_id: 'ps1', status: 'running', started_at: null, error: null, progress: null, cancel_requested: false,
  scored: 0, unscreened: [], ...changes })

/** A running pass in `phase`, with `score` as `[done, total]` (null: not counted yet). */
const running = (phase: PassProgress['phase'], score: [number, number] | null = null,
                 changes: Partial<PassState> = {}) => pass({
  progress: { phase, score: score && { done: score[0], total: score[1] } }, ...changes })

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  sessionStorage.clear()
  localStorage.clear()
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
  expect(first.getByRole('combobox', { name: /Bewerbungsstatus/ })).toHaveValue('open')
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
  expect(await screen.findByText('3 Korrekturen')).toBeVisible()
  expect(screen.getByText('3 Korrekturen').parentElement).toHaveTextContent('3 Korrekturen · Ranking passt gut · Anteil 25 %')
  expect(screen.getByText('Ranking passt gut')).toBeVisible()
  expect(screen.queryByText(/Anteil ab 10 Bewertungen/)).toBeNull()
  expect(screen.queryByText(/seit dem letzten Neu-Scoren/)).toBeNull()
})

test('one correction reads in the singular', async () => {
  stubApi({ 'GET /pool': { body: poolWith({ counter: { ...POOL.counter, corrections: 1 } }) } })
  render(<PoolView />)
  expect(await screen.findByText('1 Korrektur')).toBeVisible()
})

test('below ten ratings the share is not shown and a rescore hint is', async () => {
  stubApi({ 'GET /pool': { body: poolWith({ counter: { ...POOL.counter, rate: null, hint: 'rescore' } }) } })
  render(<PoolView />)
  expect(await screen.findByText(`Anteil ab 10 Bewertungen (bisher ${POOL.counter.rated})`)).toBeVisible()
  expect(screen.getByText('3 Korrekturen').parentElement).toHaveTextContent('3 Korrekturen · neu scoren sinnvoll · Anteil ab 10 Bewertungen (bisher 12)')
  expect(screen.getByText('neu scoren sinnvoll')).toBeVisible()
})

// --- the split pass button ----------------------------------------------------------------

const NEXT = (changes: Partial<Pool['next_pass']> = {}) =>
  poolWith({ next_pass: { default: 'unscored', unscored: 3, all: 12, ...changes } })
const posts = (calls: Call[]) => calls.filter((call) => call.method === 'POST' && call.path === '/pool/passes')
const mainPart = (name: string | RegExp) => screen.findByRole('button', { name })
/** The split button's group; it is there, hidden, also while a pass computes. */
const splitGroup = () => document.querySelector<HTMLElement>('[role="group"][aria-label="Scoren"]')!
/** Wait until the pool is loaded and the pass button rendered, whether or not it is shown. */
const loaded = () => waitFor(() => expect(splitGroup()).not.toBeNull())
const COST_ALL = (count: number) => `${count} Anzeigen, je ein Modellaufruf. Vorhandene Scores werden ersetzt.`

/** Open the variant menu by keyboard: jsdom lacks the pointer APIs Radix wants for a click. */
async function openMenu() {
  screen.getByRole('button', { name: 'Andere Variante wählen' }).focus()
  await userEvent.keyboard('{Enter}')
  return screen.findByRole('menu')
}

test('below the thresholds the main part scores the postings without a score', async () => {
  stubApi({ 'GET /pool': { body: NEXT() } })
  render(<PoolView />)
  expect(await mainPart('Anzeigen ohne Score scoren (3)')).toBeEnabled()
})

test('with the rescore hint the main part scores all postings, and the menu says it replaces scores', async () => {
  stubApi({ 'GET /pool': { body: NEXT({ default: 'all' }) } })
  render(<PoolView />)
  expect(await mainPart('Alle Anzeigen neu scoren (12)')).toBeEnabled()
  expect(within(await openMenu()).getByRole('menuitemradio', { name: /Alle Anzeigen neu scoren/ })).toHaveTextContent(COST_ALL(12))
})

test('one posting without a score is named in the singular', async () => {
  stubApi({ 'GET /pool': { body: NEXT({ unscored: 1 }) } })
  render(<PoolView />)
  await mainPart('Anzeigen ohne Score scoren (1)')
  expect(within(await openMenu()).getByRole('menuitemradio', { name: /Nur Anzeigen ohne Score/ })).toHaveTextContent('1 Anzeige ohne Score, je ein Modellaufruf.')
})

test('one posting to rescore is named in the singular', async () => {
  stubApi({ 'GET /pool': { body: NEXT({ default: 'all', all: 1 }) } })
  render(<PoolView />)
  await mainPart('Alle Anzeigen neu scoren (1)')
  expect(within(await openMenu()).getByRole('menuitemradio', { name: /Alle Anzeigen neu scoren/ })).toHaveTextContent('1 Anzeige, je ein Modellaufruf. Vorhandene Scores werden ersetzt.')
})

test('the menu, opened by keyboard, lists both variants with counts and costs and marks the shown one', async () => {
  stubApi({ 'GET /pool': { body: NEXT() } })
  render(<PoolView />)
  await mainPart(/Anzeigen ohne Score scoren/)
  const menu = within(await openMenu())
  const unscored = menu.getByRole('menuitemradio', { name: /Nur Anzeigen ohne Score \(3\)/ })
  const all = menu.getByRole('menuitemradio', { name: /Alle Anzeigen neu scoren \(12\)/ })
  expect(unscored).toHaveAttribute('aria-checked', 'true')
  expect(all).toHaveAttribute('aria-checked', 'false')
  expect(unscored).toHaveTextContent('3 Anzeigen ohne Score, je ein Modellaufruf.')
  expect(all).toHaveTextContent(COST_ALL(12))
})

test('choosing a menu entry switches the main part and sends no request', async () => {
  const calls = stubApi({ 'GET /pool': { body: NEXT() } })
  render(<PoolView />)
  await mainPart(/Anzeigen ohne Score scoren/)
  await openMenu()
  await userEvent.click(screen.getByRole('menuitemradio', { name: /Alle Anzeigen neu scoren/ }))
  await mainPart('Alle Anzeigen neu scoren (12)')
  expect(calls.filter((call) => call.method !== 'GET')).toEqual([])
  expect(screen.queryByRole('menu')).toBeNull()
})

const startable = () => stubApi({ 'GET /pool': { body: NEXT() }, 'POST /pool/passes': { status: 202, body: { pass_id: 'ps1' } },
                                  'GET /pool/passes/ps1': { body: pass({}) } })

test('the main part starts the default variant', async () => {
  const calls = startable()
  render(<PoolView />)
  await userEvent.click(await mainPart('Anzeigen ohne Score scoren (3)'))
  await vi.waitFor(() => expect(posts(calls)).toHaveLength(1))
  expect(posts(calls)[0].body).toEqual({ variant: 'unscored' })
})

test('the main part starts the picked variant', async () => {
  const calls = startable()
  render(<PoolView />)
  await pickAll()
  await userEvent.click(await mainPart('Alle Anzeigen neu scoren (12)'))
  await vi.waitFor(() => expect(posts(calls)).toHaveLength(1))
  expect(posts(calls)[0].body).toEqual({ variant: 'all' })
})

test('the menu works by keyboard alone: arrows move, Enter chooses', async () => {
  const calls = stubApi({ 'GET /pool': { body: NEXT() } })
  render(<PoolView />)
  await mainPart(/Anzeigen ohne Score scoren/)
  await openMenu()
  await userEvent.keyboard('{ArrowDown}')
  expect(screen.getByRole('menuitemradio', { name: /Alle Anzeigen neu scoren/ })).toHaveFocus()
  await userEvent.keyboard('{Enter}')
  expect(await mainPart('Alle Anzeigen neu scoren (12)')).toBeVisible()
  expect(screen.queryByRole('menu')).toBeNull()
  expect(calls.filter((call) => call.method !== 'GET')).toEqual([])
})

test('pool shortcuts stay off while the menu has focus', async () => {
  const calls = stubApi({ 'GET /pool': { body: NEXT() } })
  render(<PoolView />)
  await mainPart(/Anzeigen ohne Score scoren/)
  await openMenu()
  const item = screen.getByRole('menuitemradio', { name: /Nur Anzeigen ohne Score/ })
  expect(item).toHaveFocus()
  await userEvent.keyboard('1j4n')
  expect(calls.filter((call) => call.method !== 'GET')).toEqual([])
  expect(screen.getByRole('menu')).toBeVisible()
  expect(item).toHaveFocus()
})

test('Escape closes the menu and focus returns to the trigger', async () => {
  stubApi({ 'GET /pool': { body: NEXT() } })
  render(<PoolView />)
  await mainPart(/Anzeigen ohne Score scoren/)
  await openMenu()
  await userEvent.keyboard('{Escape}')
  await vi.waitFor(() => expect(screen.queryByRole('menu')).toBeNull())
  expect(screen.getByRole('button', { name: 'Andere Variante wählen' })).toHaveFocus()
})

test('an open menu closes when a pass starts', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem('jobadvaisor.pool-pass', 'ps1')
  stubApi({ 'GET /pool': { body: NEXT() }, 'GET /pool/passes/ps1': { body: pass({ status: 'failed', error: 'kaputt' }) },
            'POST /pool/passes': { status: 202, body: { pass_id: 'ps2' } }, 'GET /pool/passes/ps2': { body: pass({ pass_id: 'ps2' }) } })
  render(<PoolView />)
  await loaded()
  await tick()
  await openMenu()
  // The modal menu hides the rest from assistive technology and the pointer; a click sent
  // straight to the retry button stands in for a pass started some other way.
  await act(async () => screen.getByRole('button', { name: 'Erneut versuchen', hidden: true }).click())
  await vi.waitFor(() => expect(screen.queryByRole('menu')).toBeNull())
  // The pass button has given way to the cancel button, so no variant can be picked.
  expect(screen.queryByRole('button', { name: 'Andere Variante wählen' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Scoren abbrechen' })).toBeVisible()
})

/** Pick "Alle" in the menu of a view whose default is `unscored`. */
async function pickAll() {
  await mainPart(/Anzeigen ohne Score scoren/)
  await openMenu()
  await userEvent.click(screen.getByRole('menuitemradio', { name: /Alle Anzeigen neu scoren/ }))
  await mainPart('Alle Anzeigen neu scoren (12)')
}

test('a pick survives a rating that leaves the default as it is', async () => {
  stubApi({ 'GET /pool': { body: NEXT() },
            'PUT /postings/p2/rating': (call) => ratingAnswer(POOL.rows.find((entry) => entry.posting_id === 'p2')!,
              call.body as RatingBody, POOL.counter, { default: 'unscored', unscored: 2, all: 12 }) })
  render(<PoolView />)
  await titles()
  await pickAll()
  await userEvent.click(screen.getAllByRole('button', { name: 'great stack' })[0])
  expect(await mainPart('Alle Anzeigen neu scoren (12)')).toBeVisible()
  await openMenu()
  expect(await screen.findByRole('menuitemradio', { name: /Nur Anzeigen ohne Score \(2\)/ })).toBeVisible()
})

test('a pick is dropped when ratings change the default and change it back', async () => {
  let answers = 0
  stubApi({ 'GET /pool': { body: NEXT() },
            'PUT /postings/p2/rating': (call) => ratingAnswer(POOL.rows.find((entry) => entry.posting_id === 'p2')!,
              call.body as RatingBody, POOL.counter, { default: ++answers === 1 ? 'all' : 'unscored', unscored: 3, all: 12 }) })
  render(<PoolView />)
  await titles()
  await pickAll()
  await userEvent.click(screen.getAllByRole('button', { name: 'great stack' })[0])
  await mainPart('Alle Anzeigen neu scoren (12)')
  await userEvent.click(screen.getByRole('button', { name: 'too junior' }))
  expect(await mainPart('Anzeigen ohne Score scoren (3)')).toBeVisible()
})

test('a picked "Alle" is dropped when its pass ends and the pool reloads', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  let polls = 0
  stubApi({ 'GET /pool': { body: NEXT() }, 'POST /pool/passes': { status: 202, body: { pass_id: 'ps1' } },
            'GET /pool/passes/ps1': () => ({ body: pass(++polls === 1 ? running('scoring', [4, 12]) : { status: 'done' }) }) })
  render(<PoolView />)
  await pickAll()
  await act(async () => (await mainPart('Alle Anzeigen neu scoren (12)')).click())
  await tick()
  await tick()
  expect(await mainPart('Anzeigen ohne Score scoren (3)')).toBeEnabled()
})

test('nothing without a score disables the main part with a reason, and the trigger stays enabled', async () => {
  stubApi({ 'GET /pool': { body: NEXT({ unscored: 0 }) } })
  render(<PoolView />)
  const main = await mainPart('Anzeigen ohne Score scoren (0)')
  expect(main).toHaveAttribute('aria-disabled', 'true')
  expect(main).toHaveAccessibleDescription('Es gibt keine Anzeigen ohne Score. Über den Pfeil wählst du „Alle Anzeigen neu scoren“.')
  expect(screen.getByRole('button', { name: 'Andere Variante wählen' })).toBeEnabled()
})

test('nothing to score at all says all postings are excluded or held back', async () => {
  stubApi({ 'GET /pool': { body: NEXT({ default: 'all', unscored: 0, all: 0 }) } })
  render(<PoolView />)
  const main = await mainPart('Alle Anzeigen neu scoren (0)')
  expect(main).toHaveAttribute('aria-disabled', 'true')
  expect(main).toHaveAccessibleDescription('Es gibt nichts zu scoren: Alle Anzeigen sind ausgeschlossen oder zurückgehalten.')
  expect(screen.getByRole('button', { name: 'Andere Variante wählen' })).toBeEnabled()
})

test('while a pass computes the split button is out of the way and its cancel button takes the place', async () => {
  await openRunning(running('scoring', [2, 12]))
  expect(screen.queryByRole('button', { name: /Anzeigen ohne Score scoren/ })).toBeNull()
  expect(screen.queryByRole('button', { name: 'Andere Variante wählen' })).toBeNull()
  expect(splitGroup()).toHaveAttribute('inert')
  expect(screen.getByRole('button', { name: 'Scoren abbrechen' })).toBeVisible()
  expect(document.getElementById('pass-why')).toBeNull()
})

test('while a pass waits for the answer both parts are disabled and say a pass runs', async () => {
  await openQuestion()
  const main = screen.getByRole('button', { name: /Anzeigen ohne Score scoren/ })
  expect(main).toHaveAttribute('aria-disabled', 'true')
  expect(main).toHaveAccessibleDescription('Das Scoren läuft.')
  expect(screen.getByRole('button', { name: 'Andere Variante wählen' })).toBeDisabled()
})

test('the split button and its open menu have no accessibility violations', async () => {
  stubApi({ 'GET /pool': { body: NEXT() } })
  render(<PoolView />)
  await mainPart(/Anzeigen ohne Score scoren/)
  await openMenu()
  // The portal sits outside the app shell's landmarks, which the "region" rule would flag.
  expect(await axe(document.body, { rules: { region: { enabled: false } } })).toHaveNoViolations()
})

test('a pass shows its progress, then reloads the pool when done', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  let polls = 0
  let reloads = 0
  const calls = stubApi({
    'GET /pool': () => {
      reloads += 1
      return { body: reloads === 1 ? POOL : poolWith({ next_pass: { default: 'unscored', unscored: 0, all: 0 } }) }
    },
    'POST /pool/passes': { status: 202, body: { pass_id: 'ps1' } },
    'GET /pool/passes/ps1': () => ({ body: pass(++polls === 1 ? running('scoring', [4, 12]) : { status: 'done' }) }),
  })
  render(<PoolView />)
  const button = await screen.findByRole('button', { name: 'Anzeigen ohne Score scoren (12)' })
  await act(async () => button.click())
  expect(button).toHaveAttribute('aria-disabled', 'true')
  expect(splitGroup()).toHaveAttribute('inert')
  // Before the first poll the progress is there, without counts, with the cancel button.
  expect(screen.getByText('Scoren läuft: Anzeigen prüfen…')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Scoren abbrechen' })).toBeVisible()
  await tick()
  expect(screen.getByText('Scoren läuft: 4 von 12')).toBeVisible()
  // The counts change every poll, so they stay out of the live region.
  expect(screen.getByText('Scoren läuft: 4 von 12').closest('[role="status"]')).toBeNull()
  await tick()
  expect(screen.queryByText(/Scoren läuft/)).toBeNull()
  expect(await screen.findByRole('button', { name: 'Anzeigen ohne Score scoren (0)' })).toHaveAttribute('aria-disabled', 'true')
  expect(calls.filter((call) => call.path === '/pool')).toHaveLength(2)
  expect(sessionStorage.length).toBe(0)
})

test('a stored pass resumes polling after a reload', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem('jobadvaisor.pool-pass', 'ps1')
  stubApi({ 'GET /pool': { body: POOL }, 'GET /pool/passes/ps1': { body: running('scoring', [7, 12]) } })
  render(<PoolView />)
  await loaded()
  await tick()
  expect(screen.getByText('Scoren läuft: 7 von 12')).toBeVisible()
})

test('starting while another pass runs says so', async () => {
  stubApi({ 'GET /pool': { body: POOL },
            'POST /pool/passes': { status: 409, body: { error: 'pass in progress', detail: 'x' } } })
  render(<PoolView />)
  await userEvent.click(await screen.findByRole('button', { name: 'Anzeigen ohne Score scoren (12)' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Es wird schon gescort. Warte, bis das fertig ist.')
})

const QUESTION = pass({ status: 'awaiting_answer', unscreened: [
  { posting_id: 'u1', title: 'Ungeprüfte Stelle (m/w/d)', company: 'Nordblatt' }] })

async function openQuestion(answers: Record<string, unknown> = {}) {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem('jobadvaisor.pool-pass', 'ps1')
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'GET /pool/passes/ps1': { body: QUESTION },
                          'POST /pool/passes/ps1/unscreened': { status: 202, body: { pass_id: 'ps1' } }, ...answers })
  const view = render(<PoolView />)
  await loaded()
  await tick()
  return { calls, ...view }
}

test('the unscreened question names the postings and sends continue', async () => {
  const { calls } = await openQuestion()
  expect(screen.getByText('Ungeprüfte Stelle (m/w/d)')).toBeVisible()
  expect(screen.getByText(/Nordblatt/, { selector: 'li' })).toBeVisible()
  await act(async () => screen.getByRole('button', { name: 'Trotzdem scoren' }).click())
  expect(calls.find((call) => call.path.endsWith('/unscreened'))!.body).toEqual({ continue: true })
  expect(screen.queryByRole('button', { name: 'Trotzdem scoren' })).toBeNull()
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
  expect(screen.getByText('Das Scoren wurde abgebrochen.')).toBeVisible()
})

test('an aborted pass is announced', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem('jobadvaisor.pool-pass', 'ps1')
  stubApi({ 'GET /pool': { body: POOL }, 'GET /pool/passes/ps1': { body: pass({ status: 'aborted' }) } })
  render(<PoolView />)
  await loaded()
  await tick()
  expect(screen.getByText('Das Scoren wurde abgebrochen.')).toBeVisible()
  expect(screen.getByRole('button', { name: /Anzeigen ohne Score scoren/ })).toBeEnabled()
})

// --- progress beside the pass button and cancel ---------------------------------------------

const CANCEL_ROUTE = { 'POST /pool/passes/ps1/cancel': { status: 202, body: { pass_id: 'ps1' } } }
const HINT = 'Abbrechen hält nach der aktuellen Anzeige an. Was schon gescort ist, bleibt gespeichert.'
const STOPPING = 'Wird nach der aktuellen Anzeige beendet.'
const STORING = 'Das Speichern lässt sich nicht mehr abbrechen.'
const cancelCalls = (calls: Call[]) => calls.filter((call) => call.path === '/pool/passes/ps1/cancel')

/** A view whose stored pass `ps1` answers `answer()` per poll; waits for the first poll. */
async function openRunning(answer: PassState | (() => PassState), extra: Parameters<typeof stubApi>[0] = {}) {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem('jobadvaisor.pool-pass', 'ps1')
  const calls = stubApi({ 'GET /pool': { body: POOL },
                          'GET /pool/passes/ps1': () => ({ body: typeof answer === 'function' ? answer() : answer }), ...extra })
  const view = render(<PoolView />)
  await loaded()
  await tick()
  return { calls, ...view }
}

const block = () => screen.getByRole('region', { name: 'Stand des Scorens' })
const cancelButton = (name = 'Scoren abbrechen') => screen.getByRole('button', { name })
const bar = () => within(block()).getByRole('progressbar')
/** What must not change from phase to phase: the block's structure and the classes of its fixed boxes. */
const shape = () => JSON.stringify({
  children: Array.from(block().children).map((child) => [child.tagName, child.className.split(' ').filter((name) => /(^|:)(h-|w-)/.test(name))]),
  root: block().className.split(' ').filter((name) => /(^|:)w-/.test(name)),
})

test('scoring shows the count in the head and on the bar', async () => {
  await openRunning(running('scoring', [12, 80]))
  expect(screen.getByText('Scoren läuft: 12 von 80')).toBeVisible()
  expect(bar()).toHaveAccessibleName('Scoren: 12 von 80')
  expect(bar()).toHaveAttribute('value', '12')
  expect(bar()).toHaveAttribute('max', '80')
  expect(block()).toHaveTextContent(HINT)
})

test.each([['checking', running('checking')], ['a missing report', pass({})]])(
  '%s shows no count and an empty bar', async (_name, state) => {
    await openRunning(state)
    expect(screen.getByText('Scoren läuft: Anzeigen prüfen…')).toBeVisible()
    expect(block().textContent).not.toMatch(/\bvon\b/)
    expect(bar()).toHaveAttribute('value', '0')
    expect(bar()).toHaveAccessibleName('Anzeigen prüfen')
  })

test('storing says so and fills the bar', async () => {
  await openRunning(running('storing', [80, 80]))
  expect(screen.getByText('Scores werden gespeichert')).toBeVisible()
  expect(bar()).toHaveAttribute('value', '80')
  expect(bar()).toHaveAttribute('max', '80')
  expect(bar()).toHaveAccessibleName('Scoren: 80 von 80')
})

test('after a cancel the full storing bar is named with the real count, not with the total', async () => {
  await openRunning(running('storing', [2, 4], { cancel_requested: true }))
  expect(bar()).toHaveAttribute('value', '4')
  expect(bar()).toHaveAttribute('max', '4')
  expect(bar()).toHaveAccessibleName('Scoren: 2 von 4')
})

test('the count moves between two polls, outside the live region', async () => {
  let done = 12
  await openRunning(() => running('scoring', [done, 80]))
  expect(screen.getByText('Scoren läuft: 12 von 80')).toBeVisible()
  done = 13
  await tick()
  expect(screen.getByText('Scoren läuft: 13 von 80')).toBeVisible()
  expect(bar()).toHaveAttribute('value', '13')
  expect(block().closest('[role="status"]')).toBeNull()
})

test('the progress block keeps its structure and its fixed boxes in every phase, also after a cancel request and while storing', async () => {
  let current = running('checking')
  await openRunning(() => current, CANCEL_ROUTE)
  const first = shape()
  expect(first).toContain('h-10')
  for (const next of [running('scoring', [0, 80]), running('scoring', [30, 79]),
                      running('scoring', [30, 79], { cancel_requested: true }), running('storing', [79, 79])]) {
    current = next
    await tick()
    expect(shape()).toEqual(first)
  }
})


test('the progress block fills the pass column and sets no width of its own', async () => {
  await openRunning(running('scoring', [30, 79]))
  expect(block().parentElement!.parentElement).toBe(passColumn())
  expect(block()).toHaveClass('w-full', 'min-w-0')
  expect(block().className).not.toMatch(/sm:flex-/)
})

test('the cancel button shares the split button\'s grid cell, so the width stays', async () => {
  await openRunning(running('scoring', [30, 79]))
  expect(cancelButton().parentElement).toBe(splitGroup().parentElement)
  for (const element of [cancelButton(), splitGroup()]) expect(element).toHaveClass('col-start-1', 'row-start-1')
  expect(splitGroup()).toHaveClass('invisible')
  expect(splitGroup()).toHaveAttribute('inert')
})

test('a running pass offers a cancel button, and a press cancels at once without a dialog', async () => {
  const { calls } = await openRunning(running('scoring', [30, 79]), CANCEL_ROUTE)
  const cancel = cancelButton()
  expect(cancel).not.toHaveAttribute('aria-disabled')
  // jsdom applies no Tailwind, so the phone and the desktop text of the hint both count here.
  expect(cancel).toHaveAccessibleDescription(expect.stringContaining(HINT))
  await act(async () => cancel.click())
  expect(cancelCalls(calls)).toHaveLength(1)
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(cancel).toHaveAttribute('aria-disabled', 'true')
  expect(cancel).toHaveAccessibleName('Wird beendet…')
  expect(cancel).toHaveAccessibleDescription(STOPPING)
  expect(screen.getByText('Das Scoren wird nach der aktuellen Anzeige beendet.').closest('[role="status"]')).not.toBeNull()
})

test('the cancel request holds when a poll that started before it answers without it', async () => {
  await openRunning(running('scoring', [30, 79]), CANCEL_ROUTE)
  await act(async () => cancelButton().click())
  await tick()
  expect(cancelButton('Wird beendet…')).toHaveAttribute('aria-disabled', 'true')
  expect(screen.getByText(STOPPING)).toBeVisible()
})

test('a pass the server reports as cancel_requested shows the same state after a reload', async () => {
  await openRunning(running('scoring', [30, 79], { cancel_requested: true }))
  expect(cancelButton('Wird beendet…')).toHaveAttribute('aria-disabled', 'true')
  expect(screen.getByText(STOPPING)).toBeVisible()
})

test('a 409 on the cancel request shows no error, another failure shows its text and keeps the button', async () => {
  let status = 409
  await openRunning(running('scoring', [30, 79]), {
    'POST /pool/passes/ps1/cancel': () => ({ status, body: { error: 'pass not running', detail: 'x' } }) })
  const cancel = cancelButton()
  await act(async () => cancel.click())
  expect(screen.queryByRole('alert')).toBeNull()
  status = 500
  await act(async () => cancel.click())
  expect(screen.getByRole('alert')).toHaveTextContent('Das Scoren konnte nicht abgebrochen werden. Versuch es noch einmal.')
  expect(cancel).not.toHaveAttribute('aria-disabled')
  expect(screen.queryByText(STOPPING)).toBeNull()
})

test('while a pass waits for the unscreened answer there is no cancel button', async () => {
  await openQuestion()
  expect(screen.queryByRole('button', { name: 'Scoren abbrechen' })).toBeNull()
  expect(screen.queryByRole('region', { name: 'Stand des Scorens' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Abbrechen' })).toBeVisible()
})

test('while a pass stores the button keeps its label and is inert, and the hint says why', async () => {
  const { calls } = await openRunning(running('storing', [80, 80]), CANCEL_ROUTE)
  await titles()
  const cancel = cancelButton()
  expect(cancel).toHaveAttribute('aria-disabled', 'true')
  expect(cancel).toHaveAccessibleDescription(STORING)
  expect(screen.getByText(STORING)).toBeVisible()
  act(() => cancel.focus())
  await act(async () => cancel.click())
  await userEvent.keyboard('{Enter}')
  expect(cancelCalls(calls)).toHaveLength(0)
  expect(cancel).toHaveFocus()
  expect(document.getElementById('row-p3')).not.toHaveFocus()
})

test('Enter on the focused cancel button cancels and does not move the row selection', async () => {
  const { calls } = await openRunning(running('scoring', [30, 79]), CANCEL_ROUTE)
  await titles()
  act(() => cancelButton().focus())
  await userEvent.keyboard('{Enter}')
  await vi.waitFor(() => expect(cancelCalls(calls)).toHaveLength(1))
  expect(document.getElementById('row-p3')).not.toHaveFocus()
})

test('once a cancel is requested the button is inert to click and Enter and keeps focus', async () => {
  const { calls } = await openRunning(running('scoring', [30, 79]), CANCEL_ROUTE)
  await titles()
  const cancel = cancelButton()
  act(() => cancel.focus())
  await userEvent.keyboard('{Enter}')
  await vi.waitFor(() => expect(cancel).toHaveAttribute('aria-disabled', 'true'))
  expect(cancel).toHaveFocus()
  await userEvent.keyboard('{Enter}')
  await act(async () => cancel.click())
  expect(cancelCalls(calls)).toHaveLength(1)
  expect(cancel).toHaveFocus()
  expect(document.getElementById('row-p3')).not.toHaveFocus()
})

test.each([['running', () => running('scoring', [30, 79])], ['cancel-requested', () => running('scoring', [30, 79], { cancel_requested: true })],
           ['storing', () => running('storing', [80, 80])]])(
  'the %s state has no accessibility violations', async (_name, state) => {
    const { container } = await openRunning(state(), CANCEL_ROUTE)
    vi.useRealTimers()
    expect(await axe(container)).toHaveNoViolations()
  })

// --- the swap delay -------------------------------------------------------------------------

/** Every timer a swap test needs: the poll interval and the 1 s swap delay. */
const FAKE_ALL = { toFake: ['setInterval' as const, 'clearInterval' as const, 'setTimeout' as const, 'clearTimeout' as const] }
/** Run out the swap delay without a poll's worth of difference: poll and delay both last 1 s. */
const unlock = () => act(() => vi.advanceTimersByTimeAsync(SWAP_LOCK_MS))

/** A pool with a startable pass `ps1` that runs until `end()` is called, then answers `finished`;
 * timers are fake from here on (so no `findBy` or `userEvent` after this: use `act`). */
async function openStartable(finished: PassState = pass({ status: 'done' })) {
  let ended = false
  const calls = stubApi({ 'GET /pool': { body: NEXT() }, 'POST /pool/passes': { status: 202, body: { pass_id: 'ps1' } },
                          'GET /pool/passes/ps1': () => ({ body: ended ? finished : running('scoring', [5, 12]) }),
                          ...CANCEL_ROUTE })
  render(<PoolView />)
  const main = await mainPart('Anzeigen ohne Score scoren (3)')
  vi.useFakeTimers(FAKE_ALL)
  return { calls, main, end: () => { ended = true } }
}

test('a second press within 1 s of the start sends no cancel, and focus follows to the new button', async () => {
  const { calls, main } = await openStartable()
  act(() => main.focus())
  await act(async () => main.click())
  const cancel = cancelButton()
  expect(cancel).toHaveFocus()
  expect(cancel).toHaveAttribute('aria-disabled', 'true')
  await act(async () => cancel.click())
  expect(cancelCalls(calls)).toHaveLength(0)
  await unlock()
  expect(cancel).not.toHaveAttribute('aria-disabled')
  await act(async () => cancel.click())
  expect(cancelCalls(calls)).toHaveLength(1)
})

test('a press within 1 s of the end starts no pass, and focus follows to the pass button', async () => {
  const { calls, main, end } = await openStartable()
  await act(async () => main.click())
  await unlock()
  const cancel = cancelButton()
  act(() => cancel.focus())
  end()
  await tick()
  await act(async () => {})
  expect(main).toHaveAttribute('aria-disabled', 'true')
  expect(main).toHaveFocus()
  expect(splitGroup()).not.toHaveAttribute('inert')
  await act(async () => main.click())
  expect(posts(calls)).toHaveLength(1)
  await unlock()
  expect(main).not.toHaveAttribute('aria-disabled')
  await act(async () => main.click())
  expect(posts(calls)).toHaveLength(2)
})

test('the swap delay leaves the focus alone when the old button had none', async () => {
  const { main } = await openStartable()
  await act(async () => main.click())
  expect(cancelButton()).not.toHaveFocus()
})

// --- focus in the button area (a real browser blurs what turns disabled or inert, jsdom does not;
// the e2e walkthrough covers that, these pin where focus is sent and that nothing is `disabled`) ---

test('a main part without postings is aria-disabled, not disabled: it keeps focus and a press starts nothing', async () => {
  const calls = stubApi({ 'GET /pool': { body: NEXT({ unscored: 0 }) } })
  render(<PoolView />)
  const main = await mainPart('Anzeigen ohne Score scoren (0)')
  expect(main).not.toHaveAttribute('disabled')
  await titles()
  act(() => main.focus())
  await userEvent.keyboard('{Enter}')
  await userEvent.click(main)
  expect(posts(calls)).toHaveLength(0)
  expect(main).toHaveFocus()
  expect(document.getElementById('row-p3')).not.toHaveFocus()
})

test('a pass that ends with nothing left to score leaves focus on the pass button, and Enter there starts nothing', async () => {
  let reloads = 0
  const calls = stubApi({
    'GET /pool': () => ({ body: ++reloads === 1 ? NEXT() : NEXT({ unscored: 0 }) }),
    'POST /pool/passes': { status: 202, body: { pass_id: 'ps1' } },
    'GET /pool/passes/ps1': () => ({ body: reloads > 1 ? pass({ status: 'done' }) : running('scoring', [5, 12]) }),
  })
  render(<PoolView />)
  const main = await mainPart('Anzeigen ohne Score scoren (3)')
  vi.useFakeTimers(FAKE_ALL)
  act(() => main.focus())
  await act(async () => main.click())
  const cancel = cancelButton()
  act(() => cancel.focus())
  await unlock()
  reloads = 2
  await tick()
  await act(async () => {})
  expect(main).toHaveAccessibleName('Anzeigen ohne Score scoren (0)')
  expect(main).toHaveFocus()
  await act(async () => main.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })))
  expect(posts(calls)).toHaveLength(1)
  expect(document.getElementById('row-p3')).not.toHaveFocus()
})

test('a pass that stops at the unscreened question takes focus from the cancel button to the question, not to a button', async () => {
  let asking = false
  await openRunning(() => (asking ? QUESTION : running('scoring', [5, 12])))
  await titles()
  act(() => cancelButton().focus())
  asking = true
  await tick()
  const heading = document.getElementById('unscreened-title')!
  expect(heading).toHaveAttribute('tabindex', '-1')
  expect(heading).toHaveFocus()
})

test('answering "Trotzdem scoren" with focus on it moves focus to the cancel button, not to body', async () => {
  await openQuestion()
  act(() => screen.getByRole('button', { name: 'Trotzdem scoren' }).focus())
  await act(async () => screen.getByRole('button', { name: 'Trotzdem scoren' }).click())
  expect(screen.queryByRole('button', { name: 'Trotzdem scoren' })).toBeNull()
  expect(cancelButton()).toHaveFocus()
})

test('answering with "Abbrechen" moves focus to the cancel button and, once the aborted pass has ended, to the pass button', async () => {
  let aborted = false
  await openQuestion({
    'GET /pool/passes/ps1': () => ({ body: aborted ? pass({ status: 'aborted' }) : QUESTION }),
    'POST /pool/passes/ps1/unscreened': () => {
      aborted = true
      return { status: 202, body: { pass_id: 'ps1' } }
    } })
  act(() => screen.getByRole('button', { name: 'Abbrechen' }).focus())
  await act(async () => screen.getByRole('button', { name: 'Abbrechen' }).click())
  expect(cancelButton()).toHaveFocus()
  await tick()
  expect(screen.getByRole('button', { name: /Anzeigen ohne Score scoren/ })).toHaveFocus()
})

test('an answer given with focus elsewhere moves no focus', async () => {
  await openQuestion()
  await act(async () => screen.getByRole('button', { name: 'Trotzdem scoren' }).click())
  expect(cancelButton()).not.toHaveFocus()
})

test('when the polls fail the focus moves from the cancel button to the pass button, which stays on the page', async () => {
  let down = false
  await openRunning(() => running('scoring', [5, 12]), {
    'GET /pool/passes/ps1': () => (down ? { status: 500 } : { body: running('scoring', [5, 12]) }) })
  await titles()
  act(() => cancelButton().focus())
  down = true
  await tick()
  await tick()
  await tick()
  const main = screen.getByRole('button', { name: /Anzeigen ohne Score scoren/ })
  expect(main).toHaveAttribute('aria-disabled', 'true')
  expect(main).toHaveFocus()
})

const CANCELLED = 'Das Scoren wurde abgebrochen.'

test.each([[30, `${CANCELLED} 30 Anzeigen haben einen neuen Score.`], [1, `${CANCELLED} 1 Anzeige hat einen neuen Score.`],
           [0, `${CANCELLED} Keine Anzeige hat einen neuen Score.`]])(
  'a cancelled pass with %i scored reloads the pool and says so in the status region', async (scored, text) => {
    const { calls } = await openRunning(pass({ status: 'cancelled', scored }))
    await vi.waitFor(() => expect(calls.filter((call) => call.path === '/pool')).toHaveLength(2))
    expect(screen.getByText(text).closest('[role="status"]')).not.toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByRole('region', { name: 'Stand des Scorens' })).toBeNull()
    expect(sessionStorage.length).toBe(0)
    expect(screen.getByRole('button', { name: /Anzeigen ohne Score scoren/ })).toBeEnabled()
  })

test('the cancelled notice goes when the next pass starts', async () => {
  const { calls, main, end } = await openStartable(pass({ status: 'cancelled', scored: 30 }))
  await act(async () => main.click())
  end()
  await tick()
  await act(async () => {})
  expect(screen.getByText(`${CANCELLED} 30 Anzeigen haben einen neuen Score.`)).toBeVisible()
  await unlock()
  await act(async () => main.click())
  expect(posts(calls)).toHaveLength(2)
  expect(screen.queryByText(/Das Scoren wurde abgebrochen/)).toBeNull()
})

test.each([[12, 'Das Scoren ist fertig. 12 Anzeigen haben einen neuen Score.'],
           [1, 'Das Scoren ist fertig. 1 Anzeige hat einen neuen Score.']])(
  'a finished pass with %i scored says so with a dismiss button, like the check report', async (scored, text) => {
    const { calls } = await openRunning(pass({ status: 'done', scored }))
    await vi.waitFor(() => expect(calls.filter((call) => call.path === '/pool')).toHaveLength(2))
    expect(screen.getByText(text).closest('[role="status"]')).not.toBeNull()
    await act(async () => screen.getByRole('button', { name: 'Meldung ausblenden' }).click())
    expect(screen.queryByText(text)).toBeNull()
  })

test.each([['done', 'Das Scoren ist fertig. 30 Anzeigen haben einen neuen Score.'],
           ['cancelled', `${CANCELLED} 30 Anzeigen haben einen neuen Score.`], ['aborted', CANCELLED]] as const)(
  'the notice of a %s pass stays over a reload until it is dismissed, like the check report', async (status, text) => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    sessionStorage.setItem('jobadvaisor.pool-pass', 'ps1')
    stubApi({ 'GET /pool': { body: POOL }, 'GET /pool/passes/ps1': { body: pass({ status, scored: 30 }) } })
    const first = render(<PoolView />)
    await loaded()
    await tick()
    expect(screen.getByText(text)).toBeVisible()
    first.unmount()
    const second = render(<PoolView />)
    await loaded()
    expect(screen.getByText(text)).toBeVisible()
    await act(async () => screen.getByRole('button', { name: 'Meldung ausblenden' }).click())
    expect(screen.queryByText(text)).toBeNull()
    second.unmount()
    render(<PoolView />)
    await loaded()
    expect(screen.queryByText(text)).toBeNull()
  })

test('a late answer of a poll that was still open does not bring a dismissed notice back', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem('jobadvaisor.pool-pass', 'ps1')
  let release: () => void = () => {}
  let polls = 0
  const cancelled = { body: pass({ status: 'cancelled', scored: 30 }) }
  stubApi({
    'GET /pool': { body: POOL },
    // The first poll hangs until released; the second answers at once.
    'GET /pool/passes/ps1': () => ++polls === 1 ? new Promise((resolve) => { release = () => resolve(cancelled) }) : cancelled,
  })
  render(<PoolView />)
  await loaded()
  await tick()
  await tick()
  const text = `${CANCELLED} 30 Anzeigen haben einen neuen Score.`
  expect(screen.getByText(text)).toBeVisible()
  await act(async () => screen.getByRole('button', { name: 'Meldung ausblenden' }).click())
  await act(async () => release())
  expect(screen.queryByText(text)).toBeNull()
  expect(localStorage.getItem('jobadvaisor.pool-pass-end')).toBeNull()
})

test('a failed pass shows an error with retry that starts a new pass', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem('jobadvaisor.pool-pass', 'ps1')
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'GET /pool/passes/ps1': { body: pass({ status: 'failed', error: 'labels/p1.json: kaputt' }) },
                          'POST /pool/passes': { status: 202, body: { pass_id: 'ps2' } } })
  render(<PoolView />)
  await loaded()
  await tick()
  expect(screen.getByRole('heading', { name: 'Das Scoren ist fehlgeschlagen' })).toBeVisible()
  expect(screen.getByText(/labels\/p1\.json: kaputt/)).toBeVisible()
  expect(screen.getByText(/kaputte Datei/)).toBeVisible()
  expect(screen.queryByText(/Server erreichbar/)).toBeNull()
  await act(async () => screen.getByRole('button', { name: 'Erneut versuchen' }).click())
  expect(posts(calls)).toHaveLength(1)
  expect(posts(calls)[0].body).toEqual({ variant: 'unscored' })
})

test('the retry of a failed pass starts the variant the main part shows, not the one the pass was started with', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  let failed = false
  const calls = stubApi({ 'GET /pool': { body: NEXT() }, 'POST /pool/passes': { status: 202, body: { pass_id: 'ps1' } },
                          'GET /pool/passes/ps1': () => ({ body: failed ? pass({ status: 'failed', error: 'kaputt' }) : running('checking') }) })
  const { unmount } = render(<PoolView />)
  await pickAll()
  await act(async () => (await mainPart('Alle Anzeigen neu scoren (12)')).click())
  unmount()
  failed = true
  render(<PoolView />)
  await loaded()
  await tick()
  await act(async () => screen.getByRole('button', { name: 'Erneut versuchen' }).click())
  expect(posts(calls)).toHaveLength(2)
  expect(posts(calls)[1].body).toEqual({ variant: 'unscored' })
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
  const failed = await screen.findByText('Der Bewerbungsstatus wurde nicht gespeichert.')
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
  await loaded()
  await tick()
  await tick()
  expect(screen.queryByText('Der Stand des Scorens ist gerade nicht abrufbar')).toBeNull()
  await tick()
  expect(screen.getByText('Der Stand des Scorens ist gerade nicht abrufbar')).toBeVisible()
  expect(screen.getByRole('button', { name: /Anzeigen ohne Score scoren/ })).toHaveAttribute('aria-disabled', 'true')
  const polls = calls.filter((call) => call.path === '/pool/passes/ps1').length
  await tick()
  expect(calls.filter((call) => call.path === '/pool/passes/ps1')).toHaveLength(polls)
  down = false
  await act(async () => screen.getByRole('button', { name: 'Erneut versuchen' }).click())
  await tick()
  expect(screen.queryByText('Der Stand des Scorens ist gerade nicht abrufbar')).toBeNull()
  expect(await screen.findByRole('button', { name: /Anzeigen ohne Score scoren/ })).toBeEnabled()
})

test('a failed reload keeps the list and shows a retry above it', async () => {
  let reloads = 0
  stubApi({ 'GET /pool': () => (++reloads === 2 ? { status: 500 } : { body: POOL }) })
  const view = render(<PoolView />)
  await titles()
  view.rerender(<PoolView reloadKey={1} />)
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
  expect(screen.getByText(`${count} Korrekturen`)).toBeVisible()

test('a chip on a posting without a verdict gives it the derived verdict and the counter follows', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': rateRoute('p2') })
  render(<PoolView />)
  await titles()
  await userEvent.click(within(screen.getByRole('list', { name: 'Anzeigen' })).getAllByRole('button', { name: 'great stack' })[0])
  expect(puts(calls)[0].body).toEqual({ chips: ['great-stack'], note: null })
  expect(await row(ENGINEER).findByText('Bewertet: Ja')).toBeVisible()
  expect(screen.getByText('neu scoren sinnvoll')).toBeVisible()
  expect(screen.getByText('4 Korrekturen')).toBeVisible()
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
  expect(below.parentElement).toBe(row(ENGINEER).getByRole('combobox', { name: /Bewerbungsstatus/ }).closest('li'))
  expect(below).toHaveClass('basis-full')
  const status = row(ENGINEER).getByRole('combobox', { name: /Bewerbungsstatus/ })
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
  expect(await screen.findByText(`${ENGINEER}: Bewerbungsstatus beworben. Die Anzeige ist nicht mehr in dieser Ansicht.`)).toBeInTheDocument()
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
  const quiet = poolWith({ next_pass: { default: 'unscored', unscored: 0, all: 0 } })
  const calls = stubApi({ 'GET /pool': { body: quiet }, 'POST /postings/n1/score': { body: scoreAnswer(
    baseRow('n1'), { state: 'scored', score: 9 }, { counter: { ...POOL.counter, corrections: 4 },
      next_pass: { default: 'all', unscored: 0, all: 8 } }) } })
  render(<PoolView />)
  await titles()
  expect(await screen.findByRole('button', { name: 'Anzeigen ohne Score scoren (0)' })).toHaveAttribute('aria-disabled', 'true')
  await userEvent.click(row(NEW).getByRole('button', { name: 'Score berechnen' }))
  expect(await row(NEW).findByText('9')).toBeVisible()
  expect(row(NEW).getByRole('button', { name: 'Neu berechnen' })).toBeEnabled()
  expect(screen.getByText('4 Korrekturen')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Alle Anzeigen neu scoren (8)' })).toBeEnabled()
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
    'GET /pool/passes/ps1': () => ({ body: pass(++polls === 1 ? running('scoring', [4, 12]) : { status: 'done' }) }),
    'POST /postings/n1/score': { status: 409, body: { error: 'scoring in progress', detail: 'ps1' } },
    'POST /postings/broken/score': { status: 502, body: { error: 'scoring failed', detail: 'x' } } })
  render(<PoolView />)
  const start = await screen.findByRole('button', { name: 'Anzeigen ohne Score scoren (12)' })
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

test('a chip answering after the range changed does not bring its row back into the range', async () => {
  const held = late()
  stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p3/rating': held.answer })
  render(<PoolView />)
  await titles()
  await userEvent.selectOptions(von(), '3')
  await userEvent.selectOptions(bis(), '3')
  expect(await titles()).toEqual(['Datenjournalist (m/w/d)'])
  await userEvent.click(button('great stack'))
  await userEvent.selectOptions(von(), '7')
  await userEvent.selectOptions(bis(), '9')
  expect(await titles()).toEqual([DATA_ANALYST, ENGINEER])
  const body = { chips: ['great-stack'], note: null }
  await act(async () => held.release(ratingAnswer(baseRow('p3'), body, AFTER)))
  await vi.waitFor(() => corrections(4))
  expect(await titles()).toEqual([DATA_ANALYST, ENGINEER])
})

test('a level click that sends nothing does not let a pending score bring its row back', async () => {
  const held = late()
  const strong = { ...baseRow('p1'), label: label('positive', ['great-stack'], 'strong') }
  stubApi({ 'GET /pool': { body: poolWith({ rows: POOL.rows.map((entry) => (entry.posting_id === 'p1' ? strong : entry)) }) },
    'POST /postings/p1/score': held.answer })
  render(<PoolView />)
  await titles()
  await userEvent.selectOptions(von(), '7')
  await userEvent.selectOptions(bis(), '9')
  await userEvent.click(row(DATA_ANALYST).getByRole('button', { name: 'Neu berechnen' }))
  await userEvent.selectOptions(von(), '8')
  expect(await titles()).toEqual([DATA_ANALYST])
  await userEvent.click(button(`Ja, auf jeden Fall: ${DATA_ANALYST}`))
  await act(async () => held.release({ body: scoreAnswer(strong, { score: 3 }, { counter: AFTER }) }))
  await vi.waitFor(() => corrections(4))
  expect(screen.queryByRole('heading', { name: DATA_ANALYST })).toBeNull()
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
    'GET /pool/passes/ps1': { body: pass({ status: 'done' }) },
  })
  render(<PoolView />)
  await titles()
  await act(async () => { fireEvent.change(bis(), { target: { value: String(-1) } }) })
  expect(await titles()).toEqual([NEW, 'Buchhalter (m/w/d)'])
  await act(async () => button(`Ja, auf jeden Fall: ${NEW}`).click())
  await vi.waitFor(() => corrections(4))
  await act(async () => button('Anzeigen ohne Score scoren (12)').click())
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

test('"Filter zurücksetzen" resets the range as well and keeps the sort, visible in the order', async () => {
  const rows = [
    makeRow('a', 'Mitte (m/w/d)', { score: 1, added_at: '2026-10-02T08:00:00+00:00' }),
    makeRow('b', 'Neu (m/w/d)', { score: 5, added_at: '2026-10-03T08:00:00+00:00' }),
    makeRow('c', 'Alt (m/w/d)', { score: 6, added_at: '2026-10-01T08:00:00+00:00' }),
  ]
  stubApi({ 'GET /pool': { body: poolWith({ rows }) } })
  render(<PoolView />)
  expect(await titles()).toEqual(['Mitte (m/w/d)', 'Neu (m/w/d)', 'Alt (m/w/d)'])
  await userEvent.selectOptions(sortSelect(), 'added-asc')
  await userEvent.selectOptions(von(), '3')
  await userEvent.selectOptions(bis(), '3')
  await userEvent.click(await screen.findByRole('button', { name: 'Filter zurücksetzen' }))
  expect(await titles()).toEqual(['Alt (m/w/d)', 'Mitte (m/w/d)', 'Neu (m/w/d)'])
  expect(von()).toHaveValue('-1')
  expect(bis()).toHaveValue('10')
  expect(sortSelect()).toHaveValue('added-asc')
})

test('picking "Rangfolge" again after another sort brings the server order back', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  const ranked = await titles()
  await userEvent.selectOptions(sortSelect(), 'score-asc')
  expect(await titles()).not.toEqual(ranked)
  await userEvent.selectOptions(sortSelect(), 'rank')
  expect(await titles()).toEqual(ranked)
})

test('a status change still removes a row rated here from the list it no longer fits', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'PUT /postings/p2/rating': rateRoute('p2'), 'PATCH /postings/p2': { body: {} } })
  render(<PoolView />)
  await titles()
  await userEvent.click(button('Noch nicht bewertet'))
  await userEvent.selectOptions(von(), '7')
  await userEvent.selectOptions(bis(), '9')
  expect(await titles()).toEqual([ENGINEER])
  await userEvent.click(button(`Ja, auf jeden Fall: ${ENGINEER}`))
  await vi.waitFor(() => corrections(4))
  expect(await titles()).toEqual([ENGINEER])
  await userEvent.selectOptions(row(ENGINEER).getByRole('combobox', { name: /Bewerbungsstatus/ }), 'applied')
  await vi.waitFor(() => expect(screen.queryByText(ENGINEER)).toBeNull())
})

test('a status change removes a row scored here that lies outside the range', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'PATCH /postings/n1': { body: {} },
    'POST /postings/n1/score': { body: scoreAnswer(baseRow('n1'), { state: 'scored', score: 9 }, { counter: AFTER }) } })
  render(<PoolView />)
  await titles()
  await userEvent.click(button('Noch nicht bewertet'))
  await userEvent.selectOptions(bis(), NO_SCORE)
  await userEvent.click(row(NEW).getByRole('button', { name: 'Score berechnen' }))
  await vi.waitFor(() => corrections(4))
  expect(await titles()).toContain(NEW) // 9 lies outside "ohne Score": the row stays only as touched
  await userEvent.selectOptions(row(NEW).getByRole('combobox', { name: /Bewerbungsstatus/ }), 'applied')
  await vi.waitFor(() => expect(screen.queryByText(NEW)).toBeNull())
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

// --- the pool head: two columns (3.2) ---------------------------------------------------------

const passColumn = () => splitGroup().closest('[data-column="pass"]') as HTMLElement
const checkColumn = () => document.querySelector<HTMLElement>('[data-column="check"]')!
const checkStart = (name: string | RegExp = /Verfügbarkeit prüfen/) => screen.getByRole('button', { name })

test('the head has two columns: the pass with its counter line, and the check beside it', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await mainPart(/Anzeigen ohne Score scoren/)
  expect(passColumn()).not.toBeNull()
  expect(checkColumn()).not.toBeNull()
  expect(passColumn().parentElement).toBe(checkColumn().parentElement)
  expect(passColumn().nextElementSibling).toBe(checkColumn())
  expect(within(passColumn()).queryByRole('button', { name: /Verfügbarkeit prüfen/ })).toBeNull()
  expect(within(checkColumn()).getByRole('button', { name: 'Verfügbarkeit prüfen (8)' })).toBeVisible()
  expect(within(passColumn()).getByText('3 Korrekturen')).toBeVisible()
})

test('the counter line sits directly below the pass button and the cost line is gone', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await mainPart(/Anzeigen ohne Score scoren/)
  const line = screen.getByText('3 Korrekturen').parentElement!
  expect(splitGroup().compareDocumentPosition(line) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(line.previousElementSibling).toContainElement(splitGroup())
  expect(screen.queryByText(/je ein Modellaufruf/)).toBeNull()
  expect(document.getElementById('pass-why')).toBeNull()
  expect(screen.queryByText('Einstellungen')).toBeNull()
})

test('the main part has no description while it is usable, since the cost stays in the menu', async () => {
  stubApi({ 'GET /pool': { body: NEXT() } })
  render(<PoolView />)
  expect(await mainPart('Anzeigen ohne Score scoren (3)')).not.toHaveAccessibleDescription()
})

test('a pass without postings gives its reason in an info icon, which is focusable', async () => {
  stubApi({ 'GET /pool': { body: NEXT({ unscored: 0 }) } })
  render(<PoolView />)
  const main = await mainPart('Anzeigen ohne Score scoren (0)')
  const reason = 'Es gibt keine Anzeigen ohne Score. Über den Pfeil wählst du „Alle Anzeigen neu scoren“.'
  expect(main).toHaveAccessibleDescription(reason)
  const icon = screen.getByRole('button', { name: 'Warum ist Scoren nicht möglich?' })
  const tip = within(passColumn()).getByRole('tooltip', { hidden: true })
  expect(tip).not.toBeVisible()
  act(() => icon.focus())
  expect(tip).toHaveTextContent(reason)
  expect(tip).toBeVisible()
})

test('a rating key does not rate while the pass reason icon or the header settings link has focus', async () => {
  const calls = stubApi({ 'GET /pool': { body: NEXT({ unscored: 0 }) } })
  render(<><SettingsLink current={false} /><PoolView /></>)
  await mainPart('Anzeigen ohne Score scoren (0)')
  for (const control of [screen.getByRole('button', { name: 'Warum ist Scoren nicht möglich?' }),
                         screen.getByRole('link', { name: 'Einstellungen' })]) {
    act(() => control.focus())
    await userEvent.keyboard('1')
    expect(control).toHaveFocus()
  }
  expect(calls.filter((call) => call.method !== 'GET')).toEqual([])
})

test('starting a pass leaves the check button where it was, and the progress grows in the pass column', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  stubApi({ 'GET /pool': { body: NEXT() }, 'POST /pool/passes': { status: 202, body: { pass_id: 'ps1' } },
            'GET /pool/passes/ps1': () => ({ body: running('scoring', [4, 12]) }) })
  render(<PoolView />)
  const start = await mainPart('Anzeigen ohne Score scoren (3)')
  const before = checkStart()
  const column = checkColumn()
  await act(async () => start.click())
  await tick()
  expect(checkStart()).toBe(before)
  expect(checkColumn()).toBe(column)
  expect(within(passColumn()).getByRole('region', { name: 'Stand des Scorens' })).toBeVisible()
  expect(within(column).queryByRole('region', { name: 'Stand des Scorens' })).toBeNull()
})

test('the cancelled pass notice sits in the pass column', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem('jobadvaisor.pool-pass', 'ps1')
  stubApi({ 'GET /pool': { body: POOL }, 'GET /pool/passes/ps1': { body: pass({ status: 'cancelled', scored: 5 }) } })
  render(<PoolView />)
  await loaded()
  await tick()
  expect(within(passColumn()).getByText(`${CANCELLED} 5 Anzeigen haben einen neuen Score.`)).toBeVisible()
})

// --- the availability check (3.3) -------------------------------------------------------------

const CHECK_KEY = 'jobadvaisor.pool-check'
const CHECK_CANCEL = { 'POST /availability/checks/c1/cancel': { status: 202, body: { check_id: 'c1' } } }
const checkState = (changes: Partial<CheckState> = {}): CheckState => ({
  check_id: 'c1', status: 'running', error: null, total: 8, done: 3, cancel_requested: false,
  counts: { available: 2, closed: 1, unknown: 0 }, still_closed: 0,
  closed: [{ posting_id: 'p1', title: 'Data Analyst (m/w/d)', company: 'Grünwerk Solar' }], ...changes })
const closedOnes = (count: number) => Array.from({ length: count }, (_, index) => (
  { posting_id: `c${index}`, title: `Geschlossene Stelle ${index + 1}`, company: 'Nordblatt' }))
const finished = (closed: number, changes: Partial<CheckState> = {}) => checkState({
  status: 'done', done: 8, counts: { available: 4, closed, unknown: 2 }, closed: closedOnes(closed), ...changes })
const checkBlock = () => screen.getByRole('region', { name: 'Stand der Prüfung' })
const checkCalls = (calls: Call[]) => calls.filter((call) => call.method === 'POST' && call.path === '/availability/checks')
const CHECK_HINT = 'Abbrechen hält nach der aktuellen Anzeige an. Was schon geprüft ist, bleibt gespeichert.'

/** A view whose stored check `c1` answers `answer()` per poll; waits for the first poll. */
async function openCheck(answer: CheckState | (() => CheckState), extra: Parameters<typeof stubApi>[0] = {}) {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  localStorage.setItem(CHECK_KEY, 'c1')
  const calls = stubApi({ 'GET /pool': { body: POOL },
                          'GET /availability/checks/c1': () => ({ body: typeof answer === 'function' ? answer() : answer }), ...extra })
  const view = render(<PoolView />)
  await loaded()
  await tick()
  return { calls, ...view }
}

/** A view with a startable check `c1` (8 postings) that answers `answer()` once started. */
async function openStartableCheck(answer: () => CheckState, extra: Parameters<typeof stubApi>[0] = {}) {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'POST /availability/checks': { status: 202, body: { check_id: 'c1', total: 8 } },
                          'GET /availability/checks/c1': () => ({ body: answer() }), ...extra })
  render(<PoolView />)
  await loaded()
  return calls
}

test('the check button names how many postings the check covers', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  expect(await screen.findByRole('button', { name: 'Verfügbarkeit prüfen (8)' })).toBeEnabled()
  expect(screen.queryByRole('button', { name: 'Warum ist Prüfen nicht möglich?' })).toBeNull()
})

test('with nothing to check the button is inert and an info icon says why', async () => {
  const calls = stubApi({ 'GET /pool': { body: poolWith({ next_check: { total: 0 } }) } })
  render(<PoolView />)
  const button = await screen.findByRole('button', { name: 'Verfügbarkeit prüfen (0)' })
  const reason = 'Nichts zu prüfen: Keine offene Anzeige hat einen Link, den die Prüfung abrufen kann.'
  expect(button).toHaveAttribute('aria-disabled', 'true')
  expect(button).toHaveAccessibleDescription(reason)
  const icon = screen.getByRole('button', { name: 'Warum ist Prüfen nicht möglich?' })
  act(() => icon.focus())
  expect(within(checkColumn()).getByRole('tooltip')).toHaveTextContent(reason)
  expect(within(checkColumn()).getByRole('tooltip')).toBeVisible()
  await act(async () => button.click())
  expect(checkCalls(calls)).toHaveLength(0)
})

test('a press starts the check, shows its progress and offers the cancel button instead of a second start', async () => {
  let polls = 0
  const calls = await openStartableCheck(() => ++polls === 1 ? checkState() : checkState({ done: 5, counts: { available: 3, closed: 2, unknown: 0 } }))
  await act(async () => checkStart().click())
  expect(checkCalls(calls)).toHaveLength(1)
  expect(localStorage.getItem(CHECK_KEY)).toBe('c1')
  // Before the first poll the answer's total is shown.
  expect(screen.getByText('Verfügbarkeit: 0 von 8 geprüft')).toBeVisible()
  expect(within(checkColumn()).getByRole('button', { name: 'Prüfen abbrechen' })).toBeVisible()
  expect(screen.queryByRole('button', { name: /Verfügbarkeit prüfen \(/ })).toBeNull()
  await tick()
  expect(screen.getByText('Verfügbarkeit: 3 von 8 geprüft')).toBeVisible()
  expect(within(checkBlock()).getByRole('progressbar')).toHaveAccessibleName('Prüfung: 3 von 8')
  expect(within(checkBlock()).getByRole('progressbar')).toHaveAttribute('value', '3')
  expect(checkBlock()).toHaveTextContent(`1 geschlossen bisher. ${CHECK_HINT}`)
  await tick()
  expect(screen.getByText('Verfügbarkeit: 5 von 8 geprüft')).toBeVisible()
  expect(screen.getByText('Verfügbarkeit: 5 von 8 geprüft').closest('[role="status"]')).toBeNull()
  expect(checkCalls(calls)).toHaveLength(1)
})

test('the running check keeps the pass untouched, and its progress sits in the check column', async () => {
  await openCheck(checkState())
  expect(within(passColumn()).getByRole('button', { name: /Anzeigen ohne Score scoren/ })).toBeEnabled()
  expect(within(checkColumn()).getByRole('region', { name: 'Stand der Prüfung' })).toBeVisible()
})

test('a check that ends reloads the pool and shows its report with the closed postings linked', async () => {
  let reloads = 0
  const { calls } = await openCheck(() => finished(2), {
    'GET /pool': () => ({ body: ++reloads === 1 ? POOL : poolWith({ next_check: { total: 3 } }) }) })
  await titles()
  expect(calls.filter((call) => call.path === '/pool')).toHaveLength(2)
  const report = within(checkColumn()).getByRole('status')
  expect(within(report).getByRole('heading', { name: 'Prüfung fertig: 2 Stellen neu geschlossen' })).toBeVisible()
  const links = within(report).getAllByRole('link')
  expect(links.map((link) => link.textContent)).toEqual(['Geschlossene Stelle 1, Nordblatt', 'Geschlossene Stelle 2, Nordblatt'])
  expect(links[0]).toHaveAttribute('href', '#/anzeigen/c0')
  expect(report).toHaveTextContent('4 verfügbar. 2 blieben unbekannt, die nächste Prüfung versucht sie erneut.')
  expect(screen.queryByRole('region', { name: 'Stand der Prüfung' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Verfügbarkeit prüfen (3)' })).toBeEnabled()
  expect(localStorage.getItem(CHECK_KEY)).toBe('c1')
})

test('one closed posting and one unknown read in the singular', async () => {
  await openCheck(finished(1, { counts: { available: 6, closed: 1, unknown: 1 } }))
  expect(screen.getByRole('heading', { name: 'Prüfung fertig: 1 Stelle neu geschlossen' })).toBeVisible()
  expect(within(checkColumn()).getByRole('status')).toHaveTextContent('1 blieb unbekannt, die nächste Prüfung versucht sie erneut.')
})

test('postings that stay closed are counted in a sentence of their own, not in the head or the list', async () => {
  await openCheck(finished(3, { counts: { available: 4, closed: 3, unknown: 2 }, still_closed: 2, closed: closedOnes(1) }))
  const report = within(checkColumn()).getByRole('status')
  expect(within(report).getByRole('heading', { name: 'Prüfung fertig: 1 Stelle neu geschlossen' })).toBeVisible()
  expect(within(report).getAllByRole('link')).toHaveLength(1)
  expect(report).toHaveTextContent('4 verfügbar. 2 blieben unbekannt, die nächste Prüfung versucht sie erneut. 2 weiterhin geschlossen.')
})

test('only postings that stay closed: no new ones, and the sentence says how many stay', async () => {
  await openCheck(finished(2, { counts: { available: 6, closed: 2, unknown: 0 }, still_closed: 2, closed: [] }))
  const report = within(checkColumn()).getByRole('status')
  expect(within(report).getByRole('heading', { name: 'Prüfung fertig: 0 Stellen neu geschlossen' })).toBeVisible()
  expect(report).toHaveTextContent('6 verfügbar. 2 weiterhin geschlossen.')
  expect(within(report).queryByRole('list')).toBeNull()
})

test('the running hint counts only the newly closed postings', async () => {
  await openCheck(checkState({ counts: { available: 2, closed: 3, unknown: 0 }, still_closed: 2 }))
  expect(checkBlock()).toHaveTextContent(`1 geschlossen bisher. ${CHECK_HINT}`)
})

test('no unknown posting leaves out that sentence', async () => {
  await openCheck(finished(0, { counts: { available: 8, closed: 0, unknown: 0 } }))
  expect(screen.getByRole('heading', { name: 'Prüfung fertig: 0 Stellen neu geschlossen' })).toBeVisible()
  expect(within(checkColumn()).getByRole('status')).toHaveTextContent('8 verfügbar.')
  expect(within(checkColumn()).queryByText(/unbekannt/)).toBeNull()
})

test('the report links the first three closed postings and puts the rest behind a toggle', async () => {
  await openCheck(finished(5))
  const report = within(checkColumn()).getByRole('status')
  const toggle = within(report).getByText('2 weitere anzeigen')
  expect(toggle.tagName).toBe('SUMMARY')
  expect(within(report).getByRole('link', { name: 'Geschlossene Stelle 3, Nordblatt' })).toBeVisible()
  expect(within(report).getByRole('link', { name: 'Geschlossene Stelle 4, Nordblatt' })).not.toBeVisible()
  fireEvent.click(toggle)
  expect(within(report).getByRole('link', { name: 'Geschlossene Stelle 4, Nordblatt' })).toBeVisible()
  expect(within(report).getByRole('link', { name: 'Geschlossene Stelle 5, Nordblatt' })).toBeVisible()
})

test('three closed postings need no toggle', async () => {
  await openCheck(finished(3))
  expect(within(checkColumn()).queryByText(/weitere anzeigen/)).toBeNull()
})

test('the report can be dismissed, and the stored check goes with it', async () => {
  await openCheck(finished(2))
  await act(async () => screen.getByRole('button', { name: 'Bericht ausblenden' }).click())
  expect(within(checkColumn()).queryByText(/Prüfung fertig/)).toBeNull()
  expect(localStorage.getItem(CHECK_KEY)).toBeNull()
  expect(screen.getByRole('button', { name: /Verfügbarkeit prüfen \(/ })).toBeEnabled()
})

test('the report survives a reload while the server still knows the check', async () => {
  const first = await openCheck(finished(2))
  first.unmount()
  vi.unstubAllGlobals()
  await openCheck(finished(2))
  expect(screen.getByRole('heading', { name: 'Prüfung fertig: 2 Stellen neu geschlossen' })).toBeVisible()
})

test('a reload during a check shows its progress again', async () => {
  await openCheck(checkState({ done: 5 }))
  expect(screen.getByText('Verfügbarkeit: 5 von 8 geprüft')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Prüfen abbrechen' })).toBeVisible()
})

test('before the first poll of a restored check the progress has no count', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  localStorage.setItem(CHECK_KEY, 'c1')
  stubApi({ 'GET /pool': { body: POOL }, 'GET /availability/checks/c1': { body: checkState() } })
  render(<PoolView />)
  await loaded()
  expect(screen.getByText('Verfügbarkeit: Stand wird geladen…')).toBeVisible()
  expect(within(checkBlock()).getByRole('progressbar')).toHaveAttribute('value', '0')
  expect(checkBlock()).toHaveTextContent(CHECK_HINT)
})

test('a server that forgot the check says so and offers a new start', async () => {
  await openCheck(checkState(), { 'GET /availability/checks/c1': { status: 404, body: { error: 'not found', detail: 'x' } } })
  expect(within(checkColumn()).getByText(/Die Prüfung ist dem Server nicht mehr bekannt/)).toBeVisible()
  expect(screen.getByRole('button', { name: 'Verfügbarkeit prüfen (8)' })).toBeEnabled()
  expect(localStorage.getItem(CHECK_KEY)).toBeNull()
})

test('a start refused because a check runs follows that check', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  stubApi({ 'GET /pool': { body: POOL },
            'POST /availability/checks': { status: 409, body: { error: 'check in progress', detail: 'x', check_id: 'c9' } },
            'GET /availability/checks/c9': { body: checkState({ check_id: 'c9', done: 6 }) } })
  render(<PoolView />)
  await loaded()
  await act(async () => checkStart().click())
  expect(screen.queryByRole('alert')).toBeNull()
  expect(localStorage.getItem(CHECK_KEY)).toBe('c9')
  await tick()
  expect(screen.getByText('Verfügbarkeit: 6 von 8 geprüft')).toBeVisible()
})

test('a start that fails says so and keeps the button', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  stubApi({ 'GET /pool': { body: POOL }, 'POST /availability/checks': { status: 500 } })
  render(<PoolView />)
  await loaded()
  await act(async () => checkStart().click())
  expect(within(checkColumn()).getByRole('alert')).toHaveTextContent('Die Prüfung konnte nicht gestartet werden. Ist der Server erreichbar?')
  expect(checkStart()).not.toHaveAttribute('aria-disabled')
})

test('a failed check says so and a retry starts a new one', async () => {
  const { calls } = await openCheck(checkState({ status: 'failed', error: 'RuntimeError' }), {
    'POST /availability/checks': { status: 202, body: { check_id: 'c2', total: 8 } },
    'GET /availability/checks/c2': { body: checkState({ check_id: 'c2' }) } })
  const alert = within(checkColumn()).getByRole('alert')
  expect(alert).toHaveTextContent('Die Prüfung ist fehlgeschlagen')
  expect(localStorage.getItem(CHECK_KEY)).toBeNull()
  await act(async () => within(alert).getByRole('button', { name: 'Erneut versuchen' }).click())
  expect(checkCalls(calls)).toHaveLength(1)
  expect(localStorage.getItem(CHECK_KEY)).toBe('c2')
})

test('three failed polls show a notice with a retry that resumes polling', async () => {
  let fail = true
  await openCheck(checkState(), { 'GET /availability/checks/c1': () => (fail ? { status: 500 } : { body: checkState({ done: 7 }) }) })
  await tick()
  await tick()
  expect(within(checkColumn()).getByRole('alert')).toHaveTextContent('Der Stand der Prüfung ist gerade nicht abrufbar')
  fail = false
  await act(async () => within(checkColumn()).getByRole('button', { name: 'Erneut versuchen' }).click())
  await tick()
  expect(screen.getByText('Verfügbarkeit: 7 von 8 geprüft')).toBeVisible()
})

test('a press on the cancel button cancels at once without a dialog and says what happens', async () => {
  const { calls } = await openCheck(checkState(), CHECK_CANCEL)
  const cancel = screen.getByRole('button', { name: 'Prüfen abbrechen' })
  expect(cancel).toHaveAccessibleDescription(expect.stringContaining(CHECK_HINT))
  await act(async () => cancel.click())
  expect(calls.filter((call) => call.path === '/availability/checks/c1/cancel')).toHaveLength(1)
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(cancel).toHaveAccessibleName('Wird beendet…')
  expect(cancel).toHaveAttribute('aria-disabled', 'true')
  expect(checkBlock()).toHaveTextContent('Wird nach der aktuellen Anzeige beendet. Was schon geprüft ist, bleibt gespeichert.')
  await tick()
  expect(screen.getByRole('button', { name: 'Wird beendet…' })).toHaveAttribute('aria-disabled', 'true')
})

test('a cancel request the server reports shows the stopping state after a reload', async () => {
  await openCheck(checkState({ cancel_requested: true }))
  expect(screen.getByRole('button', { name: 'Wird beendet…' })).toHaveAttribute('aria-disabled', 'true')
})

test('a cancelled check reports what it found and says it was cancelled', async () => {
  let status: CheckState['status'] = 'running'
  let requested = false
  await openCheck(() => checkState({ status, cancel_requested: requested, done: 4,
                                     counts: { available: 2, closed: 2, unknown: 0 }, closed: closedOnes(2) }), CHECK_CANCEL)
  await act(async () => screen.getByRole('button', { name: 'Prüfen abbrechen' }).click())
  requested = true
  status = 'cancelled'
  await tick()
  expect(screen.getByRole('heading', { name: 'Prüfung abgebrochen: 2 Stellen neu geschlossen' })).toBeVisible()
  expect(within(checkColumn()).getAllByRole('link')).toHaveLength(2)
  expect(screen.getByRole('button', { name: /Verfügbarkeit prüfen \(/ })).toBeEnabled()
})

test('a check that finished although a cancel came with its last posting is a finished check', async () => {
  await openCheck(finished(2, { cancel_requested: true }))
  expect(screen.getByRole('heading', { name: 'Prüfung fertig: 2 Stellen neu geschlossen' })).toBeVisible()
  expect(screen.queryByText(/abgebrochen/)).toBeNull()
})

test('a 409 on the cancel request shows no error, another failure shows its text and keeps the button', async () => {
  let status = 409
  await openCheck(checkState(), { 'POST /availability/checks/c1/cancel': () => ({ status, body: { error: 'check not running', detail: 'x' } }) })
  const cancel = screen.getByRole('button', { name: 'Prüfen abbrechen' })
  await act(async () => cancel.click())
  expect(screen.queryByRole('alert')).toBeNull()
  status = 500
  await act(async () => cancel.click())
  expect(within(checkColumn()).getByRole('alert')).toHaveTextContent('Das Prüfen konnte nicht abgebrochen werden. Versuch es noch einmal.')
  expect(cancel).not.toHaveAttribute('aria-disabled')
})

test('the cancel button keeps the start button\'s grid cell, so the width stays', async () => {
  await openCheck(checkState())
  const cancel = screen.getByRole('button', { name: 'Prüfen abbrechen' })
  const start = document.querySelector<HTMLElement>('[data-column="check"] button[aria-hidden="true"]')!
  expect(start.parentElement).toBe(cancel.parentElement)
  for (const element of [cancel, start]) expect(element).toHaveClass('col-start-1', 'row-start-1')
  expect(start).toHaveClass('invisible')
  expect(start).toHaveAttribute('inert')
})

const FAKE_BOTH = { toFake: ['setInterval' as const, 'clearInterval' as const, 'setTimeout' as const, 'clearTimeout' as const] }

test('a second press within 1 s of the start sends no cancel, and focus follows to the cancel button', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL }, 'POST /availability/checks': { status: 202, body: { check_id: 'c1', total: 8 } },
                          'GET /availability/checks/c1': { body: checkState() }, ...CHECK_CANCEL })
  render(<PoolView />)
  const start = await screen.findByRole('button', { name: 'Verfügbarkeit prüfen (8)' })
  vi.useFakeTimers(FAKE_BOTH)
  act(() => start.focus())
  await act(async () => start.click())
  const cancel = screen.getByRole('button', { name: 'Prüfen abbrechen' })
  expect(cancel).toHaveFocus()
  expect(cancel).toHaveAttribute('aria-disabled', 'true')
  await act(async () => cancel.click())
  expect(calls.filter((call) => call.path.endsWith('/cancel'))).toHaveLength(0)
  await act(() => vi.advanceTimersByTimeAsync(SWAP_LOCK_MS))
  expect(cancel).not.toHaveAttribute('aria-disabled')
})

test('the check controls have no accessibility violations: disabled, running, report', async () => {
  stubApi({ 'GET /pool': { body: poolWith({ next_check: { total: 0 } }) } })
  const disabled = render(<PoolView />)
  await screen.findByRole('button', { name: 'Verfügbarkeit prüfen (0)' })
  expect(await axe(disabled.container)).toHaveNoViolations()
  disabled.unmount()
  vi.unstubAllGlobals()
  const running = await openCheck(checkState())
  vi.useRealTimers()
  expect(await axe(running.container)).toHaveNoViolations()
  running.unmount()
  vi.unstubAllGlobals()
  const report = await openCheck(finished(5))
  vi.useRealTimers()
  expect(await axe(report.container)).toHaveNoViolations()
})

test('the pool\'s keys do nothing while focus is in the check column', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  const start = checkStart()
  act(() => start.focus())
  await userEvent.keyboard('1')
  await userEvent.keyboard('j')
  expect(calls.some((call) => call.path.includes('/rating'))).toBe(false)
  expect(start).toHaveFocus()
})

// --- the filter "Stelle geschlossen" and the row mark (3.3) -----------------------------------

const closedAvailability = { state: 'closed' as const, set_at: '2026-11-20T13:05:00+00:00', set_by: 'check' as const }
/** `POOL` with the rated `Data Analyst`, the unrated `Data Engineer`, an imported open row and the
 * applied row closed. */
const CLOSED_POOL = poolWith({ rows: POOL.rows.map((entry) => (
  ['p1', 'p2', 'imp1', 'app1'].includes(entry.posting_id) ? { ...entry, availability: closedAvailability } : entry)) })

test('the filters list "Stelle geschlossen" before "Herkunft"', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  const names = within(screen.getByRole('group', { name: 'Filter' })).getAllByRole('button').map((button) => button.textContent)
  expect(names).toEqual(['Offen', 'Noch nicht bewertet', 'Bewertet', 'Beworben', 'Erledigt', 'Stelle geschlossen', 'Herkunft'])
})

test('closed postings leave Offen, Noch nicht bewertet and Bewertet and show under their own filter', async () => {
  stubApi({ 'GET /pool': { body: CLOSED_POOL } })
  render(<PoolView />)
  const open = await titles()
  expect(open).not.toContain('Data Analyst (m/w/d)')
  expect(open).not.toContain('Data Engineer (m/w/d)')
  expect(open).not.toContain('Importierte Stelle (m/w/d)')
  await userEvent.click(screen.getByRole('button', { name: 'Noch nicht bewertet' }))
  expect(await titles()).not.toContain('Data Engineer (m/w/d)')
  await userEvent.click(screen.getByRole('button', { name: 'Bewertet' }))
  expect(await titles()).toEqual(['Junior Controller (m/w/d)'])
  await userEvent.click(screen.getByRole('button', { name: 'Stelle geschlossen' }))
  expect(await titles()).toEqual(['Data Analyst (m/w/d)', 'Data Engineer (m/w/d)', 'Importierte Stelle (m/w/d)'])
})

test('a closed row carries the mark, an available, unknown or unchecked one does not', async () => {
  stubApi({ 'GET /pool': { body: poolWith({ rows: [
    makeRow('a', 'Verfügbare Stelle (m/w/d)', { availability: { ...closedAvailability, state: 'available' } }),
    makeRow('b', 'Geschlossene Stelle (m/w/d)', { availability: closedAvailability, status: 'applied' }),
    makeRow('c', 'Unbekannte Stelle (m/w/d)', { availability: { ...closedAvailability, state: 'unknown' } }),
    makeRow('d', 'Ungeprüfte Stelle (m/w/d)')] }) } })
  render(<PoolView />)
  await titles()
  for (const title of ['Verfügbare Stelle (m/w/d)', 'Unbekannte Stelle (m/w/d)', 'Ungeprüfte Stelle (m/w/d)']) {
    expect(row(title).queryByText('Stelle geschlossen')).toBeNull()
  }
  await userEvent.click(screen.getByRole('button', { name: 'Beworben' }))
  await titles()
  expect(row('Geschlossene Stelle (m/w/d)').getByText('Stelle geschlossen')).toBeVisible()
})

test('a closed imported posting is listed and marked under Herkunft', async () => {
  stubApi({ 'GET /pool': { body: CLOSED_POOL } })
  render(<PoolView />)
  await titles()
  await userEvent.click(screen.getByRole('button', { name: 'Herkunft' }))
  expect(await titles()).toContain('Importierte Stelle (m/w/d)')
  expect(row('Importierte Stelle (m/w/d)').getByText('Stelle geschlossen')).toBeVisible()
  expect(row('Projektleiter (m/w/d)').getByText('Stelle geschlossen')).toBeVisible()
})

test('the closed filter keeps only closed postings with application status open', async () => {
  stubApi({ 'GET /pool': { body: CLOSED_POOL } })
  render(<PoolView />)
  await titles()
  await userEvent.click(screen.getByRole('button', { name: 'Stelle geschlossen' }))
  expect(await titles()).not.toContain('Projektleiter (m/w/d)')
})

test('a closed posting can be rated from its filter and stays marked', async () => {
  const calls = stubApi({ 'GET /pool': { body: CLOSED_POOL },
    'PUT /postings/p2/rating': (call) => ratingAnswer({ ...baseRow('p2'), availability: closedAvailability }, call.body as RatingBody) })
  render(<PoolView />)
  await titles()
  await userEvent.click(screen.getByRole('button', { name: 'Stelle geschlossen' }))
  await titles()
  await userEvent.click(screen.getByRole('button', { name: 'Ja, auf jeden Fall: Data Engineer (m/w/d)' }))
  await vi.waitFor(() => expect(calls.some((call) => call.method === 'PUT')).toBe(true))
  await vi.waitFor(() => expect(screen.getByRole('button', { name: 'Ja, auf jeden Fall: Data Engineer (m/w/d)' })).toHaveAttribute('aria-pressed', 'true'))
  expect(row('Data Engineer (m/w/d)').getByText('Stelle geschlossen')).toBeVisible()
})

test('the application status is labelled Bewerbungsstatus in a row', async () => {
  stubApi({ 'GET /pool': { body: CLOSED_POOL } })
  render(<PoolView />)
  await titles()
  await userEvent.click(screen.getByRole('button', { name: 'Stelle geschlossen' }))
  await titles()
  const closed = row('Data Engineer (m/w/d)')
  expect(closed.getByText('Stelle geschlossen')).toBeVisible()
  expect(closed.getByLabelText('Bewerbungsstatus: Data Engineer (m/w/d)')).toHaveValue('open')
  expect(closed.getByText('Bewerbungsstatus')).toBeVisible()
})

test('the pool with closed rows has no accessibility violations', async () => {
  stubApi({ 'GET /pool': { body: CLOSED_POOL } })
  const { container } = render(<PoolView />)
  await titles()
  await userEvent.click(screen.getByRole('button', { name: 'Stelle geschlossen' }))
  await titles()
  expect(await axe(container)).toHaveNoViolations()
})

// --- deleting a posting ------------------------------------------------------------------------

const REASON_SCORING = 'Gerade läuft ein Score-Durchlauf. Löschen geht wieder, wenn er fertig ist.'
const REASON_CHECK = 'Gerade läuft eine Verfügbarkeitsprüfung. Löschen geht wieder, wenn sie fertig ist.'
const trash = (title: string) => row(title).getByRole('button', { name: 'Anzeige löschen' })

/** A `GET /pool` answer that drops `gone` once `deleted()` says the delete happened. */
const afterDelete = (gone: string, deleted: () => boolean) => () => ({
  body: deleted() ? poolWith({ rows: POOL.rows.filter((entry) => entry.posting_id !== gone) }) : POOL })

test('every row has a trash button right of the status, named "Anzeige löschen"', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  const shown = await titles()
  const first = row('Data Analyst (m/w/d)')
  const status = first.getByRole('combobox', { name: /Bewerbungsstatus/ })
  expect(trash('Data Analyst (m/w/d)')).toBeEnabled()
  expect(status.compareDocumentPosition(trash('Data Analyst (m/w/d)')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(screen.getAllByRole('button', { name: 'Anzeige löschen' })).toHaveLength(shown.length)
})

test('after a confirmed delete the row is gone, the pool reloads and the filters stay', async () => {
  let deleted = false
  const calls = stubApi({ 'GET /pool': afterDelete('p2', () => deleted),
                          'DELETE /postings/p2': () => { deleted = true; return { status: 204 } } })
  render(<PoolView />)
  await titles()
  await userEvent.click(screen.getByRole('button', { name: 'Noch nicht bewertet' }))
  await userEvent.type(screen.getByRole('searchbox', { name: 'Titel oder Firma' }), 'Dat')
  expect(await titles()).toEqual(['Data Engineer (m/w/d)', 'Datenjournalist (m/w/d)'])
  await userEvent.click(trash('Data Engineer (m/w/d)'))
  const dialog = await screen.findByRole('alertdialog', { name: 'Anzeige löschen?' })
  expect(dialog).toHaveTextContent('Data Engineer (m/w/d) (Nordblatt) wird endgültig gelöscht')
  await userEvent.click(within(dialog).getByRole('button', { name: 'Endgültig löschen' }))
  await vi.waitFor(() => expect(screen.queryByRole('heading', { name: 'Data Engineer (m/w/d)' })).toBeNull())
  expect(await titles()).toEqual(['Datenjournalist (m/w/d)'])
  expect(screen.getByRole('button', { name: 'Noch nicht bewertet' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('searchbox', { name: 'Titel oder Firma' })).toHaveValue('Dat')
  expect(calls.filter((call) => call.method === 'DELETE').map((call) => call.path)).toEqual(['/postings/p2'])
  await vi.waitFor(() => expect(calls.filter((call) => call.path === '/pool')).toHaveLength(2))
  expect(screen.queryByRole('alertdialog')).toBeNull()
})

test('the deleted row leaves at once, also when the reload fails', async () => {
  let deleted = false
  stubApi({ 'GET /pool': () => (deleted ? { status: 500, body: { error: 'internal error', detail: 'x' } } : { body: POOL }),
            'DELETE /postings/p2': () => { deleted = true; return { status: 204 } } })
  render(<PoolView />)
  await titles()
  await userEvent.click(trash('Data Engineer (m/w/d)'))
  await userEvent.click(await screen.findByRole('button', { name: 'Endgültig löschen' }))
  await vi.waitFor(() => expect(screen.queryByRole('heading', { name: 'Data Engineer (m/w/d)' })).toBeNull())
  expect(await screen.findByText(/konnten nicht neu geladen werden/)).toBeVisible()
})

test('deleting the selected row moves the selection to the next row', async () => {
  let deleted = false
  stubApi({ 'GET /pool': afterDelete('p3', () => deleted),
            'DELETE /postings/p3': () => { deleted = true; return { status: 204 } } })
  render(<PoolView />)
  await titles()
  await userEvent.click(screen.getByRole('heading', { name: 'Datenjournalist (m/w/d)' }).closest('li')!)
  expect(document.getElementById('note-p3')).not.toBeNull()
  await userEvent.click(trash('Datenjournalist (m/w/d)'))
  await userEvent.click(await screen.findByRole('button', { name: 'Endgültig löschen' }))
  await vi.waitFor(() => expect(screen.queryByRole('heading', { name: 'Datenjournalist (m/w/d)' })).toBeNull())
  // Not the first unrated row (p2): the row that followed the deleted one.
  await vi.waitFor(() => expect(document.getElementById('note-n1')).not.toBeNull())
  expect(document.getElementById('note-p2')).toBeNull()
})

test('after a confirmed delete focus moves to the newly selected row, not to the body', async () => {
  let deleted = false
  stubApi({ 'GET /pool': afterDelete('p3', () => deleted),
            'DELETE /postings/p3': () => { deleted = true; return { status: 204 } } })
  render(<PoolView />)
  await titles()
  await userEvent.click(screen.getByRole('heading', { name: 'Datenjournalist (m/w/d)' }).closest('li')!)
  await userEvent.click(trash('Datenjournalist (m/w/d)'))
  await userEvent.click(await screen.findByRole('button', { name: 'Endgültig löschen' }))
  await vi.waitFor(() => expect(screen.queryByRole('heading', { name: 'Datenjournalist (m/w/d)' })).toBeNull())
  await vi.waitFor(() => expect(document.getElementById('row-n1')).toContainElement(document.activeElement as HTMLElement))
  // Radix hands focus back on a timer after the close; it must not take it from the row.
  await new Promise((resolve) => setTimeout(resolve, 50))
  expect(document.getElementById('row-n1')).toContainElement(document.activeElement as HTMLElement)
})

test('Abbrechen gives focus back to the trash button', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  await userEvent.click(trash('Datenjournalist (m/w/d)'))
  await userEvent.click(await screen.findByRole('button', { name: 'Abbrechen' }))
  await vi.waitFor(() => expect(trash('Datenjournalist (m/w/d)')).toHaveFocus())
})

test('the next row is the neighbour in the order as it is when the delete answers, not at the click', async () => {
  let deleted = false
  let finish: (reply: { status: number }) => void = () => {}
  stubApi({ 'GET /pool': afterDelete('p3', () => deleted),
            'DELETE /postings/p3': () => new Promise((resolve) => { finish = (reply) => { deleted = true; resolve(reply) } }) })
  render(<PoolView />)
  await titles()
  await userEvent.click(screen.getByRole('heading', { name: 'Datenjournalist (m/w/d)' }).closest('li')!)
  await userEvent.click(trash('Datenjournalist (m/w/d)'))
  await userEvent.click(await screen.findByRole('button', { name: 'Endgültig löschen' }))
  // The order changes while the request runs: by score, the row after p3 is p4, not n1.
  fireEvent.change(document.getElementById('pool-sort')!, { target: { value: 'score-desc' } })
  finish({ status: 204 })
  await vi.waitFor(() => expect(screen.queryByRole('heading', { name: 'Datenjournalist (m/w/d)' })).toBeNull())
  await vi.waitFor(() => expect(document.getElementById('note-p4')).not.toBeNull())
  expect(document.getElementById('note-n1')).toBeNull()
})

test('events inside the delete dialog do not select the row that holds it', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  await userEvent.click(trash('Datenjournalist (m/w/d)'))
  const dialog = await screen.findByRole('alertdialog')
  expect(document.getElementById('note-p3')).not.toBeNull()
  // Another row takes the selection (the modal blocks the mouse, not the event).
  fireEvent.click(screen.getByRole('heading', { name: 'Data Engineer (m/w/d)', hidden: true }).closest('li')!)
  expect(document.getElementById('note-p2')).not.toBeNull()
  fireEvent.click(within(dialog).getByText(/wird endgültig gelöscht/))
  expect(document.getElementById('note-p2')).not.toBeNull()
  expect(document.getElementById('note-p3')).toBeNull()
})

test('with the delete dialog open the shortcut keys rate nothing', async () => {
  const calls = stubApi({ 'GET /pool': { body: POOL } })
  render(<PoolView />)
  await titles()
  await userEvent.click(trash('Data Engineer (m/w/d)'))
  await screen.findByRole('alertdialog')
  await userEvent.keyboard('1')
  await userEvent.keyboard('{Shift>}1{/Shift}')
  expect(calls.filter((call) => call.method === 'PUT')).toEqual([])
})

test.each([
  ['a running pass', () => openRunning(running('scoring', [3, 10])), REASON_SCORING],
  ['a pass that waits for its answer', () => openQuestion(), REASON_SCORING],
  ['a running check', () => openCheck(checkState()), REASON_CHECK],
])('during %s every trash button is disabled and its info icon gives the reason', async (_name, open, reason) => {
  await open()
  const buttons = screen.getAllByRole('button', { name: 'Anzeige löschen' })
  expect(buttons.length).toBeGreaterThan(1)
  for (const button of buttons) {
    expect(button).toBeDisabled()
    expect(button).toHaveAccessibleDescription(reason)
  }
  const first = within(screen.getByRole('heading', { name: 'Data Analyst (m/w/d)' }).closest('li')!)
  act(() => first.getByRole('button', { name: 'Warum ist Löschen nicht möglich?' }).focus())
  expect(first.getByRole('tooltip')).toHaveTextContent(reason)
})

test('the trash buttons are enabled again once the check ended', async () => {
  let current = checkState()
  await openCheck(() => current)
  expect(trash('Data Analyst (m/w/d)')).toBeDisabled()
  current = finished(1)
  await tick()
  expect(trash('Data Analyst (m/w/d)')).toBeEnabled()
  expect(screen.queryByRole('button', { name: 'Warum ist Löschen nicht möglich?' })).toBeNull()
})

test('the pool with trash buttons and an open delete dialog has no accessibility violations', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  const { container } = render(<PoolView />)
  await titles()
  expect(await axe(container)).toHaveNoViolations()
  await userEvent.click(trash('Data Analyst (m/w/d)'))
  expect(await axe(await screen.findByRole('alertdialog'))).toHaveNoViolations()
})
