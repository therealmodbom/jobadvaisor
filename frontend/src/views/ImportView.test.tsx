import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import type { ImportConflict, ImportMapping, ImportPreview, ImportState } from '@/api'
import { axe } from '@/test-axe'
import { pending, stubApi } from '@/test-api'
import { ImportView } from './ImportView'
import { POLL_MS } from './PoolView'

const COUNTS = { imported: 12, duplicate: 3, skipped_status: 2, skipped_gone: 1, failed: 2 }
const state = (changes: Partial<ImportState>): ImportState => ({
  import_id: 'im1', status: 'running', error: null, total: 20, done: 0,
  counts: { imported: 0, duplicate: 0, skipped_status: 0, skipped_gone: 0, failed: 0 },
  not_imported: [], conflicts: [], tables_left_out: [], ...changes })

const CONFLICTS: ImportConflict[] = [
  { posting_id: 'p1', title: 'Backend Engineer', company: 'Harbor GmbH', status: 'open', list_status: 'applied' },
  { posting_id: 'p2', title: 'Data Engineer', company: 'Lindqvist', status: 'applied', list_status: 'done' },
]
const withConflicts = () => state({ status: 'done', done: 20, counts: COUNTS, conflicts: CONFLICTS })

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  sessionStorage.clear()
})

const tick = () => act(() => vi.advanceTimersByTimeAsync(POLL_MS))

const PREVIEW: ImportPreview = {
  tables: [
    { name: 'Offen', columns: ['Titel', 'Firma', 'Link', 'Stand', 'Notiz'], entries: 5 },
    { name: 'Archiv', columns: ['Titel', 'Link', 'stand', 'Grund'], entries: 1 },
  ],
  values: {
    Stand: ['Offen', 'offen', 'Beworben', 'Abgesagt'],
    Notiz: ['gut', 'mäßig'],
  },
  mapping: null,
}
const WITH_PREVIEW = { 'POST /imports/preview': { body: PREVIEW } }

const NOT_IMPORTED: ImportState['not_imported'] = [
  { row: 'Backend Engineer · Harbor GmbH', url: 'https://harbor.example/jobs/1', outcome: 'failed', reason: 'browser failed: timeout' },
  { row: 'Data Engineer · Lindqvist', url: 'https://lindqvist.example/jobs/2', outcome: 'skipped_status', reason: 'Stelle weg' },
  { row: 'Platform Engineer · Nordlicht', url: 'https://nordlicht.example/jobs/3', outcome: 'skipped_gone', reason: 'HTTP 410' },
  { row: 'Eintrag ohne sicheren Link', url: 'javascript:alert(1)', outcome: 'failed', reason: 'invalid link' },
]

const listFile = () => new File(['| Titel | Link |'], 'liste.md', { type: 'text/markdown' })

/** Choose a list file and press "Weiter"; the mapping form follows. */
async function toForm() {
  const file = listFile()
  await userEvent.upload(screen.getByLabelText('Liste als Markdown-Datei'), file)
  await userEvent.click(screen.getByRole('button', { name: 'Weiter' }))
  await screen.findByRole('button', { name: 'Import starten' })
  return file
}

/** Choose a list file, go through the mapping form unchanged and start the import. */
async function upload() {
  const file = await toForm()
  await userEvent.click(screen.getByRole('button', { name: 'Import starten' }))
  return file
}

function fakeTimers() {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
}

test('explains the list and that the file is not stored, with a labelled file input', () => {
  stubApi({})
  render(<ImportView />)
  expect(screen.getByText(/nicht gespeichert/)).toBeVisible()
  expect(screen.getByLabelText('Liste als Markdown-Datei')).toHaveAttribute('accept', '.md,text/markdown,text/plain')
  expect(screen.getByRole('button', { name: 'Weiter' })).toBeEnabled()
})

test('uploads the file as multipart "file", shows progress, then the report adding up', async () => {
  fakeTimers()
  let polls = 0
  const calls = stubApi({
    ...WITH_PREVIEW, 'POST /imports': { status: 202, body: { import_id: 'im1' } },
    'GET /imports/im1': () => ({ body: ++polls === 1 ? state({ done: 5 })
      : state({ status: 'done', done: 20, counts: COUNTS }) }),
  })
  render(<ImportView />)
  const file = await upload()
  const start = calls.find((call) => call.path === '/imports')?.body as { file: File }
  expect(start.file.name).toBe(file.name)
  expect(screen.getByRole('button', { name: /Weiter|Import läuft/ })).toBeDisabled()
  expect(await screen.findByText('5 von 20 Einträgen')).toBeVisible() // the first poll is immediate
  expect(screen.getByRole('progressbar', { name: 'Fortschritt des Imports' })).toHaveAttribute('value', '5')
  await tick()
  expect(screen.queryByRole('progressbar')).toBeNull()
  expect(screen.getByText('Importiert').nextElementSibling).toHaveTextContent('12')
  expect(screen.getByText('Schon vorhanden').nextElementSibling).toHaveTextContent('3')
  expect(screen.getByText('Übersprungen (Status)').nextElementSibling).toHaveTextContent('2')
  expect(screen.getByText('Übersprungen, Link nicht mehr erreichbar').nextElementSibling).toHaveTextContent('1')
  expect(screen.getByText('Fehlgeschlagen').nextElementSibling).toHaveTextContent('2')
  expect(screen.getByRole('link', { name: 'Zu den Anzeigen' })).toHaveAttribute('href', '#/pool')
  expect(screen.getByRole('button', { name: 'Weiter' })).toBeEnabled()
  expect(screen.queryByRole('heading', { name: 'Status weicht ab' })).toBeNull()
  expect(sessionStorage.getItem('jobadvaisor.import')).toBe('im1') // kept, a reload shows the report again
})

