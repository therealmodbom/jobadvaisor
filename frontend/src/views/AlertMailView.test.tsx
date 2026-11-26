import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { AlertEntry, AlertPreview, AlertRunState } from '@/api'
import { axe } from '@/test-axe'
import { pending, stubApi } from '@/test-api'
import { AlertMailView } from './AlertMailView'
import { POLL_MS } from './PoolView'

const RUN_KEY = 'jobadvaisor.alert-run'
const HTML = '<p><a href="https://www.linkedin.com/jobs/view/4100000102">Director Software</a></p>'
const PLAIN = 'Director Software'

const entry = (n: number, over: Partial<AlertEntry> = {}): AlertEntry => ({
  url: `https://www.linkedin.com/jobs/view/41000001${n}`, title: `Stelle ${n}`,
  duplicate: null, login_walled: false, ambiguous: false, ...over,
})

const preview = (entries: AlertEntry[], over: Partial<AlertPreview> = {}): AlertPreview => ({
  entries, read_by: ['linkedin'], unread_hosts: [], held: false, model_skipped: null,
  screening: true, truncated: false, ...over,
})

const found = (entries: AlertEntry[], over: Partial<AlertPreview> = {}) =>
  ({ 'POST /alert-mails/preview': { body: preview(entries, over) } })

const done = (state: AlertRunState['entries'][number]['state']) => ['stored', 'duplicate', 'closed', 'failed'].includes(state)

const run = (entries: AlertRunState['entries'], over: Partial<AlertRunState> = {}): AlertRunState => ({
  run_id: 'r1', status: 'running', error: null, cancel_requested: false, total: entries.length,
  done: entries.filter((item) => done(item.state)).length, entries, ...over,
})

const row = (n: number, state: AlertRunState['entries'][number]['state'],
             over: object = {}): AlertRunState['entries'][number] =>
  ({ url: entry(n).url, title: entry(n).title, state, ...over })

/** A paste event carrying `html` (when given) and `plain`, as a mail client's copy delivers it. */
function paste(target: HTMLElement, plain: string, html?: string) {
  const data = new Map<string, string>([['text/plain', plain]])
  if (html !== undefined) data.set('text/html', html)
  fireEvent.paste(target, { clipboardData: { getData: (type: string) => data.get(type) ?? '' } })
}

const field = () => screen.getByLabelText('Alert-Mail')
/** The rows of a run list: its direct children, since a failed row holds a list of attempts itself. */
const rowsOf = (list: HTMLElement) => Array.from(list.children) as HTMLElement[]
/** The filter row of a run, its buttons' names in order, and the status line under it. */
const filters = () => screen.getByRole('group', { name: 'Filter' })
const filterNames = () => within(filters()).getAllByRole('button').map((button) => button.textContent)
const filterButton = (name: string) => within(filters()).getByRole('button', { name })
const statusLine = () => screen.getByText(/^Zeigt /)
const noop = () => {}
const view = (props: Partial<Parameters<typeof AlertMailView>[0]> = {}) =>
  render(<AlertMailView onUrl={noop} onText={noop} onPdf={noop} {...props} />)

async function findStellen(...entries: AlertEntry[]) {
  paste(field(), PLAIN, HTML)
  await userEvent.click(screen.getByRole('button', { name: 'Stellen finden' }))
  await screen.findByRole('heading', { name: /in der Mail gefunden/ })
  return entries
}

