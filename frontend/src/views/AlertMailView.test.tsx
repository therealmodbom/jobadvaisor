import { act, fireEvent, render, screen, within } from '@testing-library/react'
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

const done = (state: AlertRunState['entries'][number]['state']) => ['stored', 'duplicate', 'failed'].includes(state)

const run = (entries: AlertRunState['entries'], over: Partial<AlertRunState> = {}): AlertRunState => ({
  run_id: 'r1', status: 'running', error: null, total: entries.length,
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
  expect(screen.getByText(/3 hinzugefügt/)).toBeVisible()
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
  expect(rows[1]).toHaveTextContent('Seite mit Login-Pflicht: übersprungen')
  expect(rows[1]).toHaveTextContent('Websuche nach einer anderen Quelle: keine Anzeige gefunden')
  await userEvent.click(within(rows[1]).getByRole('button', { name: 'Text einfügen' }))
  await userEvent.click(within(rows[1]).getByRole('button', { name: 'PDF hochladen' }))
  expect(onText).toHaveBeenCalled()
  expect(onPdf).toHaveBeenCalled()
  expect(screen.getByText(/2 hinzugefügt, 1 nicht gelesen/)).toBeVisible()
})

test('a failed row without attempts shows no English reason but the fallback', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /alert-mails/runs/r1': { body: run([row(1, 'failed', { reason: 'ConnectError' })], { status: 'done' }) } })
  view()
  const rows = rowsOf(await screen.findByRole('list', { name: 'Stand je Anzeige' }))
  expect(rows[0]).not.toHaveTextContent('ConnectError')
  expect(within(rows[0]).getByRole('button', { name: 'Text einfügen' })).toBeVisible()
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