test('failed entries get a hint that the same file can be uploaded again', async () => {
  fakeTimers()
  stubApi({ ...WITH_PREVIEW, 'POST /imports': { status: 202, body: { import_id: 'im1' } },
            'GET /imports/im1': { body: state({ status: 'done', done: 20, counts: COUNTS }) } })
  render(<ImportView />)
  await upload()
  await tick()
  expect(screen.getByText(/dieselbe Datei noch einmal/)).toBeVisible()
})

test('no hint without failed entries', async () => {
  fakeTimers()
  stubApi({ ...WITH_PREVIEW, 'POST /imports': { status: 202, body: { import_id: 'im1' } },
            'GET /imports/im1': { body: state({ status: 'done', done: 20, counts: { ...COUNTS, failed: 0 } }) } })
  render(<ImportView />)
  await upload()
  await tick()
  expect(screen.getByText('Importiert')).toBeVisible()
  expect(screen.queryByText(/dieselbe Datei noch einmal/)).toBeNull()
})

test('the live region announces the start and the end, not the counts', async () => {
  fakeTimers()
  let polls = 0
  stubApi({ ...WITH_PREVIEW, 'POST /imports': { status: 202, body: { import_id: 'im1' } },
            'GET /imports/im1': () => ({ body: ++polls === 1 ? state({ done: 5 })
              : state({ status: 'done', done: 20, counts: COUNTS }) }) })
  render(<ImportView />)
  await upload()
  expect(screen.getByRole('status')).toHaveTextContent('Der Import läuft.')
  await tick()
  expect(screen.getByRole('status')).toHaveTextContent('Der Import ist fertig.')
  expect(screen.getByRole('status')).not.toHaveTextContent('12')
})

test('a stored import resumes polling after a reload', async () => {
  fakeTimers()
  sessionStorage.setItem('jobadvaisor.import', 'im1')
  stubApi({ 'GET /imports/im1': { body: state({ done: 7 }) } })
  render(<ImportView />)
  expect(screen.getByRole('button', { name: /Import läuft/ })).toBeDisabled()
  await tick()
  expect(screen.getByText('7 von 20 Einträgen')).toBeVisible()
})

test('a stored finished import shows its report again after a reload and stops polling', async () => {
  fakeTimers()
  sessionStorage.setItem('jobadvaisor.import', 'im1')
  const calls = stubApi({ 'GET /imports/im1': { body: withConflicts() } })
  render(<ImportView />)
  expect(await screen.findByRole('heading', { name: 'Status weicht ab' })).toBeVisible()
  expect(screen.getByText('Importiert').nextElementSibling).toHaveTextContent('12')
  expect(screen.getByRole('button', { name: 'Weiter' })).toBeEnabled()
  await tick()
  expect(calls).toHaveLength(1)
})

test('a new upload replaces the stored import and hides the old report', async () => {
  fakeTimers()
  sessionStorage.setItem('jobadvaisor.import', 'im1')
  stubApi({ 'GET /imports/im1': { body: withConflicts() },
            ...WITH_PREVIEW, 'POST /imports': { status: 202, body: { import_id: 'im2' } },
            'GET /imports/im2': { body: state({ import_id: 'im2', done: 1 }) } })
  render(<ImportView />)
  await tick()
  await upload()
  expect(sessionStorage.getItem('jobadvaisor.import')).toBe('im2')
  expect(screen.queryByRole('heading', { name: 'Status weicht ab' })).toBeNull()
})

function conflictRow(title: string) {
  return screen.getByRole('listitem', { name: title })
}

async function finishedWithConflicts() {
  fakeTimers()
  sessionStorage.setItem('jobadvaisor.import', 'im1')
  const calls = stubApi({
    'GET /imports/im1': { body: withConflicts() },
    'PATCH /postings/p1': { body: {} },
    'PATCH /postings/p2': { body: {} },
  })
  const view = render(<ImportView />)
  await tick()
  return { calls, view }
}

test('names each differing posting with both statuses in German and a link, never a URL', async () => {
  await finishedWithConflicts()
  const section = screen.getByRole('region', { name: 'Status weicht ab' })
  expect(section).toHaveTextContent('Diese Anzeigen sind schon gespeichert, aber deine Liste nennt einen anderen Status. Welcher gilt?')
  expect(screen.getByRole('link', { name: 'Backend Engineer' })).toHaveAttribute('href', '#/anzeigen/p1')
  expect(conflictRow('Backend Engineer')).toHaveTextContent('Harbor GmbH')
  expect(conflictRow('Backend Engineer')).toHaveTextContent('App: offen · Liste: beworben')
  expect(conflictRow('Data Engineer')).toHaveTextContent('App: beworben · Liste: erledigt')
  expect(section.innerHTML).not.toContain('http')
  expect(screen.getAllByRole('button', { name: 'Aus Liste übernehmen' })).toHaveLength(2)
  expect(screen.getAllByRole('button', { name: 'App behalten' })).toHaveLength(2)
})