beforeEach(() => {
  sessionStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

// ---- 7.1: paste ----

test('a paste keeps the HTML part and shows the plain text; "Stellen finden" sends both', async () => {
  const calls = stubApi(found([entry(1)]))
  view()
  paste(field(), PLAIN, HTML)
  expect(field()).toHaveValue(PLAIN)
  await userEvent.click(screen.getByRole('button', { name: 'Stellen finden' }))
  await screen.findByRole('list', { name: 'Gefundene Stellen' })
  expect(calls.at(-1)!.body).toEqual({ html: HTML, text: PLAIN })
})

test('a paste without HTML sends html null', async () => {
  const calls = stubApi(found([entry(1)]))
  view()
  paste(field(), PLAIN)
  await userEvent.click(screen.getByRole('button', { name: 'Stellen finden' }))
  await screen.findByRole('list', { name: 'Gefundene Stellen' })
  expect(calls.at(-1)!.body).toEqual({ html: null, text: PLAIN })
})

test('a second paste replaces the text and the HTML', async () => {
  const calls = stubApi(found([entry(1)]))
  view()
  paste(field(), PLAIN, HTML)
  paste(field(), 'Zweite Mail', '<p><a href="https://example.com/job/x/1?refid=2">Zweite</a></p>')
  expect(field()).toHaveValue('Zweite Mail')
  await userEvent.click(screen.getByRole('button', { name: 'Stellen finden' }))
  await screen.findByRole('list', { name: 'Gefundene Stellen' })
  expect(calls.at(-1)!.body).toEqual({
    html: '<p><a href="https://example.com/job/x/1?refid=2">Zweite</a></p>', text: 'Zweite Mail',
  })
})

test('a second paste without HTML drops the HTML of the first', async () => {
  const calls = stubApi(found([entry(1)]))
  view()
  paste(field(), PLAIN, HTML)
  paste(field(), 'Nur Text')
  await userEvent.click(screen.getByRole('button', { name: 'Stellen finden' }))
  await screen.findByRole('list', { name: 'Gefundene Stellen' })
  expect(calls.at(-1)!.body).toEqual({ html: null, text: 'Nur Text' })
})

test('clearing the field drops the HTML, so "Stellen finden" sends nothing', async () => {
  const calls = stubApi(found([entry(1)]))
  view()
  paste(field(), PLAIN, HTML)
  await userEvent.clear(field())
  await userEvent.click(screen.getByRole('button', { name: 'Stellen finden' }))
  expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0)
})

test('typing after a paste leaves the HTML as it is', async () => {
  const calls = stubApi(found([entry(1)]))
  view()
  paste(field(), PLAIN, HTML)
  await userEvent.type(field(), '!')
  await userEvent.click(screen.getByRole('button', { name: 'Stellen finden' }))
  await screen.findByRole('list', { name: 'Gefundene Stellen' })
  expect(calls.at(-1)!.body).toEqual({ html: HTML, text: `${PLAIN}!` })
})

test('typed text without a paste goes out as plain text', async () => {
  const calls = stubApi(found([entry(1)]))
  view()
  await userEvent.type(field(), 'https://www.linkedin.com/jobs/view/4100000101')
  await userEvent.click(screen.getByRole('button', { name: 'Stellen finden' }))
  await screen.findByRole('list', { name: 'Gefundene Stellen' })
  expect(calls.at(-1)!.body).toEqual({ html: null, text: 'https://www.linkedin.com/jobs/view/4100000101' })
})

test('while the mail is read, the field and the button wait and a status says so', async () => {
  stubApi({ 'POST /alert-mails/preview': pending })
  view()
  paste(field(), PLAIN, HTML)
  await userEvent.click(screen.getByRole('button', { name: 'Stellen finden' }))
  expect(screen.getByRole('button', { name: 'Stellen werden gesucht…' })).toBeDisabled()
  expect(field()).toBeDisabled()
  expect(screen.getByRole('status')).toHaveTextContent('Stellen werden gesucht')
})

// ---- 7.2: pick list ----

test('the pick list preselects new entries, marks stored ones and login-walled ones', async () => {
  stubApi(found([
    entry(1),
    entry(2, { duplicate: { posting_id: 'p-2', title: 'Stelle 2' } }),
    entry(3, { login_walled: true, url: 'https://www.xing.com/jobs/x-4711' }),
    entry(4),
  ]))
  view()
  await findStellen()
  expect(screen.getByRole('heading', { name: '4 Stellen in der Mail gefunden' })).toBeVisible()
  const list = screen.getByRole('list', { name: 'Gefundene Stellen' })
  expect(within(list).getByRole('checkbox', { name: 'Stelle 1' })).toBeChecked()
  expect(within(list).getByRole('checkbox', { name: 'Stelle 4' })).toBeChecked()
  const stored = within(list).getByRole('checkbox', { name: 'Stelle 2' })
  expect(stored).toBeDisabled()
  expect(stored).not.toBeChecked()
  expect(stored).toHaveAccessibleDescription('Schon gespeichert')
  expect(within(list).getByRole('link', { name: 'Gespeicherte Anzeige ansehen' }))
    .toHaveAttribute('href', '#/anzeigen/p-2')
  const walled = within(list).getByRole('checkbox', { name: 'Stelle 3' })
  expect(walled).toBeEnabled()
  expect(walled).not.toBeChecked()
  expect(within(list).getByText('Seite mit Login-Pflicht')).toBeVisible()
  expect(screen.getByRole('button', { name: '2 Anzeigen hinzufügen' })).toBeEnabled()
})

test('an entry of the pick list links its address in a new tab, named for the posting, and its checkbox still toggles', async () => {
  stubApi(found([entry(1, { title: 'Data Engineer', url: 'https://jobs.example.com/data-engineer/1' })]))
  view()
  await findStellen()
  const link = screen.getByRole('link', { name: 'Anzeige „Data Engineer“ öffnen, neuer Tab: https://jobs.example.com/data-engineer/1' })
  expect(link).toHaveTextContent('https://jobs.example.com/data-engineer/1')
  expect(link).toHaveAttribute('href', 'https://jobs.example.com/data-engineer/1')
  expect(link).toHaveAttribute('target', '_blank')
  expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  const box = screen.getByRole('checkbox', { name: 'Data Engineer' })
  expect(box).toBeChecked()
  await userEvent.click(box)
  expect(box).not.toBeChecked()
})

test('an entry without a title gives its link no posting name', async () => {
  stubApi(found([entry(1, { title: '', url: 'https://jobs.example.com/x/1' })]))
  view()
  await findStellen()
  expect(screen.getByRole('link', { name: 'Anzeige öffnen, neuer Tab: https://jobs.example.com/x/1' })).toBeVisible()
})

test('an entry whose address is not http(s) shows it as text, not as a link', async () => {
  stubApi(found([entry(1, { url: 'ftp://files.example.com/job' })]))
  view()
  await findStellen()
  const list = screen.getByRole('list', { name: 'Gefundene Stellen' })
  expect(within(list).getByText('ftp://files.example.com/job')).toBeVisible()
  expect(within(list).queryByRole('link')).toBeNull()
})

test('changing the selection changes the count, and nothing selected disables the action', async () => {
  stubApi(found([entry(1), entry(2)]))
  view()
  await findStellen()
  await userEvent.click(screen.getByRole('checkbox', { name: 'Stelle 1' }))
  expect(screen.getByRole('button', { name: '1 Anzeige hinzufügen' })).toBeEnabled()
  await userEvent.click(screen.getByRole('checkbox', { name: 'Stelle 2' }))
  expect(screen.getByRole('button', { name: '0 Anzeigen hinzufügen' })).toBeDisabled()
})

test('an ambiguous entry is not selectable and offers the text option', async () => {
  const onText = vi.fn()
  stubApi(found([entry(1), entry(2, { ambiguous: true, url: 'https://trk.example.com/ls/click' })]))
  view({ onText })
  await findStellen()
  const box = screen.getByRole('checkbox', { name: 'Stelle 2' })
  expect(box).toBeDisabled()
  expect(box).not.toBeChecked()
  expect(screen.getByText('Link nicht eindeutig')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Text einfügen' }))
  expect(onText).toHaveBeenCalled()
})

test('the note names the hosts of links no rule read, with their counts', async () => {
  stubApi(found([entry(1)], { unread_hosts: [{ host: 'jobs.example.net', links: 4 }, { host: 'social.example.com', links: 1 }] }))
  view()
  await findStellen()
  const note = screen.getByRole('note')
  expect(note).toHaveTextContent('Nicht gelesen: jobs.example.net (4 Links), social.example.com (1 Link)')
  expect(note).toHaveTextContent('Füge diese Mail einzeln ein')
})

test('a truncated mail says that only the first 100 are listed', async () => {
  stubApi(found([entry(1)], { truncated: true }))
  view()
  await findStellen()
  expect(screen.getByText(/Nur die ersten 100 sind aufgeführt/)).toBeVisible()
})

test('the pick list says which finder read the mail and that nothing was fetched yet', async () => {
  stubApi(found([entry(1)], { read_by: ['linkedin'] }))
  view()
  await findStellen()
  expect(screen.getByText(/Gelesen über die feste Regel für LinkedIn/)).toBeVisible()
  expect(screen.getByText(/nichts wurde bisher abgerufen/)).toBeVisible()
})

test('a mail read by the model says so', async () => {
  stubApi(found([entry(1)], { read_by: ['model'] }))
  view()
  await findStellen()
  expect(screen.getByText(/Gelesen von einem Modell/)).toBeVisible()
})

test('"Andere Mail einfügen" starts over with an empty field', async () => {
  stubApi(found([entry(1)]))
  view()
  await findStellen()
  await userEvent.click(screen.getByRole('button', { name: 'Andere Mail einfügen' }))
  expect(field()).toHaveValue('')
  expect(screen.queryByRole('list', { name: 'Gefundene Stellen' })).not.toBeInTheDocument()
})

test('the pick list has no accessibility violations', async () => {
  stubApi(found([entry(1), entry(2, { duplicate: { posting_id: 'p-2', title: 'Stelle 2' } }),
                 entry(3, { ambiguous: true })]))
  const { container } = view()
  await findStellen()
  expect(await axe(container)).toHaveNoViolations()
})

// ---- 7.2: states without a pick list ----

test('no posting found points to the link and text inputs', async () => {
  const onUrl = vi.fn()
  const onText = vi.fn()
  stubApi(found([], { read_by: [] }))
  view({ onUrl, onText })
  paste(field(), PLAIN, HTML)
  await userEvent.click(screen.getByRole('button', { name: 'Stellen finden' }))
  expect(await screen.findByRole('heading', { name: 'Keine Stellen gefunden' })).toBeVisible()
  expect(screen.getByText(/kein Link zu einer Stellenanzeige gefunden/)).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Link einfügen' }))
  await userEvent.click(screen.getByRole('button', { name: 'Text einfügen' }))
  expect(onUrl).toHaveBeenCalled()
  expect(onText).toHaveBeenCalled()
})

test('screening off and an unknown sender says that only known senders can be read', async () => {
  stubApi(found([], { read_by: [], screening: false, model_skipped: 'screening off' }))
  view()
  paste(field(), PLAIN, HTML)
  await userEvent.click(screen.getByRole('button', { name: 'Stellen finden' }))
  expect(await screen.findByRole('heading', { name: /Nur bekannte Absender/ })).toBeVisible()
  expect(screen.queryByRole('heading', { name: 'Keine Stellen gefunden' })).not.toBeInTheDocument()
})

test('a mail held by the content guard says so and lists nothing', async () => {
  stubApi(found([], { read_by: ['model'], held: true }))
  view()
  paste(field(), PLAIN, HTML)
  await userEvent.click(screen.getByRole('button', { name: 'Stellen finden' }))
  expect(await screen.findByRole('heading', { name: 'Mail von der Inhaltsprüfung zurückgehalten' })).toBeVisible()
  expect(screen.queryByRole('list', { name: 'Gefundene Stellen' })).not.toBeInTheDocument()
})

test('a failed reading says so, offers a retry and keeps the mail in the field', async () => {
  let attempts = 0
  const calls = stubApi({ 'POST /alert-mails/preview': () => ++attempts === 1
    ? { status: 502, body: { error: 'screening failed', detail: 'reading the mail failed; try again' } }
    : { body: preview([entry(1)]) } })
  view()
  paste(field(), PLAIN, HTML)
  await userEvent.click(screen.getByRole('button', { name: 'Stellen finden' }))
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('Mail konnte nicht gelesen werden')
  expect(field()).toHaveValue(PLAIN)
  await userEvent.click(within(alert).getByRole('button', { name: 'Erneut versuchen' }))
  await screen.findByRole('list', { name: 'Gefundene Stellen' })
  expect(calls.filter((call) => call.method === 'POST')[1].body).toEqual({ html: HTML, text: PLAIN })
})

test('a failed reading with the model says that the model did not answer', async () => {
  stubApi({ 'POST /alert-mails/preview': { status: 502, body: { error: 'finder failed', detail: 'x' } } })
  view()
  paste(field(), PLAIN, HTML)
  await userEvent.click(screen.getByRole('button', { name: 'Stellen finden' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Das Modell hat nicht geantwortet')
})

test('an unreachable server is named', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline') }))
  view()
  paste(field(), PLAIN, HTML)
  await userEvent.click(screen.getByRole('button', { name: 'Stellen finden' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Der Server ist nicht erreichbar')
})

test('the screening line follows the last answer', async () => {
  stubApi(found([], { screening: false, read_by: ['linkedin'] }))
  view()
  paste(field(), PLAIN, HTML)
  await userEvent.click(screen.getByRole('button', { name: 'Stellen finden' }))
  await screen.findByRole('heading', { name: 'Keine Stellen gefunden' })
  await userEvent.click(screen.getByRole('button', { name: 'Andere Mail einfügen' }))
  expect(screen.getByText(/Inhaltsprüfung ist aus/)).toBeVisible()
})

// ---- 7.2: run ----

const RUNNING = run([row(1, 'stored', { posting_id: 'p-1' }), row(2, 'running'), row(3, 'waiting')])

test('the chosen entries start a run with their cleaned links and the run is kept', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  const calls = stubApi({
    ...found([entry(1), entry(2), entry(3, { duplicate: { posting_id: 'p-3', title: 'Stelle 3' } })]),
    'POST /alert-mails/runs': { status: 202, body: { run_id: 'r1' } },
    'GET /alert-mails/runs/r1': { body: run([row(1, 'running'), row(2, 'waiting')]) },
  })
  view()
  await findStellen()
  await userEvent.click(screen.getByRole('checkbox', { name: 'Stelle 2' }))
  await userEvent.click(screen.getByRole('button', { name: '1 Anzeige hinzufügen' }))
  await screen.findByRole('list', { name: 'Stand je Anzeige' })
  const start = calls.find((call) => call.path === '/alert-mails/runs')!
  expect(start.body).toEqual({ entries: [{ url: entry(1).url, title: 'Stelle 1', force: false }] })
  expect(sessionStorage.getItem(RUN_KEY)).toBe('r1')
  expect(screen.queryByRole('list', { name: 'Gefundene Stellen' })).not.toBeInTheDocument()
})

test('each row shows its state, and the count and the bar follow', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: RUNNING } })
  view()
  const list = await screen.findByRole('list', { name: 'Stand je Anzeige' })
  const rows = rowsOf(list)
  expect(rows[0]).toHaveTextContent('Hinzugefügt')
  expect(within(rows[0]).getByRole('link', { name: 'Anzeige ansehen' })).toHaveAttribute('href', '#/anzeigen/p-1')
  expect(rows[1]).toHaveTextContent('wird abgerufen…')
  expect(rows[2]).toHaveTextContent('wartet')
  expect(screen.getByRole('heading', { name: '1 von 3 erledigt' })).toBeVisible()
  const bar = screen.getByRole('progressbar', { name: 'Fortschritt' })
  expect(bar).toHaveAttribute('value', '1')
  expect(bar).toHaveAttribute('max', '3')
})

test('the run is polled every second until it is done, then the poll stops', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem(RUN_KEY, 'r1')
  let reads = 0
  const calls = stubApi({ 'GET /alert-mails/runs/r1': () => ({ body: ++reads < 2 ? RUNNING
    : run([row(1, 'stored', { posting_id: 'p-1' }), row(2, 'stored', { posting_id: 'p-2' }),
           row(3, 'stored', { posting_id: 'p-3' })], { status: 'done' }) }) })
  view()
  await screen.findByRole('list', { name: 'Stand je Anzeige' })
  await act(() => vi.advanceTimersByTimeAsync(POLL_MS))
  expect(await screen.findByRole('heading', { name: '3 von 3 erledigt' })).toBeVisible()
  expect(filterNames()).toEqual(['Alle (3)', '3 hinzugefügt'])
  const before = calls.length
  await act(() => vi.advanceTimersByTimeAsync(POLL_MS * 3))
  expect(calls.length).toBe(before)
  await userEvent.click(screen.getByRole('button', { name: 'Andere Mail einfügen' }))
  expect(field()).toHaveValue('')
  expect(sessionStorage.getItem(RUN_KEY)).toBeNull()
})

test('a failed row lists the attempts and offers text and PDF, and the others are stored', async () => {
  const onText = vi.fn()
  const onPdf = vi.fn()
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: run([
    row(1, 'stored', { posting_id: 'p-1' }),
    row(2, 'failed', { attempts: [{ step: 'login_wall', url: entry(2).url, outcome: 'skipped' },
                                  { step: 'loop:search_alternative_source', url: entry(2).url, outcome: 'ok' }] }),
    row(3, 'stored', { posting_id: 'p-3' }),
  ], { status: 'done' }) } })
  view({ onText, onPdf })
  const list = await screen.findByRole('list', { name: 'Stand je Anzeige' })
  const rows = rowsOf(list)
  expect(within(rows[0]).getByRole('link', { name: 'Anzeige ansehen' })).toHaveAttribute('href', '#/anzeigen/p-1')
  expect(within(rows[2]).getByRole('link', { name: 'Anzeige ansehen' })).toHaveAttribute('href', '#/anzeigen/p-3')
  expect(rows[1]).toHaveTextContent('Nicht gelesen')
  expect(within(rows[1]).getByRole('list')).not.toBeVisible()
  await userEvent.click(within(rows[1]).getByText('Details: 2 Versuche'))
  const attempts = within(rows[1]).getByRole('list')
  expect(attempts).toBeVisible()
  expect(attempts).toHaveTextContent('Seite mit Login-Pflicht: übersprungen')
  expect(attempts).toHaveTextContent('Websuche nach einer anderen Quelle: keine Anzeige gefunden')
  await userEvent.click(within(rows[1]).getByRole('button', { name: 'Text einfügen' }))
  await userEvent.click(within(rows[1]).getByRole('button', { name: 'PDF hochladen' }))
  expect(onText).toHaveBeenCalled()
  expect(onPdf).toHaveBeenCalled()
  expect(filterNames()).toEqual(['Alle (3)', '2 hinzugefügt', '1 nicht gelesen'])
})

