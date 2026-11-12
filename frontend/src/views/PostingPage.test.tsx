import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import type { PostingPageData, RatingBody } from '@/api'
import { axe } from '@/test-axe'
import { pending, stubApi } from '@/test-api'
import { label, POOL, ratingAnswer, row } from '@/test-fixtures'
import { PostingPage } from './PostingPage'

afterEach(() => vi.unstubAllGlobals())

const posting = { title: 'Data Analyst (m/w/d)', company: 'Grünwerk Solar', location_raw: 'Kiel',
  source_type: 'url' as const, urls: ['https://example.com/job', 'https://other.example/x'],
  text: 'Du wertest Daten aus.\nUnd baust Dashboards.' }

/** A page answer: a scored, rated posting with one example, unless `changes` says otherwise. */
const page = (changes: Partial<PostingPageData> = {}): PostingPageData => ({
  row: row('p1', 'Data Analyst (m/w/d)', { score: 8,
    label: { verdict: 'positive', chips: ['great-stack'], note: 'Passt zu meinem Profil.', rated_at: '2026-10-12T08:00:00+00:00' } }),
  posting,
  score: { score: 8, reasoning: 'Viel SQL, passt zu deinen Beispielen.', example_ids: ['ex1'], scored_at: '2026-10-13T08:00:00+00:00' },
  examples: [{ posting_id: 'ex1', title: 'Analyst Energie', company: 'Nordblatt' }],
  reason_chips: POOL.reason_chips, screening: true, ...changes,
})

test('shows heading, text, original link, score with reasoning, examples, rating, status and no origin', async () => {
  stubApi({ 'GET /postings/p1': { body: page() } })
  render(<PostingPage postingId="p1" />)
  expect(await screen.findByRole('heading', { level: 1, name: 'Data Analyst (m/w/d)' })).toBeVisible()
  expect(screen.getByText('Grünwerk Solar, Kiel')).toBeVisible()
  expect(screen.getByRole('link', { name: 'Zurück zur Liste' })).toHaveAttribute('href', '#/pool')
  expect(screen.getByRole('link', { name: /Originalanzeige öffnen/ })).toHaveAttribute('href', 'https://example.com/job')
  expect(screen.getByText('8')).toBeVisible()
  expect(screen.getByText('Viel SQL, passt zu deinen Beispielen.')).toBeVisible()
  expect(screen.getByText('Verglichen mit:')).toBeVisible()
  expect(screen.getByRole('link', { name: /Analyst Energie/ })).toHaveAttribute('href', '#/anzeigen/ex1')
  expect(screen.getByText('Bewertet: Ja')).toBeVisible()
  expect(screen.getByText('great stack')).toBeVisible()
  expect(screen.getByDisplayValue('Passt zu meinem Profil.')).toBeVisible()
  expect(screen.getByRole('combobox', { name: /Status/ })).toHaveValue('open')
  expect(screen.getByText(/Du wertest Daten aus\./)).toBeVisible()
  expect(screen.queryByText(/Importiert aus/)).toBeNull()
  await waitFor(() => expect(document.title).toBe('Data Analyst (m/w/d) – JobAdvAIsor'))
})