test('"Aus Liste übernehmen" patches the list status, then confirms in place', async () => {
  const { calls } = await finishedWithConflicts()
  const row = within(conflictRow('Backend Engineer'))
  await userEvent.click(row.getByRole('button', { name: 'Aus Liste übernehmen' }))
  const patch = calls.find((call) => call.method === 'PATCH')
  expect(patch).toEqual({ method: 'PATCH', path: '/postings/p1', body: { status: 'applied' } })
  expect(await row.findByRole('status')).toHaveTextContent('Übernommen: beworben')
  expect(row.queryByRole('button')).toBeNull()
  expect(screen.getAllByRole('listitem').map((item) => item.getAttribute('aria-label')))
    .toEqual(['Backend Engineer', 'Data Engineer'])
  expect(row.getByRole('status')).toHaveFocus()
  expect(within(conflictRow('Data Engineer')).getAllByRole('button')).toHaveLength(2)
})

test('the button is inert but keeps focus while the status is saved', async () => {
  fakeTimers()
  sessionStorage.setItem('jobadvaisor.import', 'im1')
  const calls = stubApi({ 'GET /imports/im1': { body: withConflicts() }, 'PATCH /postings/p1': pending() })
  render(<ImportView />)
  await tick()
  const button = within(conflictRow('Backend Engineer')).getByRole('button', { name: 'Aus Liste übernehmen' })
  await userEvent.click(button)
  expect(button).toHaveAttribute('aria-disabled', 'true')
  expect(button).toHaveFocus() // a disabled button would drop keyboard focus to <body>
  await userEvent.click(button)
  expect(calls.filter((call) => call.method === 'PATCH')).toHaveLength(1)
})

test('a failed patch shows an error and keeps the button for a retry', async () => {
  fakeTimers()
  sessionStorage.setItem('jobadvaisor.import', 'im1')
  let attempts = 0
  const calls = stubApi({ 'GET /imports/im1': { body: withConflicts() },
    'PATCH /postings/p1': () => (++attempts === 1
      ? { status: 500, body: { error: 'boom', detail: '' } } : { body: {} }) })
  render(<ImportView />)
  await tick()
  const row = within(conflictRow('Backend Engineer'))
  await userEvent.click(row.getByRole('button', { name: 'Aus Liste übernehmen' }))
  expect(await row.findByRole('alert')).toHaveTextContent('Der Status wurde nicht gespeichert.')
  expect(row.getByRole('button', { name: 'Aus Liste übernehmen' })).not.toHaveAttribute('aria-disabled', 'true')
  expect(row.getByRole('button', { name: 'Aus Liste übernehmen' })).toHaveFocus()
  await userEvent.click(row.getByRole('button', { name: 'Aus Liste übernehmen' }))
  expect(await row.findByRole('status')).toHaveTextContent('Übernommen: beworben')
  expect(row.queryByRole('alert')).toBeNull()
  expect(calls.filter((call) => call.method === 'PATCH')).toHaveLength(2)
})

test('"App behalten" sends nothing and says the app status stays', async () => {
  const { calls } = await finishedWithConflicts()
  const row = within(conflictRow('Data Engineer'))
  await userEvent.click(row.getByRole('button', { name: 'App behalten' }))
  expect(row.getByText('App-Status bleibt: beworben')).toBeVisible()
  expect(row.queryByRole('button')).toBeNull()
  expect(calls.filter((call) => call.method !== 'GET')).toHaveLength(0)
  expect(within(conflictRow('Backend Engineer')).getAllByRole('button')).toHaveLength(2)
})

test('an import without conflicts shows no section', async () => {
  fakeTimers()
  sessionStorage.setItem('jobadvaisor.import', 'im1')
  stubApi({ 'GET /imports/im1': { body: state({ status: 'done', done: 20, counts: COUNTS }) } })
  render(<ImportView />)
  await tick()
  expect(screen.queryByRole('region', { name: 'Status weicht ab' })).toBeNull()
})

test('the section has no accessibility violations, open and decided', async () => {
  const { view } = await finishedWithConflicts()
  expect(await axe(view.container)).toHaveNoViolations()
  await userEvent.click(within(conflictRow('Backend Engineer')).getByRole('button', { name: 'Aus Liste übernehmen' }))
  await userEvent.click(within(conflictRow('Data Engineer')).getByRole('button', { name: 'App behalten' }))
  expect(await axe(view.container)).toHaveNoViolations()
})

test('an import already running says so', async () => {
  stubApi({ ...WITH_PREVIEW, 'POST /imports': { status: 409, body: { error: 'import in progress', detail: 'x' } } })
  render(<ImportView />)
  await upload()
  expect(await screen.findByRole('alert')).toHaveTextContent('Es läuft schon ein Import')
})

test('a file that is no text says so', async () => {
  stubApi({ ...WITH_PREVIEW, 'POST /imports': { status: 422, body: { error: 'invalid upload', detail: 'x' } } })
  render(<ImportView />)
  await upload()
  expect(await screen.findByRole('alert')).toHaveTextContent('nicht als Text gelesen')
})