test('a failed row without attempts shows no English reason but the fallback', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: run([row(1, 'failed', { reason: 'ConnectError' })], { status: 'done' }) } })
  view()
  const rows = rowsOf(await screen.findByRole('list', { name: 'Stand je Anzeige' }))
  expect(rows[0]).not.toHaveTextContent('ConnectError')
  expect(rows[0]).toHaveTextContent('Diese Anzeige konnte nicht gelesen werden.')
  expect(within(rows[0]).getByRole('button', { name: 'Text einfügen' })).toBeVisible()
  expect(within(rows[0]).getByRole('button', { name: 'PDF hochladen' })).toBeVisible()
  expect(rows[0].querySelector('details')).toBeNull()
})

test('a duplicate by link shows the stored posting and offers no way to store it again', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: run([
    row(1, 'duplicate', { posting_id: 'p-9', duplicate_by: 'url' })], { status: 'done' }) } })
  view()
  const list = await screen.findByRole('list', { name: 'Stand je Anzeige' })
  expect(within(list).getByText('Schon gespeichert')).toBeVisible()
  expect(within(list).getByRole('link', { name: 'Gespeicherte Anzeige ansehen' })).toHaveAttribute('href', '#/anzeigen/p-9')
  expect(screen.queryByRole('button', { name: 'Trotzdem als neue Anzeige speichern' })).not.toBeInTheDocument()
})

const TEXT_DUPLICATE = {
  'GET /postings/p-9': { body: { posting: { title: 'Lead Engineer Video', company: 'Musterdienst GmbH' } } },
  'GET /alert-mails/runs/r1': { body: run([
    row(1, 'duplicate', { posting_id: 'p-9', duplicate_by: 'text' }),
    row(2, 'stored', { posting_id: 'p-2' }),
  ], { status: 'done' }) },
}

test('a duplicate by text names the matching posting and offers to store it anyway', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi(TEXT_DUPLICATE)
  view()
  const list = await screen.findByRole('list', { name: 'Stand je Anzeige' })
  expect(within(list).getByText('Gleicher Text wie eine gespeicherte Anzeige')).toBeVisible()
  const link = await within(list).findByRole('link', { name: /Lead Engineer Video/ })
  expect(link).toHaveAttribute('href', '#/anzeigen/p-9')
  expect(link).toHaveTextContent('bei Musterdienst GmbH')
  expect(within(list).getByRole('button', { name: 'Trotzdem als neue Anzeige speichern' })).toBeVisible()
})

test('a duplicate by similar text says "ähnelt"', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ ...TEXT_DUPLICATE, 'GET /alert-mails/runs/r1': { body: run([
    row(1, 'duplicate', { posting_id: 'p-9', duplicate_by: 'similar_text' })], { status: 'done' }) } })
  view()
  expect(await screen.findByText('Ähnlicher Text wie eine gespeicherte Anzeige')).toBeVisible()
})

test('store anyway asks first, naming the posting, and cancelling stores nothing', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  const calls = stubApi(TEXT_DUPLICATE)
  view()
  await userEvent.click(await screen.findByRole('button', { name: 'Trotzdem als neue Anzeige speichern' }))
  const confirm = await screen.findByRole('group', { name: /Als neue Anzeige speichern\?/ })
  expect(confirm).toHaveTextContent('Lead Engineer Video')
  expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0)
  await userEvent.click(within(confirm).getByRole('button', { name: 'Abbrechen' }))
  expect(screen.queryByRole('group', { name: /Als neue Anzeige speichern\?/ })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Trotzdem als neue Anzeige speichern' })).toBeVisible()
  expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0)
})