test('shows when the posting was added, above the title, which stays the heading name', async () => {
  stubApi({ 'GET /postings/p1': { body: page() } })
  render(<PostingPage postingId="p1" />)
  const heading = await screen.findByRole('heading', { level: 1 })
  const line = screen.getByText('Hinzugefügt 10.10.2026, 09:12')
  expect(line).toBeVisible()
  expect(line.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(heading).toHaveAccessibleName('Data Analyst (m/w/d)')
  expect(line.closest('time')).toHaveAttribute('datetime', '2026-10-10T07:12:00.000Z')
})

test('shows "Noch keine Bewertung" without a rating, and origin when set', async () => {
  stubApi({ 'GET /postings/p1': { body: page({
    row: row('p1', 'Data Analyst (m/w/d)', { origin: { table: 'jobs_alt', fit: 'gut', status: 'beworben' } }) }) } })
  render(<PostingPage postingId="p1" />)
  expect(await screen.findByText('Noch keine Bewertung')).toBeVisible()
  expect(screen.getByText('Importiert aus jobs_alt, Einschätzung: gut, Status: beworben')).toBeVisible()
})

test('an unscored posting points to the pass', async () => {
  stubApi({ 'GET /postings/p1': { body: page({ row: row('p1', 'Data Analyst (m/w/d)', { state: 'unscored', score: null }),
    score: null, examples: [] }) } })
  render(<PostingPage postingId="p1" />)
  expect(await screen.findByText('Noch kein Score – starte in der Liste „Neue Anzeigen bewerten“.')).toBeVisible()
  expect(screen.queryByText('noch kein Score')).toBeNull()
  expect(screen.queryByText('Verglichen mit:')).toBeNull()
})

test('a rated posting without a score keeps the hint and offers the score button', async () => {
  stubApi({ 'GET /postings/p1': { body: page({ row: row('p1', 'Data Analyst (m/w/d)', { state: 'unscored', score: null,
    label: label('positive') }), score: null, examples: [] }) } })
  render(<PostingPage postingId="p1" />)
  expect(await screen.findByText('Noch kein Score – starte in der Liste „Neue Anzeigen bewerten“.')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Score berechnen' })).toBeEnabled()
})

test('a rated posting with an unreadable score keeps "Score unlesbar" beside the button', async () => {
  stubApi({ 'GET /postings/b': { body: page({ row: row('b', 'X', { state: 'unscored', score: null, label: label('negative'),
    score_problem: 'scores/b.json ist nicht lesbar' }), score: null, examples: [] }) } })
  render(<PostingPage postingId="b" />)
  expect(await screen.findByText(/Score unlesbar/)).toBeVisible()
  expect(screen.getByRole('button', { name: 'Score berechnen' })).toBeEnabled()
})

/** The answer of a single score for `p1`: the page with the score `value`. */
const scored = (value: number) => ({ ...page({ row: row('p1', 'Data Analyst (m/w/d)', { score: value }),
  score: { score: value, reasoning: `Neu: ${value} von 10.`, example_ids: [], scored_at: '2026-11-11T08:00:00+00:00' },
  examples: [] }), counter: POOL.counter, next_pass: POOL.next_pass })

test('a re-score keeps the old score marked as recomputing, then shows the new one', async () => {
  let answer: (value: unknown) => void = () => {}
  const calls = stubApi({ 'GET /postings/p1': { body: page() },
    'POST /postings/p1/score': () => new Promise<{ body: unknown }>((resolve) => { answer = (body) => resolve({ body }) }) as Promise<never> })
  render(<PostingPage postingId="p1" />)
  await userEvent.click(await screen.findByRole('button', { name: 'Neu berechnen' }))
  const section = screen.getByRole('region', { name: 'Score' })
  expect(within(section).getByRole('button', { name: 'Wird berechnet …' })).toBeVisible()
  expect(within(section).getByText('8')).toBeVisible()
  expect(within(section).getByText(/wird neu berechnet/)).toBeVisible()
  expect(within(section).getByText('Viel SQL, passt zu deinen Beispielen.')).toBeVisible()
  expect(section).toHaveAttribute('aria-busy', 'true')
  answer(scored(9))
  expect(await within(section).findByText('Neu: 9 von 10.')).toBeVisible()
  expect(within(section).getByText('9')).toBeVisible()
  expect(within(section).queryByText(/wird neu berechnet/)).toBeNull()
  expect(within(section).queryByText('Verglichen mit:')).toBeNull()
  expect(within(section).getByRole('button', { name: 'Neu berechnen' })).toBeEnabled()
  expect(calls.filter((call) => call.method === 'POST').map((call) => call.path)).toEqual(['/postings/p1/score'])
})

test('a score on an unscored posting replaces the hint with score and reasoning', async () => {
  stubApi({ 'GET /postings/p1': { body: page({ row: row('p1', 'Data Analyst (m/w/d)', { state: 'unscored', score: null }),
    score: null, examples: [] }) }, 'POST /postings/p1/score': { body: scored(6) } })
  render(<PostingPage postingId="p1" />)
  await userEvent.click(await screen.findByRole('button', { name: 'Score berechnen' }))
  expect(await screen.findByText('Neu: 6 von 10.')).toBeVisible()
  expect(screen.queryByText(/starte in der Liste/)).toBeNull()
})

test('a failed score shows the error and keeps the old score', async () => {
  stubApi({ 'GET /postings/p1': { body: page() },
    'POST /postings/p1/score': { status: 502, body: { error: 'scoring failed', detail: 'ConnectionError: down' } } })
  render(<PostingPage postingId="p1" />)
  await userEvent.click(await screen.findByRole('button', { name: 'Neu berechnen' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Der Score konnte nicht berechnet werden. Versuch es noch einmal.')
  expect(screen.getByText('Viel SQL, passt zu deinen Beispielen.')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Erneut versuchen' })).toBeEnabled()
})

test('a held refusal on the click reloads the page and the button turns disabled with its reason', async () => {
  let loads = 0
  stubApi({ 'GET /postings/p1': () => ({ body: ++loads === 1 ? page({ row: row('p1', 'Data Analyst (m/w/d)', { state: 'unscored', score: null }), score: null, examples: [] })
    : page({ row: row('p1', 'Data Analyst (m/w/d)', { state: 'held', score: null, categories: ['instructions_for_ai'] }), score: null, examples: [] }) }),
  'POST /postings/p1/score': { status: 409, body: { error: 'held', detail: 'instructions_for_ai' } } })
  render(<PostingPage postingId="p1" />)
  await userEvent.click(await screen.findByRole('button', { name: 'Score berechnen' }))
  const button = await screen.findByRole('button', { name: 'Score berechnen' })
  await waitFor(() => expect(button).toBeDisabled())
  expect(button).toHaveAccessibleDescription(/Der Inhaltsfilter hält diese Anzeige zurück/)
  expect(screen.queryByRole('alert')).toBeNull()
})

test('held and excluded postings say why, an unreadable score says so', async () => {
  stubApi({ 'GET /postings/h': { body: page({ row: row('h', 'X', { state: 'held', score: null, categories: ['instructions_for_ai'] }), score: null }) },
    'GET /postings/e': { body: page({ row: row('e', 'X', { state: 'excluded', score: null, rules: ['keine-vertriebsjobs'] }), score: null }) },
    'GET /postings/b': { body: page({ row: row('b', 'X', { state: 'unscored', score: null, score_problem: 'scores/b.json ist nicht lesbar' }), score: null }) } })
  const { rerender } = render(<PostingPage postingId="h" />)
  expect(await screen.findByText('zurückgehalten: Anweisungen an eine KI')).toBeVisible()
  rerender(<PostingPage postingId="e" />)
  expect(await screen.findByText('ausgeschlossen: keine-vertriebsjobs')).toBeVisible()
  rerender(<PostingPage postingId="b" />)
  expect(await screen.findByText(/Score unlesbar/)).toBeVisible()
  expect(screen.getByText(/scores\/b\.json ist nicht lesbar/)).toBeInTheDocument()
})

test('changing the status sends a PATCH and shows the new status', async () => {
  const calls = stubApi({ 'GET /postings/p1': { body: page() }, 'PATCH /postings/p1': { body: { posting_id: 'p1', posting } } })
  render(<PostingPage postingId="p1" />)
  await userEvent.selectOptions(await screen.findByRole('combobox', { name: /Status/ }), 'applied')
  expect(calls.find((call) => call.method === 'PATCH')?.body).toEqual({ status: 'applied' })
  expect(await screen.findByDisplayValue('beworben')).toBeVisible()
})

test('a failed status change shows an error, keeps the old status and retries', async () => {
  let fail = true
  stubApi({ 'GET /postings/p1': { body: page() },
    'PATCH /postings/p1': () => (fail ? { status: 500, body: { error: 'x', detail: '' } } : { body: {} }) })
  render(<PostingPage postingId="p1" />)
  await userEvent.selectOptions(await screen.findByRole('combobox', { name: /Status/ }), 'done')
  expect(await screen.findByText('Der Status wurde nicht gespeichert.')).toBeVisible()
  expect(screen.getByRole('combobox', { name: /Status/ })).toHaveValue('open')
  fail = false
  await userEvent.click(screen.getByRole('button', { name: 'Erneut versuchen' }))
  expect(await screen.findByDisplayValue('erledigt')).toBeVisible()
  expect(screen.queryByText('Der Status wurde nicht gespeichert.')).toBeNull()
})

/** Stubs the page and a PATCH that stores the sent fields; `fail` makes the PATCH answer 500. */
function stubCorrection(fail = false) {
  return stubApi({ 'GET /postings/p1': { body: page() },
    'PATCH /postings/p1': ({ body }) => (fail ? { status: 500, body: { error: 'x', detail: '' } }
      : { body: { posting_id: 'p1', posting: { ...posting, ...(body as object) } } }) })
}

test('"Bearbeiten" opens the fields; a corrected company is sent alone and shown', async () => {
  const calls = stubCorrection()
  render(<PostingPage postingId="p1" />)
  const toggle = await screen.findByRole('button', { name: 'Bearbeiten' })
  expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await userEvent.click(toggle)
  expect(toggle).toHaveAttribute('aria-expanded', 'true')
  expect(screen.getByLabelText('Titel')).toHaveValue('Data Analyst (m/w/d)')
  expect(screen.getByLabelText('Ort')).toHaveValue('Kiel')
  await userEvent.clear(screen.getByLabelText('Firma'))
  await userEvent.type(screen.getByLabelText('Firma'), 'Sonnenwerk')
  await userEvent.click(screen.getByRole('button', { name: 'Korrekturen speichern' }))
  expect(await screen.findByText('Sonnenwerk, Kiel')).toBeVisible()
  expect(calls.filter((call) => call.method === 'PATCH').map((call) => call.body)).toEqual([{ company: 'Sonnenwerk' }])
  expect(screen.queryByLabelText('Firma')).toBeNull()
  expect(toggle).toHaveAttribute('aria-expanded', 'false')
  expect(toggle).toHaveFocus()
})

test('a corrected title reaches the heading, the tab title and the status control', async () => {
  stubCorrection()
  render(<PostingPage postingId="p1" />)
  await userEvent.click(await screen.findByRole('button', { name: 'Bearbeiten' }))
  await userEvent.clear(screen.getByLabelText('Titel'))
  await userEvent.type(screen.getByLabelText('Titel'), 'Data Engineer')
  await userEvent.click(screen.getByRole('button', { name: 'Korrekturen speichern' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Data Engineer' })).toBeVisible()
  await waitFor(() => expect(document.title).toBe('Data Engineer – JobAdvAIsor'))
  expect(screen.getByRole('combobox', { name: 'Status: Data Engineer' })).toBeVisible()
})

test('an emptied field is not sent and says so', async () => {
  const calls = stubCorrection()
  render(<PostingPage postingId="p1" />)
  await userEvent.click(await screen.findByRole('button', { name: 'Bearbeiten' }))
  await userEvent.clear(screen.getByLabelText('Ort'))
  await userEvent.click(screen.getByRole('button', { name: 'Korrekturen speichern' }))
  expect(await screen.findByText('Titel, Firma und Ort dürfen nicht leer sein.')).toBeVisible()
  expect(calls.filter((call) => call.method === 'PATCH')).toEqual([])
})

test('a failed correction shows the error and keeps the form with the typed value', async () => {
  stubCorrection(true)
  render(<PostingPage postingId="p1" />)
  await userEvent.click(await screen.findByRole('button', { name: 'Bearbeiten' }))
  await userEvent.clear(screen.getByLabelText('Firma'))
  await userEvent.type(screen.getByLabelText('Firma'), 'Sonnenwerk')
  await userEvent.click(screen.getByRole('button', { name: 'Korrekturen speichern' }))
  expect(await screen.findByText('Speichern hat nicht geklappt. Versuch es noch einmal.')).toBeVisible()
  expect(screen.getByLabelText('Firma')).toHaveValue('Sonnenwerk')
  expect(screen.getByText('Grünwerk Solar, Kiel')).toBeVisible()
})

test('"Abbrechen" closes the form without a request and returns focus', async () => {
  const calls = stubCorrection()
  render(<PostingPage postingId="p1" />)
  const toggle = await screen.findByRole('button', { name: 'Bearbeiten' })
  await userEvent.click(toggle)
  await userEvent.type(screen.getByLabelText('Firma'), 'X')
  await userEvent.click(screen.getByRole('button', { name: 'Abbrechen' }))
  expect(screen.queryByLabelText('Firma')).toBeNull()
  expect(toggle).toHaveFocus()
  expect(calls.filter((call) => call.method === 'PATCH')).toEqual([])
  await userEvent.click(toggle)
  expect(screen.getByLabelText('Firma')).toHaveValue('Grünwerk Solar')
})

const unrated = () => page({ row: row('p1', 'Data Analyst (m/w/d)') })
const rateRoute = (call: { body: unknown }) => ratingAnswer(unrated().row, call.body as RatingBody)

test('a chip on an unrated posting sends no verdict and shows the one the server derives', async () => {
  const calls = stubApi({ 'GET /postings/p1': { body: unrated() }, 'PUT /postings/p1/rating': rateRoute })
  render(<PostingPage postingId="p1" />)
  await userEvent.click(await screen.findByRole('button', { name: 'too junior' }))
  expect(calls.find((call) => call.method === 'PUT')?.body).toEqual({ chips: ['too-junior'], note: null })
  expect(await screen.findByText('Bewertet: Nein')).toBeVisible()
  expect(screen.queryByText('Noch keine Bewertung')).toBeNull()
  expect(screen.getByRole('button', { name: 'great stack' })).toBeEnabled()
})

test('a verdict button and the note are stored at once', async () => {
  const calls = stubApi({ 'GET /postings/p1': { body: unrated() }, 'PUT /postings/p1/rating': rateRoute })
  render(<PostingPage postingId="p1" />)
  await userEvent.click(await screen.findByRole('button', { name: 'Ja, auf jeden Fall: Data Analyst (m/w/d)' }))
  await userEvent.type(await screen.findByLabelText('Notiz'), 'Remote möglich')
  await userEvent.tab()
  await vi.waitFor(() => expect(calls.filter((call) => call.method === 'PUT')).toHaveLength(2))
  expect(calls.filter((call) => call.method === 'PUT').map((call) => call.body)).toEqual([
    { verdict: 'positive', strength: 'strong', chips: [], note: null },
    { verdict: 'positive', strength: 'strong', chips: [], note: 'Remote möglich' }])
})

test('a failed rating keeps the input and retries', async () => {
  let fail = true
  const calls = stubApi({ 'GET /postings/p1': { body: unrated() },
    'PUT /postings/p1/rating': (call) => (fail ? { status: 500, body: { error: 'x', detail: '' } } : rateRoute(call)) })
  render(<PostingPage postingId="p1" />)
  await userEvent.click(await screen.findByRole('button', { name: 'great stack' }))
  expect(await screen.findByText(/Die Bewertung wurde nicht gespeichert/)).toBeVisible()
  expect(screen.getByRole('button', { name: 'great stack' })).toHaveAttribute('aria-pressed', 'true')
  fail = false
  await userEvent.click(screen.getByRole('button', { name: 'Erneut versuchen' }))
  expect(await screen.findByText('Bewertet: Ja')).toBeVisible()
  expect(calls.filter((call) => call.method === 'PUT').map((call) => call.body)).toEqual(
    [{ chips: ['great-stack'], note: null }, { chips: ['great-stack'], note: null }])
})

const LEVELS = [
  ['Ja, auf jeden Fall', 'positive', 'strong'], ['Ja, vielleicht', 'positive', 'weak'],
  ['Nein, eher nicht', 'negative', 'weak'], ['Nein, auf keinen Fall', 'negative', 'strong'],
] as const

test.each(LEVELS)('the button "%s" stores its level and shows it as chosen alone', async (name, verdict, strength) => {
  const calls = stubApi({ 'GET /postings/p1': { body: unrated() }, 'PUT /postings/p1/rating': rateRoute })
  render(<PostingPage postingId="p1" />)
  await userEvent.click(await screen.findByRole('button', { name: `${name}: Data Analyst (m/w/d)` }))
  await vi.waitFor(() => expect(screen.getByRole('button', { name: `${name}: Data Analyst (m/w/d)` })).toHaveAttribute('aria-pressed', 'true'))
  expect(calls.find((call) => call.method === 'PUT')?.body).toEqual({ verdict, strength, chips: [], note: null })
  expect(screen.getAllByRole('button', { pressed: true }).filter((button) => LEVELS.some(([level]) => button.getAttribute('aria-label')?.startsWith(level)))).toHaveLength(1)
})

test.each(LEVELS)('a stored level "%s" is shown as chosen after the page loads', async (name, verdict, strength) => {
  stubApi({ 'GET /postings/p1': { body: page({ row: row('p1', 'Data Analyst (m/w/d)', { label: label(verdict, [], strength) }) }) } })
  render(<PostingPage postingId="p1" />)
  expect(await screen.findByRole('button', { name: `${name}: Data Analyst (m/w/d)` })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.queryByText(/^Bewertet:/)).toBeNull()
})

test('text pasted while no text field has focus lands in the note', async () => {
  stubApi({ 'GET /postings/p1': { body: unrated() }, 'PUT /postings/p1/rating': rateRoute })
  render(<PostingPage postingId="p1" />)
  await userEvent.click(await screen.findByRole('button', { name: 'Ja, vielleicht: Data Analyst (m/w/d)' }))
  await vi.waitFor(() => expect(document.getElementById('reasons-p1')).toHaveFocus())
  fireEvent.paste(document.activeElement!, { clipboardData: { getData: () => 'Eingefügt' } })
  const note = await screen.findByLabelText('Notiz')
  await vi.waitFor(() => expect(note).toHaveFocus())
  expect(note).toHaveValue('Eingefügt')
})

test('a chip after a level resends its strength', async () => {
  const calls = stubApi({ 'GET /postings/p1': { body: unrated() }, 'PUT /postings/p1/rating': rateRoute })
  render(<PostingPage postingId="p1" />)
  await userEvent.click(await screen.findByRole('button', { name: 'Ja, vielleicht: Data Analyst (m/w/d)' }))
  await vi.waitFor(() => expect(screen.getByRole('button', { name: 'Ja, vielleicht: Data Analyst (m/w/d)' })).toHaveAttribute('aria-pressed', 'true'))
  await userEvent.click(screen.getByRole('button', { name: 'too junior' }))
  await vi.waitFor(() => expect(calls.filter((call) => call.method === 'PUT')).toHaveLength(2))
  expect(calls.filter((call) => call.method === 'PUT')[1].body).toEqual({ verdict: 'positive', strength: 'weak', chips: ['too-junior'], note: null })
})

test('shows a loading state', () => {
  stubApi({ 'GET /postings/p1': pending() })
  render(<PostingPage postingId="p1" />)
  expect(screen.getByText('Anzeige wird geladen')).toBeVisible()
})

test('an unknown posting says so and links back', async () => {
  stubApi({ 'GET /postings/nope': { status: 404, body: { error: 'not found', detail: 'no posting nope' } } })
  render(<PostingPage postingId="nope" />)
  expect(await screen.findByText('Diese Anzeige gibt es nicht (mehr).')).toBeVisible()
  expect(screen.getByRole('link', { name: 'Zurück zur Liste' })).toHaveAttribute('href', '#/pool')
})

test('another error offers a retry that loads the page', async () => {
  let fail = true
  stubApi({ 'GET /postings/p1': () => (fail ? { status: 500, body: { error: 'x', detail: '' } } : { body: page() }) })
  render(<PostingPage postingId="p1" />)
  expect(await screen.findByText('Die Anzeige konnte nicht geladen werden')).toBeVisible()
  fail = false
  await userEvent.click(screen.getByRole('button', { name: 'Erneut versuchen' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Data Analyst (m/w/d)' })).toBeVisible()
})

test('switching the ID loads the other posting', async () => {
  stubApi({ 'GET /postings/p1': { body: page() },
    'GET /postings/ex1': { body: page({ row: row('ex1', 'Analyst Energie'), posting: { ...posting, title: 'Analyst Energie' }, score: null, examples: [] }) } })
  const { rerender } = render(<PostingPage postingId="p1" />)
  await screen.findByRole('heading', { level: 1, name: 'Data Analyst (m/w/d)' })
  rerender(<PostingPage postingId="ex1" />)
  expect(await screen.findByRole('heading', { level: 1, name: 'Analyst Energie' })).toBeVisible()
  await waitFor(() => expect(document.title).toBe('Analyst Energie – JobAdvAIsor'))
})

test('has no axe violations', async () => {
  stubApi({ 'GET /postings/p1': { body: page() } })
  const { container } = render(<PostingPage postingId="p1" />)
  await screen.findByRole('heading', { level: 1 })
  expect(await axe(container)).toHaveNoViolations()
})