test('an unreachable server offers a retry that uploads again', async () => {
  let attempts = 0
  const calls = stubApi({ ...WITH_PREVIEW, 'POST /imports': () => (++attempts === 1
    ? { status: 500, body: { error: 'boom', detail: '' } } : { status: 202, body: { import_id: 'im1' } }) })
  render(<ImportView />)
  await upload()
  expect(await screen.findByRole('alert')).toHaveTextContent('Der Import konnte nicht gestartet werden')
  await userEvent.click(screen.getByRole('button', { name: 'Import starten' }))
  expect(calls.filter((call) => call.path === '/imports')).toHaveLength(2)
  expect(screen.queryByRole('alert')).toBeNull()
})

test('submitting without a file asks for one', async () => {
  const calls = stubApi({})
  render(<ImportView />)
  await userEvent.click(screen.getByRole('button', { name: 'Weiter' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Wähle zuerst eine Datei')
  expect(calls).toHaveLength(0)
})

test('a failed import shows a message without the detail', async () => {
  fakeTimers()
  stubApi({ ...WITH_PREVIEW, 'POST /imports': { status: 202, body: { import_id: 'im1' } },
            'GET /imports/im1': { body: state({ status: 'failed', error: 'secret trace' }) } })
  render(<ImportView />)
  await upload()
  await tick()
  expect(screen.getByRole('alert')).toHaveTextContent('Der Import ist fehlgeschlagen')
  expect(screen.queryByText(/secret trace/)).toBeNull()
  expect(screen.getByRole('button', { name: 'Weiter' })).toBeEnabled()
})

test('a 404 for an import last seen running says it was interrupted', async () => {
  fakeTimers()
  let polls = 0
  stubApi({ ...WITH_PREVIEW, 'POST /imports': { status: 202, body: { import_id: 'im1' } },
            'GET /imports/im1': () => (++polls === 1 ? { body: state({ done: 5 }) }
              : { status: 404, body: { error: 'not found', detail: '' } }) })
  render(<ImportView />)
  await upload()
  await tick()
  expect(screen.getByRole('alert')).toHaveTextContent('Der Import wurde unterbrochen')
  expect(screen.getByRole('alert')).toHaveTextContent('noch einmal hochladen')
  expect(screen.getByRole('button', { name: 'Weiter' })).toBeEnabled()
  expect(sessionStorage.length).toBe(0)
})

test('a 404 for an import last seen finished clears the stored ID without a notice', async () => {
  fakeTimers()
  stubApi({ ...WITH_PREVIEW, 'POST /imports': { status: 202, body: { import_id: 'im1' } },
            'GET /imports/im1': { body: state({ status: 'done', done: 20, counts: COUNTS }) } })
  const first = render(<ImportView />)
  await upload()
  expect(await screen.findByText('Importiert')).toBeVisible()
  first.unmount() // the server restarts, the page reloads
  stubApi({ 'GET /imports/im1': { status: 404, body: { error: 'not found', detail: '' } } })
  render(<ImportView />)
  await waitFor(() => expect(sessionStorage.length).toBe(0))
  expect(screen.queryByRole('alert')).toBeNull()
  expect(screen.getByRole('button', { name: 'Weiter' })).toBeEnabled()
})

test('a stored import is fetched at once, not after the first interval', async () => {
  fakeTimers()
  sessionStorage.setItem('jobadvaisor.import', 'im1')
  stubApi({ 'GET /imports/im1': { body: withConflicts() } })
  render(<ImportView />)
  expect(await screen.findByRole('heading', { name: 'Status weicht ab' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Weiter' })).toBeEnabled()
})

test('three failed polls in a row stop polling and offer a retry', async () => {
  fakeTimers()
  sessionStorage.setItem('jobadvaisor.import', 'im1')
  let polls = 0
  stubApi({ 'GET /imports/im1': () => (++polls <= 3
    ? { status: 500, body: { error: 'boom', detail: '' } } : { body: state({ done: 9 }) }) })
  render(<ImportView />)
  await tick()
  await tick()
  await tick()
  expect(screen.getByRole('alert')).toHaveTextContent('Der Stand des Imports ist gerade nicht abrufbar')
  await act(async () => screen.getByRole('button', { name: 'Erneut versuchen' }).click())
  await tick()
  expect(screen.getByText('9 von 20 Einträgen')).toBeVisible()
})

test('the view has no accessibility violations while idle, running and finished', async () => {
  fakeTimers()
  stubApi({ ...WITH_PREVIEW, 'POST /imports': { status: 202, body: { import_id: 'im1' } },
            'GET /imports/im1': () => ({ body: state({ status: 'done', done: 20, counts: COUNTS }) }) })
  const { container } = render(<ImportView />)
  expect(await axe(container)).toHaveNoViolations()
  await upload()
  expect(await axe(container)).toHaveNoViolations()
  await tick()
  expect(await axe(container)).toHaveNoViolations()
})

test('"Weiter" sends the file to the preview, which lists tables and columns without a start yet', async () => {
  const calls = stubApi(WITH_PREVIEW)
  render(<ImportView />)
  const file = await toForm()
  expect(calls).toHaveLength(1)
  expect(calls[0]).toMatchObject({ method: 'POST', path: '/imports/preview' })
  expect((calls[0].body as { file: File }).file.name).toBe(file.name)
  const tables = screen.getByRole('list', { name: 'Tabellen in der Datei' })
  expect(within(tables).getAllByRole('listitem').map((item) => item.textContent))
    .toEqual(['Offen · 5 Einträge', 'Archiv · 1 Eintrag'])
  const status = screen.getByLabelText('Status-Spalte')
  expect(within(status).getAllByRole('option').map((option) => option.textContent))
    .toEqual(['keine', 'Titel', 'Firma', 'Link', 'Stand', 'Notiz', 'Grund']) // "stand" merges into "Stand"
  expect(status).toHaveValue('')
  expect(screen.getByLabelText('Spalte für deine Einschätzung (optional)')).toHaveValue('')
  expect(screen.queryByRole('group')).toBeNull()
})

test('a stored mapping prefills the columns and values without regard to case', async () => {
  stubApi({ 'POST /imports/preview': { body: { ...PREVIEW, mapping: {
    status_column: 'STAND', assessment_column: 'notiz',
    values: { ' beworben': 'applied', abgesagt: 'skip', OFFEN: 'done' } } } } })
  render(<ImportView />)
  await toForm()
  expect(screen.getByLabelText('Status-Spalte')).toHaveValue('Stand')
  expect(screen.getByLabelText('Spalte für deine Einschätzung (optional)')).toHaveValue('Notiz')
  const group = screen.getByRole('group', { name: /Werte/ })
  expect(within(group).getByLabelText('Beworben')).toHaveValue('applied')
  expect(within(group).getByLabelText('Abgesagt')).toHaveValue('skip')
  expect(within(group).getByLabelText('Offen')).toHaveValue('done')
})

test('values that differ only in case form one row, open by default', async () => {
  stubApi({ 'POST /imports/preview': { body: { ...PREVIEW, mapping: { status_column: 'Stand', assessment_column: null, values: {} } } } })
  render(<ImportView />)
  await toForm()
  const group = screen.getByRole('group', { name: /Werte/ })
  expect(within(group).getAllByRole('combobox')).toHaveLength(3) // Offen/offen, Beworben, Abgesagt
  expect(within(group).getByLabelText('Offen')).toHaveValue('open')
  expect(within(group).getByLabelText('Abgesagt')).toHaveValue('open')
  expect(within(within(group).getByLabelText('Abgesagt')).getAllByRole('option').map((option) => option.textContent))
    .toEqual(['offen', 'beworben', 'erledigt', 'überspringen'])
})

test('a stored column the file lacks falls back to "keine"', async () => {
  stubApi({ 'POST /imports/preview': { body: { ...PREVIEW, mapping: {
    status_column: 'Zustand', assessment_column: 'Urteil', values: { fertig: 'done' } } } } })
  render(<ImportView />)
  await toForm()
  expect(screen.getByLabelText('Status-Spalte')).toHaveValue('')
  expect(screen.getByLabelText('Spalte für deine Einschätzung (optional)')).toHaveValue('')
  expect(screen.queryByRole('group')).toBeNull()
})

test('another status column swaps the value rows', async () => {
  stubApi(WITH_PREVIEW)
  render(<ImportView />)
  await toForm()
  await userEvent.selectOptions(screen.getByLabelText('Status-Spalte'), 'Stand')
  expect(screen.getByRole('group', { name: /Werte/ })).toHaveTextContent('Beworben')
  expect(screen.getByText(/nur Tabellen.*Status-Spalte/)).toBeVisible()
  await userEvent.selectOptions(screen.getByLabelText('Status-Spalte'), 'Notiz')
  const group = screen.getByRole('group', { name: /Werte/ })
  expect(group).not.toHaveTextContent('Beworben')
  expect(within(group).getByLabelText('gut')).toHaveValue('open')
  expect(within(group).getByLabelText('mäßig')).toHaveValue('open')
})

test('a column with too many values says so and shows no value rows', async () => {
  stubApi(WITH_PREVIEW)
  render(<ImportView />)
  await toForm()
  await userEvent.selectOptions(screen.getByLabelText('Status-Spalte'), 'Titel')
  expect(screen.getByText(/mehr als 30 verschiedene Werte/)).toBeVisible()
  expect(screen.queryByRole('group')).toBeNull()
  expect(screen.getByRole('button', { name: 'Import starten' })).toBeDisabled()
  await userEvent.selectOptions(screen.getByLabelText('Status-Spalte'), '')
  expect(screen.getByRole('button', { name: 'Import starten' })).toBeEnabled()
})

test('"Import starten" sends the file and the chosen mapping as JSON', async () => {
  const calls = stubApi({ ...WITH_PREVIEW, 'POST /imports': { status: 202, body: { import_id: 'im1' } },
    'GET /imports/im1': { body: state({}) } })
  render(<ImportView />)
  const file = await toForm()
  await userEvent.selectOptions(screen.getByLabelText('Status-Spalte'), 'Stand')
  await userEvent.selectOptions(screen.getByLabelText('Spalte für deine Einschätzung (optional)'), 'Notiz')
  await userEvent.selectOptions(screen.getByLabelText('Abgesagt'), 'skip')
  await userEvent.selectOptions(screen.getByLabelText('Beworben'), 'applied')
  await userEvent.click(screen.getByRole('button', { name: 'Import starten' }))
  const body = calls.find((call) => call.path === '/imports')?.body as { file: File; mapping: string }
  expect(body.file.name).toBe(file.name)
  expect(JSON.parse(body.mapping)).toEqual({
    status_column: 'Stand', assessment_column: 'Notiz',
    values: { Offen: 'open', Beworben: 'applied', Abgesagt: 'skip' } })
  expect(await screen.findByText('0 von 20 Einträgen')).toBeVisible()
  expect(sessionStorage.getItem('jobadvaisor.import')).toBe('im1')
})

test('"Import starten" keeps remembered choices for values this file does not have', async () => {
  const calls = stubApi({ 'POST /imports/preview': { body: { ...PREVIEW, mapping: {
    status_column: 'Stand', assessment_column: null,
    values: { 'Stelle weg': 'skip', ' BEWORBEN': 'applied' } } } },
    'POST /imports': { status: 202, body: { import_id: 'im1' } }, 'GET /imports/im1': { body: state({}) } })
  render(<ImportView />)
  await toForm()
  await userEvent.selectOptions(screen.getByLabelText('Abgesagt'), 'done')
  await userEvent.click(screen.getByRole('button', { name: 'Import starten' }))
  const body = calls.find((call) => call.path === '/imports')?.body as { mapping: string }
  expect(JSON.parse(body.mapping).values).toEqual({
    'Stelle weg': 'skip', Offen: 'open', Beworben: 'applied', Abgesagt: 'done' })
})

test('without columns chosen the mapping names none', async () => {
  const calls = stubApi({ ...WITH_PREVIEW, 'POST /imports': { status: 202, body: { import_id: 'im1' } },
    'GET /imports/im1': { body: state({}) } })
  render(<ImportView />)
  await upload()
  const body = calls.find((call) => call.path === '/imports')?.body as { mapping: string }
  expect(JSON.parse(body.mapping)).toEqual({ status_column: null, assessment_column: null, values: {} })
})

test('"Andere Datei" returns to the upload', async () => {
  const calls = stubApi(WITH_PREVIEW)
  render(<ImportView />)
  await toForm()
  await userEvent.click(screen.getByRole('button', { name: 'Andere Datei' }))
  expect(screen.getByLabelText('Liste als Markdown-Datei')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Import starten' })).toBeNull()
  expect(calls).toHaveLength(1)
})

test('after "Andere Datei" the old file is forgotten', async () => {
  const calls = stubApi(WITH_PREVIEW)
  render(<ImportView />)
  await toForm()
  await userEvent.click(screen.getByRole('button', { name: 'Andere Datei' }))
  await userEvent.click(screen.getByRole('button', { name: 'Weiter' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Wähle zuerst eine Datei aus.')
  expect(calls).toHaveLength(1)
})

test('focus follows the steps: heading of the form, file input, progress', async () => {
  stubApi({ ...WITH_PREVIEW, 'POST /imports': { status: 202, body: { import_id: 'im1' } },
    'GET /imports/im1': { body: state({}) } })
  render(<ImportView />)
  await toForm()
  expect(screen.getByRole('heading', { name: 'Spalten zuordnen' })).toHaveFocus()
  await userEvent.click(screen.getByRole('button', { name: 'Andere Datei' }))
  expect(screen.getByLabelText('Liste als Markdown-Datei')).toHaveFocus()
  await toForm()
  await userEvent.click(screen.getByRole('button', { name: 'Import starten' }))
  const progress = (await screen.findByText('0 von 20 Einträgen')).closest('p')
  expect(progress).toHaveFocus()
})

test('"Weiter" shows that the file is being read and ignores a second press', async () => {
  const calls = stubApi({ 'POST /imports/preview': pending() })
  render(<ImportView />)
  await userEvent.upload(screen.getByLabelText('Liste als Markdown-Datei'), listFile())
  await userEvent.click(screen.getByRole('button', { name: 'Weiter' }))
  const button = screen.getByRole('button', { name: 'Wird gelesen…' })
  expect(button).toHaveAttribute('aria-disabled', 'true')
  expect(button).toHaveFocus() // not `disabled`: keyboard focus stays
  await userEvent.click(button)
  expect(calls).toHaveLength(1)
})

test('a list without tables says so and offers no start', async () => {
  stubApi({ 'POST /imports/preview': { body: { tables: [], values: {}, mapping: null } } })
  render(<ImportView />)
  await userEvent.upload(screen.getByLabelText('Liste als Markdown-Datei'), listFile())
  await userEvent.click(screen.getByRole('button', { name: 'Weiter' }))
  expect(await screen.findByText(/keine Tabelle mit Links/)).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Import starten' })).toBeNull()
  await userEvent.click(screen.getByRole('button', { name: 'Andere Datei' }))
  expect(screen.getByLabelText('Liste als Markdown-Datei')).toBeVisible()
})

test('a refused preview says the file is no text and stays on the upload', async () => {
  stubApi({ 'POST /imports/preview': { status: 422, body: { error: 'invalid upload', detail: 'x' } } })
  render(<ImportView />)
  await userEvent.upload(screen.getByLabelText('Liste als Markdown-Datei'), listFile())
  await userEvent.click(screen.getByRole('button', { name: 'Weiter' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('nicht als Text gelesen')
  expect(screen.getByRole('button', { name: 'Weiter' })).toBeEnabled()
})

test('a refused mapping keeps the form for another try', async () => {
  stubApi({ ...WITH_PREVIEW, 'POST /imports': { status: 422, body: { error: 'invalid mapping', detail: 'x' } } })
  render(<ImportView />)
  await upload()
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Import starten' })).toBeEnabled()
})

test('the mapping form has no accessibility violations', async () => {
  stubApi({ 'POST /imports/preview': { body: { ...PREVIEW, mapping: { status_column: 'Stand', assessment_column: 'Notiz', values: {} } } } })
  const { container } = render(<ImportView />)
  await toForm()
  expect(await axe(container)).toHaveNoViolations()
})

test('the report names every entry not imported with its link, outcome and reason', async () => {
  fakeTimers()
  sessionStorage.setItem('jobadvaisor.import', 'im1')
  stubApi({ 'GET /imports/im1': { body: state({ status: 'done', done: 20, counts: COUNTS, not_imported: NOT_IMPORTED }) } })
  render(<ImportView />)
  await tick()
  const section = screen.getByRole('region', { name: 'Nicht importiert' })
  const items = within(section).getAllByRole('listitem')
  expect(items).toHaveLength(4)
  expect(items[0]).toHaveTextContent('Backend Engineer · Harbor GmbH')
  expect(items[0]).toHaveTextContent('Fehlgeschlagen: browser failed: timeout')
  const link = within(items[0]).getByRole('link')
  expect(link).toHaveAttribute('href', 'https://harbor.example/jobs/1')
  expect(link).toHaveAttribute('target', '_blank')
  expect(link).toHaveAttribute('rel', 'noreferrer')
  expect(items[1]).toHaveTextContent('Übersprungen (Status): Stelle weg')
  expect(items[2]).toHaveTextContent('Link nicht mehr erreichbar: HTTP 410')
  expect(within(items[3]).queryByRole('link')).toBeNull() // http(s) only
  expect(items[3]).toHaveTextContent('Eintrag ohne sicheren Link')
})

test('an import that skipped nothing shows no "Nicht importiert" section', async () => {
  fakeTimers()
  sessionStorage.setItem('jobadvaisor.import', 'im1')
  stubApi({ 'GET /imports/im1': { body: state({ status: 'done', done: 20, counts: COUNTS }) } })
  render(<ImportView />)
  await tick()
  expect(screen.queryByRole('region', { name: 'Nicht importiert' })).toBeNull()
})

test('the report with both sections has no accessibility violations', async () => {
  fakeTimers()
  sessionStorage.setItem('jobadvaisor.import', 'im1')
  stubApi({ 'GET /imports/im1': { body: { ...withConflicts(), not_imported: NOT_IMPORTED } } })
  const { container } = render(<ImportView />)
  await tick()
  expect(screen.getByRole('region', { name: 'Nicht importiert' })).toBeVisible()
  expect(screen.getByRole('region', { name: 'Status weicht ab' })).toBeVisible()
  expect(await axe(container)).toHaveNoViolations()
})

const WITH_SOURCES: ImportPreview = {
  ...PREVIEW,
  tables: [...PREVIEW.tables, { name: 'Quellen', columns: ['Titel', 'Link'], entries: 2 }],
}
const STORED: ImportMapping = { status_column: 'Stand', assessment_column: null, values: { offen: 'open', BEWORBEN: 'applied' } }
const tableItems = () => within(screen.getByRole('list', { name: 'Tabellen in der Datei' })).getAllByRole('listitem')

test('each table says whether the chosen status column lets it be imported, live', async () => {
  stubApi({ 'POST /imports/preview': { body: WITH_SOURCES } })
  render(<ImportView />)
  await toForm()
  expect(tableItems().map((item) => item.textContent))
    .toEqual(['Offen · 5 Einträge', 'Archiv · 1 Eintrag', 'Quellen · 2 Einträge']) // no column: all are imported
  await userEvent.selectOptions(screen.getByLabelText('Status-Spalte'), 'Stand')
  expect(tableItems().map((item) => item.textContent)).toEqual([
    'Offen · 5 Einträge', 'Archiv · 1 Eintrag', // "stand" matches "Stand" without case
    'Quellen · 2 Einträge · wird nicht importiert (Spalte „Stand“ fehlt)'])
  await userEvent.selectOptions(screen.getByLabelText('Status-Spalte'), 'Notiz')
  expect(tableItems().map((item) => item.textContent)).toEqual([
    'Offen · 5 Einträge',
    'Archiv · 1 Eintrag · wird nicht importiert (Spalte „Notiz“ fehlt)',
    'Quellen · 2 Einträge · wird nicht importiert (Spalte „Notiz“ fehlt)'])
  await userEvent.selectOptions(screen.getByLabelText('Status-Spalte'), '')
  expect(screen.queryByText(/wird nicht importiert/)).toBeNull()
})

test('a status value the stored mapping does not name is marked "neu" and stays marked once chosen', async () => {
  stubApi({ 'POST /imports/preview': { body: { ...PREVIEW, mapping: STORED } } })
  render(<ImportView />)
  await toForm()
  const group = screen.getByRole('group', { name: /Werte/ })
  const row = (label: string) => within(within(group).getByLabelText(label).parentElement as HTMLElement)
  expect(within(group).getAllByText('neu')).toHaveLength(1)
  expect(row('Abgesagt').getByText('neu')).toBeVisible()
  const badge = row('Abgesagt').getByText('neu')
  expect(within(group).getByLabelText('Abgesagt')).toHaveAccessibleDescription('neu')
  expect(within(group).getByLabelText('Abgesagt')).toHaveAttribute('aria-describedby', badge.id)
  expect(within(group).getByLabelText('Beworben')).not.toHaveAttribute('aria-describedby')
  expect(row('Offen').queryByText('neu')).toBeNull() // known in another spelling of the case
  expect(row('Beworben').queryByText('neu')).toBeNull()
  expect(within(group).getByLabelText('Abgesagt')).toHaveValue('open')
  await userEvent.selectOptions(within(group).getByLabelText('Abgesagt'), 'done')
  expect(row('Abgesagt').getByText('neu')).toBeVisible()
})

test('without a stored mapping no value is marked "neu"', async () => {
  stubApi(WITH_PREVIEW)
  render(<ImportView />)
  await toForm()
  await userEvent.selectOptions(screen.getByLabelText('Status-Spalte'), 'Stand')
  expect(screen.getByRole('group', { name: /Werte/ })).toBeVisible()
  expect(screen.queryByText('neu')).toBeNull()
})

test('"keine" warns when the stored mapping names a status column, and still lets the import start', async () => {
  stubApi({ 'POST /imports/preview': { body: { ...PREVIEW, mapping: STORED } },
    'POST /imports': { status: 202, body: { import_id: 'im1' } }, 'GET /imports/im1': { body: state({}) } })
  render(<ImportView />)
  await toForm()
  expect(screen.queryByRole('alert')).toBeNull()
  await userEvent.selectOptions(screen.getByLabelText('Status-Spalte'), '')
  expect(screen.getByRole('alert')).toHaveTextContent('jede Tabelle mit Links importiert')
  expect(screen.getByRole('alert')).toHaveTextContent('jeder Eintrag wird „offen“')
  await userEvent.selectOptions(screen.getByLabelText('Status-Spalte'), 'Stand')
  expect(screen.queryByRole('alert')).toBeNull()
  await userEvent.selectOptions(screen.getByLabelText('Status-Spalte'), '')
  await userEvent.click(screen.getByRole('button', { name: 'Import starten' }))
  expect(await screen.findByText('0 von 20 Einträgen')).toBeVisible()
})

test('a renamed status column opens the form on "keine" with the warning, choosing the new name clears it', async () => {
  const renamed: ImportPreview = {
    tables: [{ name: 'Offen', columns: ['Titel', 'Link', 'Status'], entries: 5 }],
    values: { Status: ['offen', 'Beworben'] },
    mapping: STORED, // names "Stand", which this file no longer has
  }
  stubApi({ 'POST /imports/preview': { body: renamed } })
  render(<ImportView />)
  await toForm()
  expect(screen.getByLabelText('Status-Spalte')).toHaveValue('')
  expect(screen.getByRole('alert')).toHaveTextContent('jede Tabelle mit Links importiert')
  expect(screen.getByRole('alert')).toHaveTextContent('„Stand“')
  await userEvent.selectOptions(screen.getByLabelText('Status-Spalte'), 'Status')
  expect(screen.queryByRole('alert')).toBeNull()
})

test('"keine" does not warn without a stored status column', async () => {
  stubApi({ 'POST /imports/preview': { body: { ...PREVIEW, mapping: { ...STORED, status_column: null } } } })
  const first = render(<ImportView />)
  await toForm()
  expect(screen.queryByRole('alert')).toBeNull()
  first.unmount()
  stubApi(WITH_PREVIEW)
  render(<ImportView />)
  await toForm()
  await userEvent.selectOptions(screen.getByLabelText('Status-Spalte'), 'Stand')
  await userEvent.selectOptions(screen.getByLabelText('Status-Spalte'), '')
  expect(screen.queryByRole('alert')).toBeNull()
})

test('the mapping form with the marker and the warning has no accessibility violations', async () => {
  stubApi({ 'POST /imports/preview': { body: { ...WITH_SOURCES, mapping: STORED } } })
  const { container } = render(<ImportView />)
  await toForm()
  expect(screen.getByText('neu')).toBeVisible()
  expect(screen.getByText(/wird nicht importiert/)).toBeVisible()
  await userEvent.selectOptions(screen.getByLabelText('Status-Spalte'), '')
  expect(screen.getByRole('alert')).toBeVisible()
  expect(await axe(container)).toHaveNoViolations()
})

test('the report names each table left out for lacking the status column with its entries', async () => {
  fakeTimers()
  sessionStorage.setItem('jobadvaisor.import', 'im1')
  const left = [{ name: 'Archiv', entries: 6 }, { name: 'Quellen', entries: 1 }]
  stubApi({ 'GET /imports/im1': { body: state({ status: 'done', done: 20, counts: COUNTS, tables_left_out: left }) } })
  const { container } = render(<ImportView />)
  await tick()
  const section = screen.getByRole('region', { name: 'Nicht importierte Tabellen' })
  expect(within(section).getAllByRole('listitem').map((item) => item.textContent))
    .toEqual(['Archiv · 6 Einträge · Status-Spalte fehlt', 'Quellen · 1 Eintrag · Status-Spalte fehlt'])
  expect(await axe(container)).toHaveNoViolations()
})

test('a report without tables left out has no "Nicht importierte Tabellen" section', async () => {
  fakeTimers()
  sessionStorage.setItem('jobadvaisor.import', 'im1')
  stubApi({ 'GET /imports/im1': { body: state({ status: 'done', done: 20, counts: COUNTS }) } })
  render(<ImportView />)
  await tick()
  expect(screen.getByText('Importiert')).toBeVisible()
  expect(screen.queryByRole('region', { name: 'Nicht importierte Tabellen' })).toBeNull()
})