test('confirmed, it starts a run of that entry with force and its row shows it as stored', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem(RUN_KEY, 'r1')
  const calls = stubApi({
    ...TEXT_DUPLICATE,
    'POST /alert-mails/runs': { status: 202, body: { run_id: 'r2' } },
    'GET /alert-mails/runs/r2': { body: run([row(1, 'stored', { posting_id: 'p-10' })],
                                             { run_id: 'r2', status: 'done' }) },
  })
  view()
  await userEvent.click(await screen.findByRole('button', { name: 'Trotzdem als neue Anzeige speichern' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Ja, als neue Anzeige speichern' }))
  const start = calls.find((call) => call.method === 'POST')!
  expect(start.body).toEqual({ entries: [{ url: entry(1).url, title: 'Stelle 1', force: true }] })
  const rows = rowsOf(await screen.findByRole('list', { name: 'Stand je Anzeige' }))
  expect(rows).toHaveLength(2)
  expect(rows[0]).toHaveTextContent('Hinzugefügt')
  expect(within(rows[0]).getByRole('link', { name: 'Anzeige ansehen' })).toHaveAttribute('href', '#/anzeigen/p-10')
  expect(rows[1]).toHaveTextContent('Hinzugefügt')
  expect(sessionStorage.getItem(RUN_KEY)).toBe('r2')
})

test('after a reload the forced row sits in its original report again', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem(RUN_KEY, 'r1')
  const routes = {
    ...TEXT_DUPLICATE,
    'POST /alert-mails/runs': { status: 202, body: { run_id: 'r2' } },
    'GET /alert-mails/runs/r2': { body: run([row(1, 'stored', { posting_id: 'p-10' })],
                                             { run_id: 'r2', status: 'done' }) },
  }
  stubApi(routes)
  const first = view()
  await userEvent.click(await screen.findByRole('button', { name: 'Trotzdem als neue Anzeige speichern' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Ja, als neue Anzeige speichern' }))
  await screen.findByRole('list', { name: 'Stand je Anzeige' })
  first.unmount()
  stubApi(routes)
  view()
  await waitFor(() => expect(rowsOf(screen.getByRole('list', { name: 'Stand je Anzeige' }))).toHaveLength(2))
  const rows = rowsOf(screen.getByRole('list', { name: 'Stand je Anzeige' }))
  expect(within(rows[0]).getByRole('link', { name: 'Anzeige ansehen' })).toHaveAttribute('href', '#/anzeigen/p-10')
  expect(rows[1]).toHaveTextContent('Hinzugefügt')
})

test('after a second stored-anyway run and a reload the report still comes from the original run', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem(RUN_KEY, 'r1')
  const ids = ['r2', 'r3']
  const routes = {
    'GET /postings/p-9': { body: { posting: { title: 'Lead Engineer Video', company: 'Musterdienst GmbH' } } },
    'GET /alert-mails/runs/r1': { body: run([
      row(1, 'duplicate', { posting_id: 'p-9', duplicate_by: 'text' }),
      row(2, 'duplicate', { posting_id: 'p-9', duplicate_by: 'text' }),
      row(3, 'stored', { posting_id: 'p-3' }),
    ], { status: 'done' }) },
    'POST /alert-mails/runs': () => ({ status: 202, body: { run_id: ids.shift() } }),
    'GET /alert-mails/runs/r2': { body: run([row(1, 'stored', { posting_id: 'p-10' })], { run_id: 'r2', status: 'done' }) },
    'GET /alert-mails/runs/r3': { body: run([row(2, 'stored', { posting_id: 'p-11' })], { run_id: 'r3', status: 'done' }) },
  }
  stubApi(routes)
  const first = view()
  for (let round = 0; round < 2; round++) {
    await userEvent.click((await screen.findAllByRole('button', { name: 'Trotzdem als neue Anzeige speichern' }))[0])
    await userEvent.click(await screen.findByRole('button', { name: 'Ja, als neue Anzeige speichern' }))
    await waitFor(() => expect(screen.getAllByText('Hinzugefügt').length).toBeGreaterThan(round + 1))
  }
  first.unmount()
  stubApi(routes)
  view()
  await waitFor(() => expect(rowsOf(screen.getByRole('list', { name: 'Stand je Anzeige' }))).toHaveLength(3))
  const rows = rowsOf(screen.getByRole('list', { name: 'Stand je Anzeige' }))
  await waitFor(() => expect(within(rows[0]).getByRole('link', { name: 'Anzeige ansehen' })).toHaveAttribute('href', '#/anzeigen/p-10'))
  expect(within(rows[1]).getByRole('link', { name: 'Anzeige ansehen' })).toHaveAttribute('href', '#/anzeigen/p-11')
})

test('editing a pasted mail says the edit does not change what is found', async () => {
  view()
  paste(field(), PLAIN, HTML)
  expect(screen.queryByText(/Änderungen am Text/)).not.toBeInTheDocument()
  await userEvent.type(field(), '!')
  expect(screen.getByText(/Änderungen am Text wirken sich nicht aus/)).toBeVisible()
  await userEvent.clear(field())
  expect(screen.queryByText(/Änderungen am Text/)).not.toBeInTheDocument()
})

test('two open confirmations do not share an id', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({
    'GET /postings/p-9': { body: { posting: { title: 'Lead Engineer Video', company: 'Musterdienst GmbH' } } },
    'GET /alert-mails/runs/r1': { body: run([
      row(1, 'duplicate', { posting_id: 'p-9', duplicate_by: 'text' }),
      row(2, 'duplicate', { posting_id: 'p-9', duplicate_by: 'text' }),
    ], { status: 'done' }) },
  })
  view()
  for (const button of await screen.findAllByRole('button', { name: 'Trotzdem als neue Anzeige speichern' })) {
    await userEvent.click(button)
  }
  const ids = screen.getAllByRole('group', { name: /Als neue Anzeige speichern\?/ })
    .map((group) => group.getAttribute('aria-labelledby'))
  expect(new Set(ids).size).toBe(2)
})

test('an entry without a title shows its link as the name', async () => {
  stubApi(found([entry(1, { title: '' })]))
  view()
  await findStellen()
  expect(screen.getByRole('checkbox', { name: entry(1).url })).toBeVisible()
})

test('the store-anyway action waits while the run still computes', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ ...TEXT_DUPLICATE, 'GET /alert-mails/runs/r1': { body: run([
    row(1, 'duplicate', { posting_id: 'p-9', duplicate_by: 'text' }), row(2, 'running')]) } })
  view()
  await screen.findByRole('list', { name: 'Stand je Anzeige' })
  expect(screen.queryByRole('button', { name: 'Trotzdem als neue Anzeige speichern' })).not.toBeInTheDocument()
})

// ---- 7.2: run refused, lost, crashed, resumed ----

test('a run refused with 409 attaches to the computing run', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  stubApi({
    ...found([entry(1)]),
    'POST /alert-mails/runs': { status: 409, body: { error: 'alert run in progress', detail: 'x', run_id: 'r7' } },
    'GET /alert-mails/runs/r7': { body: run([row(1, 'running')], { run_id: 'r7' }) },
  })
  view()
  await findStellen()
  await userEvent.click(screen.getByRole('button', { name: '1 Anzeige hinzufügen' }))
  expect(await screen.findByRole('list', { name: 'Stand je Anzeige' })).toBeVisible()
  expect(sessionStorage.getItem(RUN_KEY)).toBe('r7')
})

test('a refused start for another reason says so and keeps the pick list', async () => {
  stubApi({ ...found([entry(1)]), 'POST /alert-mails/runs': { status: 422, body: { error: 'invalid request', detail: 'x' } } })
  view()
  await findStellen()
  await userEvent.click(screen.getByRole('button', { name: '1 Anzeige hinzufügen' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Der Lauf konnte nicht gestartet werden')
  expect(screen.getByRole('list', { name: 'Gefundene Stellen' })).toBeVisible()
})

test('a run the server no longer knows says so and offers to paste the mail again', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { status: 404, body: { error: 'not found', detail: 'x' } } })
  view()
  expect(await screen.findByRole('heading', { name: 'Lauf nicht mehr bekannt' })).toBeVisible()
  expect(sessionStorage.getItem(RUN_KEY)).toBeNull()
  await userEvent.click(screen.getByRole('button', { name: 'Mail noch einmal einfügen' }))
  expect(field()).toHaveValue('')
})

test('a run that ended failed says so and keeps its rows', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: run([
    row(1, 'stored', { posting_id: 'p-1' }), row(2, 'stored', { posting_id: 'p-2' }), row(3, 'waiting')],
  { status: 'failed', error: 'RuntimeError' }) } })
  view()
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('Der Lauf ist abgebrochen')
  expect(alert).toHaveTextContent('nach 2 von 3 Anzeigen')
  expect(alert).not.toHaveTextContent('RuntimeError')
  expect(screen.getByRole('list', { name: 'Stand je Anzeige' })).toBeVisible()
})

test('a stored run ID attaches after a remount and keeps polling', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem(RUN_KEY, 'r1')
  let reads = 0
  stubApi({ 'GET /alert-mails/runs/r1': () => ({ body: ++reads < 3 ? RUNNING : run(RUNNING.entries, { status: 'done' }) }) })
  const first = view()
  await screen.findByRole('list', { name: 'Stand je Anzeige' })
  first.unmount()
  view()
  await screen.findByRole('list', { name: 'Stand je Anzeige' })
  await act(() => vi.advanceTimersByTimeAsync(POLL_MS))
  expect(reads).toBeGreaterThanOrEqual(3)
})

test('polling that fails repeatedly says the state is not retrievable and offers a retry', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { status: 500, body: { error: 'x', detail: 'x' } } })
  view()
  await act(() => vi.advanceTimersByTimeAsync(POLL_MS * 4))
  expect(await screen.findByText('Der Stand des Laufs ist gerade nicht abrufbar')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Erneut versuchen' })).toBeVisible()
})

test('the run view has no accessibility violations', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ ...TEXT_DUPLICATE, 'GET /alert-mails/runs/r1': { body: run([
    row(1, 'stored', { posting_id: 'p-1' }),
    row(2, 'duplicate', { posting_id: 'p-9', duplicate_by: 'text' }),
    row(3, 'failed', { attempts: [{ step: 'plain', url: 'x', outcome: 'http 404' }] }),
  ], { status: 'done' }) } })
  const { container } = view()
  await screen.findByRole('list', { name: 'Stand je Anzeige' })
  await screen.findByRole('link', { name: /Lead Engineer Video/ })
  expect(await axe(container)).toHaveNoViolations()
})

// --- closed entries (3.6) ---------------------------------------------------------------------

const closedRun = () => run([
  row(1, 'stored', { posting_id: 'p-1' }),
  row(2, 'closed', { attempts: [{ step: 'plain', url: entry(2).url, outcome: 'HTTP 404' },
                                { step: 'loop:search_alternative_source', url: entry(2).url, outcome: 'ok' }] }),
  row(3, 'failed', { attempts: [{ step: 'plain', url: entry(3).url, outcome: 'HTTP 503' }] }),
], { status: 'done', done: 3 })

test('a closed row shows "Stelle geschlossen" with its attempts and offers no text or PDF', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: closedRun() } })
  view()
  const rows = rowsOf(await screen.findByRole('list', { name: 'Stand je Anzeige' }))
  expect(within(rows[1]).getByText('Stelle geschlossen')).toBeVisible()
  expect(rows[1]).toHaveTextContent('Nichts gespeichert.')
  expect(rows[1]).not.toHaveTextContent('Diese Versuche wurden gemacht')
  await userEvent.click(within(rows[1]).getByText('Details: 2 Versuche'))
  const attempts = within(rows[1]).getByRole('list')
  expect(attempts).toBeVisible()
  expect(attempts).toHaveTextContent('Einfacher Abruf: Stelle geschlossen (HTTP 404)')
  expect(attempts).toHaveTextContent('Websuche nach einer anderen Quelle: keine Anzeige gefunden')
  expect(within(rows[1]).queryByRole('button')).toBeNull()
  expect(within(rows[1]).getByRole('link', { name: `Anzeige „Stelle 2“ öffnen, neuer Tab: ${entry(2).url}` }))
    .toHaveAttribute('href', entry(2).url)
  expect(rows[1]).not.toHaveClass('border-danger')
  expect(within(rows[2]).getByRole('button', { name: 'Text einfügen' })).toBeVisible()
})

// ---- #158: attempts behind „Details“ ----

test('a closed row shows its text and link, and its attempts only behind a collapsed „Details: n Versuche“', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: closedRun() } })
  view()
  const rows = rowsOf(await screen.findByRole('list', { name: 'Stand je Anzeige' }))
  const closed = rows[1]
  expect(within(closed).getByText('Stelle geschlossen')).toBeVisible()
  expect(within(closed).getByText('Stelle 2')).toBeVisible()
  expect(within(closed).getByText(entry(2).url)).toBeVisible()
  expect(within(closed).getByText('Nichts gespeichert.')).toBeVisible()
  const summary = within(closed).getByText('Details: 2 Versuche')
  expect(summary.tagName).toBe('SUMMARY')
  expect(summary.closest('details')).not.toHaveAttribute('open')
  expect(within(closed).getByRole('list')).not.toBeVisible()
  expect(within(closed).getByText(/Einfacher Abruf: Stelle geschlossen/)).not.toBeVisible()
})

test('a click on „Details“ opens the attempts', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: closedRun() } })
  view()
  const rows = rowsOf(await screen.findByRole('list', { name: 'Stand je Anzeige' }))
  await userEvent.click(within(rows[1]).getByText('Details: 2 Versuche'))
  expect(rows[1].querySelector('details')).toHaveAttribute('open')
  expect(within(rows[1]).getByText(/Einfacher Abruf: Stelle geschlossen/)).toBeVisible()
  expect(within(rows[1]).getByText(/Websuche nach einer anderen Quelle/)).toBeVisible()
  expect(within(rows[2]).getByRole('list')).not.toBeVisible() // another row stays collapsed
})

test('„Details“ counts one attempt in the singular', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: run([
    row(1, 'closed', { attempts: [{ step: 'plain', url: entry(1).url, outcome: 'HTTP 410' }] })], { status: 'done' }) } })
  view()
  const [only] = rowsOf(await screen.findByRole('list', { name: 'Stand je Anzeige' }))
  expect(within(only).getByText('Details: 1 Versuch')).toBeVisible()
})

test('a closed entry counts as done in the heading and has its own filter', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: closedRun() } })
  view()
  expect(await screen.findByRole('heading', { name: '3 von 3 erledigt' })).toBeVisible()
  expect(filterNames()).toEqual(['Alle (3)', '1 hinzugefügt', '1 geschlossen', '1 nicht gelesen'])
})

test('a running run counts a closed entry as finished and does not call the rest "nicht gestartet"', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: run([
    row(1, 'closed', { attempts: [{ step: 'plain', url: entry(1).url, outcome: 'HTTP 410' }] }),
    row(2, 'running')], { done: 1 }) } })
  view()
  const rows = rowsOf(await screen.findByRole('list', { name: 'Stand je Anzeige' }))
  expect(within(rows[0]).getByText('Stelle geschlossen')).toBeVisible()
  expect(within(rows[1]).getByText('wird abgerufen…')).toBeVisible()
  expect(screen.getByRole('heading', { name: '1 von 2 erledigt' })).toBeVisible()
})

test('a crashed run counts a closed entry among the finished ones', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: run([
    row(1, 'closed', { attempts: [{ step: 'plain', url: entry(1).url, outcome: 'HTTP 404' }] }),
    row(2, 'waiting')], { status: 'failed', error: 'x', done: 1 }) } })
  view()
  expect(await screen.findByText(/nach 1 von 2 Anzeigen beendet/)).toBeVisible()
})

test('a closed run has no axe violations', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: closedRun() } })
  const { container } = view()
  await screen.findByRole('list', { name: 'Stand je Anzeige' })
  expect(await axe(container)).toHaveNoViolations()
})

// ---- #159: same link, entries that could not be judged ----

test('a row taken from an earlier entry shows its outcome, says the link was fetched once and links the same posting', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: run([
    row(1, 'stored', { posting_id: 'p-1' }),
    row(2, 'stored', { posting_id: 'p-1', same_as: 0 }),
  ], { status: 'done' }) } })
  view()
  const rows = rowsOf(await screen.findByRole('list', { name: 'Stand je Anzeige' }))
  expect(rows[0]).not.toHaveTextContent('Gleicher Link')
  expect(rows[1]).toHaveTextContent('Hinzugefügt')
  expect(rows[1]).toHaveTextContent('Gleicher Link wie oben, nur einmal abgerufen.')
  expect(within(rows[1]).getByRole('link', { name: 'Anzeige ansehen' })).toHaveAttribute('href', '#/anzeigen/p-1')
})

test('the filters count a link of two rows once', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: run([
    row(1, 'stored', { posting_id: 'p-1' }),
    row(2, 'stored', { posting_id: 'p-1', same_as: 0 }),
  ], { status: 'done' }) } })
  view()
  await screen.findByRole('group', { name: 'Filter' })
  expect(filterNames()).toEqual(['Alle (2)', '1 hinzugefügt'])
  expect(screen.getByRole('heading', { name: '2 von 2 erledigt' })).toBeVisible()
})

test('a failed row that could not be judged says so, lists its attempts and offers text and PDF', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: run([
    row(1, 'failed', { unclear: true, attempts: [{ step: 'plain', url: entry(1).url, outcome: 'HTTP 404' },
                                               { step: 'rendered', url: entry(1).url, outcome: 'HTTP 429' }] }),
  ], { status: 'done' }) } })
  view()
  const [failed] = rowsOf(await screen.findByRole('list', { name: 'Stand je Anzeige' }))
  expect(within(failed).getByText('Nicht beurteilbar')).toBeVisible()
  expect(failed).not.toHaveTextContent('Nicht gelesen')
  expect(failed).toHaveTextContent('Der Link hat einmal geantwortet, die Stelle sei geschlossen, andere Abrufe wurden aber abgewiesen. Ob sie wirklich geschlossen ist, ist unklar.')
  expect(within(failed).getByText(/Der Link hat einmal geantwortet/).closest('details')).toBeNull()
  expect(within(failed).getByText(/Der Link hat einmal geantwortet/)).toBeVisible()
  expect(within(failed).getByRole('button', { name: 'Text einfügen' }).closest('details')).toBeNull()
  expect(within(failed).getByRole('button', { name: 'Text einfügen' })).toBeVisible()
  expect(within(failed).getByRole('button', { name: 'PDF hochladen' })).toBeVisible()
  expect(within(failed).getByRole('list')).not.toBeVisible()
  await userEvent.click(within(failed).getByText('Details: 2 Versuche'))
  expect(within(failed).getByRole('list')).toBeVisible()
  expect(within(failed).getByRole('list')).toHaveTextContent('Einfacher Abruf: Stelle geschlossen (HTTP 404)')
  expect(filterNames()).toEqual(['Alle (1)', '1 nicht beurteilbar'])
})

test('the link of a row that could not be judged opens the original ad in a new tab', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: run([
    row(1, 'failed', { unclear: true, title: 'Data Engineer', url: 'https://jobs.example.com/data-engineer/1',
                       attempts: [{ step: 'plain', url: 'https://jobs.example.com/data-engineer/1', outcome: 'HTTP 404' }] }),
  ], { status: 'done' }) } })
  view()
  const [failed] = rowsOf(await screen.findByRole('list', { name: 'Stand je Anzeige' }))
  const link = within(failed).getByRole('link', { name: 'Anzeige „Data Engineer“ öffnen, neuer Tab: https://jobs.example.com/data-engineer/1' })
  expect(link).toHaveAttribute('href', 'https://jobs.example.com/data-engineer/1')
  expect(link).toHaveAttribute('target', '_blank')
  expect(link).toHaveAttribute('rel', 'noopener noreferrer')
})

test('a row whose address is not http(s) shows it as text, not as a link', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: run([
    row(1, 'failed', { url: 'ftp://files.example.com/job' })], { status: 'done' }) } })
  view()
  const [failed] = rowsOf(await screen.findByRole('list', { name: 'Stand je Anzeige' }))
  expect(within(failed).getByText('ftp://files.example.com/job')).toBeVisible()
  expect(within(failed).queryByRole('link')).toBeNull()
})

// ---- #153: cancel a run ----

const cancelButton = () => screen.getByRole('button', { name: /Lauf abbrechen|Wird abgebrochen/ })

test('a running run offers "Lauf abbrechen" with what it does, and pressing it cancels at once and waits', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  const calls = stubApi({ 'GET /alert-mails/runs/r1': { body: RUNNING },
                          'POST /alert-mails/runs/r1/cancel': { status: 202, body: { run_id: 'r1' } } })
  view()
  await screen.findByRole('list', { name: 'Stand je Anzeige' })
  expect(cancelButton()).toHaveTextContent('Lauf abbrechen')
  expect(cancelButton()).not.toHaveAttribute('aria-disabled')
  expect(cancelButton()).toHaveAccessibleDescription('Der Lauf stoppt nach der aktuellen Anzeige. Was gespeichert ist, bleibt gespeichert.')
  await userEvent.click(cancelButton())
  expect(calls.filter((call) => call.path === '/alert-mails/runs/r1/cancel')).toHaveLength(1)
  expect(cancelButton()).toHaveTextContent('Wird abgebrochen …')
  expect(cancelButton()).toHaveAttribute('aria-disabled', 'true')
  await userEvent.click(cancelButton())
  expect(calls.filter((call) => call.path === '/alert-mails/runs/r1/cancel')).toHaveLength(1)
})

test('a run that reports cancel_requested shows the waiting button without a press', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: { ...RUNNING, cancel_requested: true } } })
  view()
  await screen.findByRole('list', { name: 'Stand je Anzeige' })
  expect(cancelButton()).toHaveTextContent('Wird abgebrochen …')
  expect(cancelButton()).toHaveAttribute('aria-disabled', 'true')
})

test('a cancel request that fails says so and offers the button again', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: RUNNING }, 'POST /alert-mails/runs/r1/cancel': { status: 500 } })
  view()
  await screen.findByRole('list', { name: 'Stand je Anzeige' })
  await userEvent.click(cancelButton())
  expect(await screen.findByRole('alert')).toHaveTextContent('Das Abbrechen hat nicht geklappt')
  expect(cancelButton()).toHaveTextContent('Lauf abbrechen')
  expect(cancelButton()).not.toHaveAttribute('aria-disabled')
})

test('a cancel refused because the run ended is left to the next poll', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: RUNNING },
            'POST /alert-mails/runs/r1/cancel': { status: 409, body: { error: 'run not running', detail: 'x' } } })
  view()
  await screen.findByRole('list', { name: 'Stand je Anzeige' })
  await userEvent.click(cancelButton())
  expect(screen.queryByRole('alert')).toBeNull()
  expect(cancelButton()).toHaveAttribute('aria-disabled', 'true')
})

test('a running and a cancelled run have no accessibility violations', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: RUNNING } })
  const first = view()
  await screen.findByRole('list', { name: 'Stand je Anzeige' })
  expect(await axe(first.container)).toHaveNoViolations()
  first.unmount()
  stubApi({ 'GET /alert-mails/runs/r1': { body: run([row(1, 'stored', { posting_id: 'p-1' }), row(2, 'waiting')],
                                                     { status: 'cancelled', cancel_requested: true }) } })
  const second = view()
  await screen.findByText('Abgebrochen nach 1 von 2 Anzeigen')
  expect(await axe(second.container)).toHaveNoViolations()
})

test('an ended run offers no cancel button', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: run([row(1, 'stored', { posting_id: 'p-1' })], { status: 'done' }) } })
  view()
  await screen.findByRole('list', { name: 'Stand je Anzeige' })
  expect(screen.queryByRole('button', { name: /Lauf abbrechen|Wird abgebrochen/ })).toBeNull()
})

test('a cancelled pasted run says after how many entries, shows the rest as not started and says to paste the mail again', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  const rows = Array.from({ length: 10 }, (_, i) => i < 4 ? row(i + 1, 'stored', { posting_id: `p-${i + 1}` }) : row(i + 1, 'waiting'))
  stubApi({ 'GET /alert-mails/runs/r1': { body: run(rows, { status: 'cancelled', cancel_requested: true }) } })
  view()
  const list = await screen.findByRole('list', { name: 'Stand je Anzeige' })
  expect(screen.getByText('Abgebrochen nach 4 von 10 Anzeigen')).toBeVisible()
  expect(screen.getByText('Füge die Mail erneut ein, um die übrigen hinzuzufügen. Was schon gespeichert ist, erscheint dann als gespeichert.')).toBeVisible()
  expect(rowsOf(list).filter((item) => item.textContent?.includes('nicht gestartet'))).toHaveLength(6)
  expect(screen.queryByRole('button', { name: /Lauf abbrechen|Wird abgebrochen/ })).toBeNull()
  expect(screen.getByRole('button', { name: 'Andere Mail einfügen' })).toBeVisible()
  expect(screen.queryByText(/Die nächste Prüfung/)).toBeNull()
})

test('a pasted run with failed entries does not promise that the next check offers their mails', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: run([row(1, 'failed')], { status: 'done' }) } })
  view()
  await screen.findByRole('list', { name: 'Stand je Anzeige' })
  expect(screen.queryByText(/Die nächste Prüfung/)).toBeNull()
})

// ---- #162: filter by outcome ----

const JUDGED = [{ step: 'plain', url: entry(8).url, outcome: 'HTTP 404' }, { step: 'rendered', url: entry(8).url, outcome: 'HTTP 429' }]

/** Nine rows of a finished run: 3 added, 2 stored before, 1 closed, 2 not read (one a repeat of a link), 1 not assessable. */
const MIXED = () => run([
  row(1, 'stored', { posting_id: 'p-1' }), row(2, 'stored', { posting_id: 'p-2' }), row(3, 'stored', { posting_id: 'p-3' }),
  row(4, 'duplicate', { posting_id: 'p-9', duplicate_by: 'url' }), row(5, 'duplicate', { posting_id: 'p-9', duplicate_by: 'url' }),
  row(6, 'closed', { attempts: [{ step: 'plain', url: entry(6).url, outcome: 'HTTP 404' }] }),
  row(7, 'failed', { attempts: [{ step: 'plain', url: entry(7).url, outcome: 'HTTP 503' }] }),
  row(8, 'failed', { unclear: true, attempts: JUDGED }),
  row(9, 'failed', { same_as: 6 }),
], { status: 'done' })

const titlesOf = () => rowsOf(screen.getByRole('list', { name: 'Stand je Anzeige' }))
  .map((item) => /Stelle \d/.exec(item.textContent ?? '')?.[0])

async function openMixed() {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: MIXED() } })
  view()
  await screen.findByRole('group', { name: 'Filter' })
}

test('a finished run offers "Alle" with the number of rows and one filter per outcome that occurs, "Alle" active', async () => {
  await openMixed()
  expect(filterNames()).toEqual(['Alle (9)', '3 hinzugefügt', '2 schon gespeichert', '1 geschlossen', '1 nicht gelesen', '1 nicht beurteilbar'])
  expect(filterButton('Alle (9)')).toHaveAttribute('aria-pressed', 'true')
  expect(filterButton('3 hinzugefügt')).toHaveAttribute('aria-pressed', 'false')
  expect(titlesOf()).toHaveLength(9)
  expect(screen.getByText('Prüfe Titel, Firma und Ort der neuen Anzeigen auf ihren Seiten.')).toBeVisible()
  expect(screen.queryByText(/^3 hinzugefügt,/)).toBeNull()
})

test('a filter shows only the rows of its outcome, and choosing it again or "Alle" shows every row again', async () => {
  await openMixed()
  await userEvent.click(filterButton('2 schon gespeichert'))
  expect(filterButton('2 schon gespeichert')).toHaveAttribute('aria-pressed', 'true')
  expect(filterButton('Alle (9)')).toHaveAttribute('aria-pressed', 'false')
  expect(titlesOf()).toEqual(['Stelle 4', 'Stelle 5'])
  await userEvent.click(filterButton('2 schon gespeichert'))
  expect(filterButton('Alle (9)')).toHaveAttribute('aria-pressed', 'true')
  expect(titlesOf()).toHaveLength(9)
  await userEvent.click(filterButton('1 geschlossen'))
  expect(titlesOf()).toEqual(['Stelle 6'])
  await userEvent.click(filterButton('Alle (9)'))
  expect(filterButton('Alle (9)')).toHaveAttribute('aria-pressed', 'true')
  expect(titlesOf()).toHaveLength(9)
})

test('the counts stay those of the whole run while a filter is active', async () => {
  await openMixed()
  await userEvent.click(filterButton('3 hinzugefügt'))
  expect(filterNames()).toEqual(['Alle (9)', '3 hinzugefügt', '2 schon gespeichert', '1 geschlossen', '1 nicht gelesen', '1 nicht beurteilbar'])
})

test('the filter for the entries that could not be judged keeps their text and PDF options', async () => {
  const onText = vi.fn()
  const onPdf = vi.fn()
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: MIXED() } })
  view({ onText, onPdf })
  await userEvent.click(await within(await screen.findByRole('group', { name: 'Filter' })).findByRole('button', { name: '1 nicht beurteilbar' }))
  const [only, ...rest] = rowsOf(screen.getByRole('list', { name: 'Stand je Anzeige' }))
  expect(rest).toHaveLength(0)
  expect(only).toHaveTextContent('Nicht beurteilbar')
  await userEvent.click(within(only).getByRole('button', { name: 'Text einfügen' }))
  await userEvent.click(within(only).getByRole('button', { name: 'PDF hochladen' }))
  expect(onText).toHaveBeenCalled()
  expect(onPdf).toHaveBeenCalled()
})

test('a filter drops the repeat of a link, "Alle" keeps it, and the counts count the link once', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: run([
    row(1, 'closed', { attempts: [] }), row(2, 'closed', { attempts: [], same_as: 0 }),
  ], { status: 'done' }) } })
  view()
  await screen.findByRole('group', { name: 'Filter' })
  expect(filterNames()).toEqual(['Alle (2)', '1 geschlossen'])
  await userEvent.click(filterButton('1 geschlossen'))
  expect(titlesOf()).toEqual(['Stelle 1'])
  await userEvent.click(filterButton('Alle (2)'))
  expect(titlesOf()).toEqual(['Stelle 1', 'Stelle 2'])
})

test('the status line says how many rows the list shows, of how many, and which outcome, and is announced', async () => {
  await openMixed()
  expect(statusLine()).toHaveTextContent('Zeigt alle 9 Anzeigen')
  expect(statusLine()).toHaveAttribute('role', 'status')
  await userEvent.click(filterButton('1 nicht beurteilbar'))
  expect(filterButton('1 nicht beurteilbar')).toHaveAttribute('aria-pressed', 'true')
  expect(statusLine()).toHaveTextContent('Zeigt 1 von 9 Anzeigen: nicht beurteilbar')
  await userEvent.click(filterButton('3 hinzugefügt'))
  expect(statusLine()).toHaveTextContent('Zeigt 3 von 9 Anzeigen: hinzugefügt')
  await userEvent.click(filterButton('Alle (9)'))
  expect(statusLine()).toHaveTextContent('Zeigt alle 9 Anzeigen')
})

test('the filter row sits below the progress bar and above the list, and has no accessibility violations', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: RUNNING } })
  const { container } = view()
  const list = await screen.findByRole('list', { name: 'Stand je Anzeige' })
  const bar = screen.getByRole('progressbar', { name: 'Fortschritt' })
  expect(bar.compareDocumentPosition(filters()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(filters().compareDocumentPosition(statusLine()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(statusLine().compareDocumentPosition(list) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(await axe(container)).toHaveNoViolations()
})

// ---- #162: the filter while the run computes ----

const UNREAD = (n: number) => row(n, 'failed', { attempts: [{ step: 'plain', url: entry(n).url, outcome: 'HTTP 503' }] })

test('a filter shows while the run computes, its count grows with each entry, and the entry that ends with it joins the list', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem(RUN_KEY, 'r1')
  let polls = 0
  const states = [
    run([UNREAD(1), UNREAD(2), row(3, 'running'), row(4, 'waiting')]),
    run([UNREAD(1), UNREAD(2), UNREAD(3), row(4, 'running')]),
    run([UNREAD(1), UNREAD(2), UNREAD(3), row(4, 'closed', { attempts: [] })], { status: 'done' }),
  ]
  stubApi({ 'GET /alert-mails/runs/r1': () => ({ body: states[Math.min(polls++, states.length - 1)] }) })
  view()
  await screen.findByRole('group', { name: 'Filter' })
  expect(filterNames()).toEqual(['Alle (4)', '2 nicht gelesen'])
  await userEvent.click(filterButton('2 nicht gelesen'))
  expect(titlesOf()).toEqual(['Stelle 1', 'Stelle 2'])
  expect(statusLine()).toHaveTextContent('Zeigt 2 von 4 Anzeigen: nicht gelesen')

  await act(() => vi.advanceTimersByTimeAsync(POLL_MS))
  expect(filterButton('3 nicht gelesen')).toHaveAttribute('aria-pressed', 'true')
  expect(titlesOf()).toEqual(['Stelle 1', 'Stelle 2', 'Stelle 3'])
  expect(statusLine()).toHaveTextContent('Zeigt 3 von 4 Anzeigen: nicht gelesen')

  await act(() => vi.advanceTimersByTimeAsync(POLL_MS))
  expect(filterNames()).toEqual(['Alle (4)', '1 geschlossen', '3 nicht gelesen']) // a filter appears once its outcome occurs
  expect(titlesOf()).toEqual(['Stelle 1', 'Stelle 2', 'Stelle 3'])
})

test('entries that wait or are being added show only under "Alle", and a filter does not list them', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: run([
    row(1, 'stored', { posting_id: 'p-1' }), row(2, 'running'), row(3, 'waiting'), UNREAD(4)]) } })
  view()
  await screen.findByRole('group', { name: 'Filter' })
  expect(titlesOf()).toEqual(['Stelle 1', 'Stelle 2', 'Stelle 3', 'Stelle 4'])
  expect(filterNames()).toEqual(['Alle (4)', '1 hinzugefügt', '1 nicht gelesen'])
  for (const name of ['1 hinzugefügt', '1 nicht gelesen']) {
    await userEvent.click(filterButton(name))
    expect(titlesOf()).toHaveLength(1)
    await userEvent.click(filterButton(name))
  }
  expect(titlesOf()).toHaveLength(4)
})

test('under a filter the status line text does not change while other entries end', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem(RUN_KEY, 'r1')
  let polls = 0
  const states = [
    run([UNREAD(1), row(2, 'running'), row(3, 'waiting')]),
    run([UNREAD(1), row(2, 'stored', { posting_id: 'p-2' }), row(3, 'running')]),
  ]
  stubApi({ 'GET /alert-mails/runs/r1': () => ({ body: states[Math.min(polls++, states.length - 1)] }) })
  view()
  await screen.findByRole('group', { name: 'Filter' })
  await userEvent.click(filterButton('1 nicht gelesen'))
  const line = statusLine()
  const text = line.textContent
  await act(() => vi.advanceTimersByTimeAsync(POLL_MS))
  expect(filterNames()).toEqual(['Alle (3)', '1 hinzugefügt', '1 nicht gelesen'])
  expect(statusLine()).toBe(line)
  expect(line.textContent).toBe(text)
})

// ---- #162: a row stored anyway keeps its place ----

type Routes = Parameters<typeof stubApi>[0]
const TEXT_DUP = (n: number) => row(n, 'duplicate', { posting_id: 'p-9', duplicate_by: 'text' })

/** A finished run r1 of `rows` whose text duplicates can be stored anyway. `forced` maps the ID of each
 * stored-anyway run (r2, r3, in the order they start) to the number of the row it stores; such a run
 * reports `running` until `finish(id)`, then stored. */
function forceable(rows: AlertRunState['entries'], forced: Record<string, number>) {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  sessionStorage.setItem(RUN_KEY, 'r1')
  const finished = new Set<string>()
  const ids = Object.keys(forced)
  const routes: Routes = {
    'GET /postings/p-9': { body: { posting: { title: 'Lead Engineer Video', company: 'Musterdienst GmbH' } } },
    'GET /alert-mails/runs/r1': { body: run(rows, { status: 'done' }) },
    'POST /alert-mails/runs': () => ({ status: 202, body: { run_id: ids.shift() } }),
  }
  for (const [id, n] of Object.entries(forced)) {
    routes[`GET /alert-mails/runs/${id}`] = () => ({ body: finished.has(id)
      ? run([row(n, 'stored', { posting_id: `p-1${n}` })], { run_id: id, status: 'done' })
      : run([row(n, 'running')], { run_id: id }) })
  }
  stubApi(routes)
  return { finish: (id: string) => act(async () => { finished.add(id); await vi.advanceTimersByTimeAsync(POLL_MS) }) }
}

const rowOf = (n: number) => rowsOf(screen.getByRole('list', { name: 'Stand je Anzeige' }))
  .find((item) => item.textContent?.includes(`Stelle ${n}`))!

/** Stores the text duplicate of row `n` anyway, confirming with the keyboard. */
async function storeAnyway(n: number) {
  await userEvent.click(within(rowOf(n)).getByRole('button', { name: 'Trotzdem als neue Anzeige speichern' }))
  const yes = await screen.findByRole('button', { name: 'Ja, als neue Anzeige speichern' })
  yes.focus()
  await userEvent.keyboard('{Enter}')
}

test('a text duplicate stored anyway under "schon gespeichert" stays in the list, fetched and then added, and the counts move by one', async () => {
  const forced = forceable([TEXT_DUP(1), row(2, 'stored', { posting_id: 'p-2' }), row(3, 'duplicate', { posting_id: 'p-9', duplicate_by: 'url' })], { r2: 1 })
  view()
  await screen.findByRole('group', { name: 'Filter' })
  await userEvent.click(filterButton('2 schon gespeichert'))
  expect(titlesOf()).toEqual(['Stelle 1', 'Stelle 3'])
  await storeAnyway(1)
  await screen.findByText('wird abgerufen…')
  expect(titlesOf()).toEqual(['Stelle 1', 'Stelle 3'])
  expect(rowOf(1)).toHaveTextContent('wird abgerufen…')
  expect(filterNames()).toEqual(['Alle (3)', '1 hinzugefügt', '1 schon gespeichert'])
  expect(statusLine()).toHaveTextContent('Zeigt 2 von 3 Anzeigen: schon gespeichert')
  await forced.finish('r2')
  expect(rowOf(1)).toHaveTextContent('Hinzugefügt')
  expect(titlesOf()).toEqual(['Stelle 1', 'Stelle 3'])
  expect(filterNames()).toEqual(['Alle (3)', '2 hinzugefügt', '1 schon gespeichert'])
  expect(filterButton('1 schon gespeichert')).toHaveAttribute('aria-pressed', 'true')
  expect(statusLine()).toHaveTextContent('Zeigt 2 von 3 Anzeigen: schon gespeichert')
})

test('the last entry of the active filter stored anyway leaves "0 schon gespeichert" pressed with its row, until another filter is chosen', async () => {
  const forced = forceable([TEXT_DUP(1), row(2, 'stored', { posting_id: 'p-2' }), UNREAD(3)], { r2: 1 })
  view()
  await screen.findByRole('group', { name: 'Filter' })
  await userEvent.click(filterButton('1 schon gespeichert'))
  await storeAnyway(1)
  await screen.findByText('wird abgerufen…')
  expect(filterButton('0 schon gespeichert')).toHaveAttribute('aria-pressed', 'true')
  await forced.finish('r2')
  expect(filterNames()).toEqual(['Alle (3)', '2 hinzugefügt', '0 schon gespeichert', '1 nicht gelesen'])
  expect(filterButton('0 schon gespeichert')).toHaveAttribute('aria-pressed', 'true')
  expect(titlesOf()).toEqual(['Stelle 1'])
  expect(rowOf(1)).toHaveTextContent('Hinzugefügt')
  expect(statusLine()).toHaveTextContent('Zeigt 1 von 3 Anzeigen: schon gespeichert')
  await userEvent.click(filterButton('Alle (3)'))
  expect(filterNames()).toEqual(['Alle (3)', '2 hinzugefügt', '1 nicht gelesen'])
})

test.each([
  ['without a filter', null],
  ['under a filter', '2 schon gespeichert'],
])('focus moves to the row\'s outcome line when the store-anyway confirm is taken, and stays on it, %s', async (_name, filter) => {
  const forced = forceable([TEXT_DUP(1), row(2, 'stored', { posting_id: 'p-2' }), row(3, 'duplicate', { posting_id: 'p-9', duplicate_by: 'url' })], { r2: 1 })
  view()
  await screen.findByRole('group', { name: 'Filter' })
  if (filter) await userEvent.click(filterButton(filter))
  await storeAnyway(1)
  const line = await screen.findByText('wird abgerufen…')
  expect(screen.queryByRole('group', { name: /Als neue Anzeige speichern\?/ })).toBeNull()
  expect(document.activeElement).toBe(line)
  expect(line).toHaveAttribute('tabindex', '-1')
  await forced.finish('r2')
  expect(line).toBeInTheDocument()
  expect(line).toHaveTextContent('Hinzugefügt')
  expect(document.activeElement).toBe(line)
})

test('two text duplicates stored anyway in a row both stay in the list under "schon gespeichert"', async () => {
  const forced = forceable([TEXT_DUP(1), TEXT_DUP(2), row(3, 'stored', { posting_id: 'p-3' })], { r2: 1, r3: 2 })
  view()
  await screen.findByRole('group', { name: 'Filter' })
  await userEvent.click(filterButton('2 schon gespeichert'))
  await storeAnyway(1)
  await screen.findByText('wird abgerufen…')
  await forced.finish('r2')
  expect(titlesOf()).toEqual(['Stelle 1', 'Stelle 2'])
  await storeAnyway(2)
  await forced.finish('r3')
  expect(titlesOf()).toEqual(['Stelle 1', 'Stelle 2'])
  expect(rowOf(1)).toHaveTextContent('Hinzugefügt')
  expect(rowOf(2)).toHaveTextContent('Hinzugefügt')
  expect(filterNames()).toEqual(['Alle (3)', '3 hinzugefügt', '0 schon gespeichert'])
  expect(statusLine()).toHaveTextContent('Zeigt 2 von 3 Anzeigen: schon gespeichert')
})

test('choosing another filter drops the rows stored anyway from the list', async () => {
  const forced = forceable([TEXT_DUP(1), row(2, 'stored', { posting_id: 'p-2' }), row(3, 'duplicate', { posting_id: 'p-9', duplicate_by: 'url' })], { r2: 1 })
  view()
  await screen.findByRole('group', { name: 'Filter' })
  await userEvent.click(filterButton('2 schon gespeichert'))
  await storeAnyway(1)
  await screen.findByText('wird abgerufen…')
  await forced.finish('r2')
  await userEvent.click(filterButton('2 hinzugefügt'))
  expect(titlesOf()).toEqual(['Stelle 1', 'Stelle 2'])
  await userEvent.click(filterButton('1 schon gespeichert'))
  expect(titlesOf()).toEqual(['Stelle 3'])
})
