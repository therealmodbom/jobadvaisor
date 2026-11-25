import { act, cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { MailboxAccount } from '@/api'
import { axe } from '@/test-axe'
import { type Call, stubApi } from '@/test-api'
import { mailCheck, mailEntries, mailItem, MAILBOX, NO_MAILBOX } from '@/test-fixtures'
import { MailboxView } from './MailboxView'
import { POLL_MS } from './PoolView'

const CHECK_KEY = 'jobadvaisor.mailbox-check'
const noop = () => {}
const RUNNING = mailCheck({ total: 12, read: 5 })
/** A mailbox that was checked before: the start date and the last check are set. */
const CHECKED: MailboxAccount = { ...MAILBOX, since: '2026-10-24', last_check_at: '2026-11-22T17:04:00Z' }

const view = (props: Partial<Parameters<typeof MailboxView>[0]> = {}) =>
  render(<MailboxView active onText={noop} onPdf={noop} {...props} />)
const checkButton = () => screen.getByRole('button', { name: 'Postfach prüfen' })
const tick = (times = 1) => act(() => vi.advanceTimersByTimeAsync(POLL_MS * times))

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
  vi.setSystemTime(new Date(2026, 10, 24, 12))
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

test('nothing is requested while the source is not shown', () => {
  const calls = stubApi({ 'GET /mailbox': { body: MAILBOX } })
  view({ active: false })
  expect(calls).toHaveLength(0)
})

test('the account is read once the source is shown for the first time and kept after', async () => {
  const calls = stubApi({ 'GET /mailbox': { body: CHECKED } })
  const { rerender } = view({ active: false })
  rerender(<MailboxView active onText={noop} onPdf={noop} />)
  await screen.findByRole('button', { name: 'Postfach prüfen' })
  rerender(<MailboxView active={false} onText={noop} onPdf={noop} />)
  rerender(<MailboxView active onText={noop} onPdf={noop} />)
  expect(calls.filter((call) => call.path === '/mailbox')).toHaveLength(1)
})

test('a failed read of the account offers a retry', async () => {
  let failing = true
  stubApi({ 'GET /mailbox': () => (failing ? { status: 500 } : { body: CHECKED }) })
  view()
  failing = false
  await userEvent.click(await screen.findByRole('button', { name: 'Erneut versuchen' }))
  expect(await screen.findByRole('button', { name: 'Postfach prüfen' })).toBeVisible()
})

test('without a mailbox the view says so and links to the section of the settings', async () => {
  stubApi({ 'GET /mailbox': { body: NO_MAILBOX } })
  view()
  expect(await screen.findByText(/Noch kein Postfach eingerichtet/)).toBeVisible()
  expect(screen.getByRole('link', { name: 'Postfach einrichten' })).toHaveAttribute('href', '#/einstellungen/postfach')
  expect(screen.queryByRole('button', { name: 'Postfach prüfen' })).toBeNull()
})

test('a mailbox never checked shows the account, "Mails ab" 30 days back with the cost hint, and the check button', async () => {
  stubApi({ 'GET /mailbox': { body: MAILBOX } })
  view()
  await screen.findByRole('button', { name: 'Postfach prüfen' })
  expect(screen.getByText(/name@example\.org/)).toHaveTextContent('imap.example.org')
  expect(screen.getByText(/Alle Ordner/)).toBeVisible()
  expect(screen.getByText(/Noch nie geprüft/)).toBeVisible()
  expect(screen.getByLabelText('Mails ab')).toHaveValue('2026-10-25')
  expect(screen.getByText(/Ältere Mails werden nie gelesen/)).toHaveTextContent(/Modellaufruf/)
  expect(screen.getByRole('link', { name: 'Einstellungen' })).toHaveAttribute('href', '#/einstellungen/postfach')
})

test('a checked mailbox shows the folders, the time of the last check and no "Mails ab"', async () => {
  stubApi({ 'GET /mailbox': { body: { ...CHECKED, folders: { names: ['Jobs', 'Posteingang'] } } } })
  view()
  await screen.findByRole('button', { name: 'Postfach prüfen' })
  expect(screen.queryByLabelText('Mails ab')).toBeNull()
  expect(screen.getByText(/Jobs, Posteingang/)).toBeVisible()
  expect(screen.getByText(/Letzte Prüfung/)).toHaveTextContent('22.11.2026, 18:04')
})

test('the first check sends the start date, a later one sends nothing', async () => {
  const calls = stubApi({ 'GET /mailbox': { body: MAILBOX }, 'POST /mailbox/checks': { status: 202, body: { check_id: 'c1' } },
                          'GET /mailbox/checks/c1': { body: RUNNING } })
  view()
  await screen.findByRole('button', { name: 'Postfach prüfen' })
  await userEvent.clear(screen.getByLabelText('Mails ab'))
  await userEvent.type(screen.getByLabelText('Mails ab'), '2026-11-01')
  await userEvent.click(checkButton())
  await screen.findByRole('status')
  expect(calls.find((call) => call.method === 'POST')!.body).toEqual({ since: '2026-11-01' })
  expect(localStorage.getItem(CHECK_KEY)).toBe('c1')
})

test('a later check sends no body', async () => {
  const calls = stubApi({ 'GET /mailbox': { body: CHECKED }, 'POST /mailbox/checks': { status: 202, body: { check_id: 'c1' } },
                          'GET /mailbox/checks/c1': { body: RUNNING } })
  view()
  await userEvent.click(await screen.findByRole('button', { name: 'Postfach prüfen' }))
  await screen.findByRole('status')
  expect(calls.find((call) => call.method === 'POST')!.body).toBeUndefined()
})

test('without a start date the check is not started', async () => {
  const calls = stubApi({ 'GET /mailbox': { body: MAILBOX } })
  view()
  await screen.findByRole('button', { name: 'Postfach prüfen' })
  await userEvent.clear(screen.getByLabelText('Mails ab'))
  await userEvent.click(checkButton())
  expect(await screen.findByRole('alert')).toHaveTextContent('Startdatum')
  expect(calls.some((call) => call.method === 'POST')).toBe(false)
})

test('while a check runs it shows how many mails it found and read, the check button waits and cancel is offered', async () => {
  stubApi({ 'GET /mailbox': { body: { ...CHECKED, check_id: 'c1' } }, 'GET /mailbox/checks/c1': { body: RUNNING } })
  view()
  await screen.findByText('12 neue Mails gefunden, 5 gelesen')
  const progress = screen.getByRole('region', { name: 'Stand der Prüfung' })
  expect(within(progress).getByRole('progressbar', { name: /5 von 12/ })).toBeVisible()
  expect(checkButton()).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Warum ist Prüfen nicht möglich?' })).toBeVisible()
  const cancel = screen.getByRole('button', { name: 'Prüfen abbrechen' })
  expect(cancel).toHaveAccessibleDescription(/nach der aktuellen Mail/)
  expect(cancel).toHaveAccessibleDescription(/bleiben in der Auswahlliste/)
})

test('a check that has not found its mails yet says it searches the mailbox', async () => {
  stubApi({ 'GET /mailbox': { body: { ...CHECKED, check_id: 'c1' } }, 'GET /mailbox/checks/c1': { body: mailCheck() } })
  view()
  expect(await screen.findByRole('region', { name: 'Stand der Prüfung' })).toHaveTextContent('Postfach wird durchsucht')
})

test('the progress follows the polls', async () => {
  let reads = 0
  stubApi({ 'GET /mailbox': { body: { ...CHECKED, check_id: 'c1' } },
            'GET /mailbox/checks/c1': () => ({ body: ++reads < 2 ? RUNNING : mailCheck({ total: 12, read: 9 }) }) })
  view()
  await screen.findByText(/12 neue Mails gefunden, 5 gelesen/)
  await tick()
  expect(await screen.findByText(/12 neue Mails gefunden, 9 gelesen/)).toBeVisible()
})

test('"Prüfen abbrechen" cancels at once without a confirm step, then says the check stops after the current mail', async () => {
  let cancelled = false
  const calls = stubApi({
    'GET /mailbox': { body: { ...CHECKED, check_id: 'c1' } },
    'GET /mailbox/checks/c1': () => ({ body: { ...RUNNING, cancel_requested: cancelled } }),
    'POST /mailbox/checks/c1/cancel': () => { cancelled = true; return { status: 202, body: { check_id: 'c1' } } },
  })
  view()
  await userEvent.click(await screen.findByRole('button', { name: 'Prüfen abbrechen' }))
  expect(calls.filter((call) => call.path.endsWith('/cancel'))).toHaveLength(1)
  const stopping = await screen.findByRole('button', { name: 'Wird beendet…' })
  expect(stopping).toHaveAttribute('aria-disabled', 'true')
  expect(screen.getByText(/Wird nach der aktuellen Mail beendet/)).toHaveTextContent(/bleiben in der Auswahlliste/)
  await userEvent.click(stopping)
  expect(calls.filter((call) => call.path.endsWith('/cancel'))).toHaveLength(1)
})

test('a cancel that is refused because the check ended is left to the next poll', async () => {
  let reads = 0
  stubApi({
    'GET /mailbox': { body: { ...CHECKED, check_id: 'c1' } },
    'GET /mailbox/checks/c1': () => ({ body: ++reads < 2 ? RUNNING : mailCheck({ status: 'done', total: 12, read: 12 }) }),
    'POST /mailbox/checks/c1/cancel': { status: 409, body: { error: 'check not running', detail: 'x' } },
  })
  view()
  await userEvent.click(await screen.findByRole('button', { name: 'Prüfen abbrechen' }))
  expect(screen.queryByRole('alert')).toBeNull()
  await tick()
  await vi.waitFor(() => expect(screen.queryByRole('button', { name: 'Prüfen abbrechen' })).toBeNull())
})

test('a cancelled check without mails says after how many mails it stopped', async () => {
  stubApi({ 'GET /mailbox': { body: { ...CHECKED, check_id: 'c1' } },
            'GET /mailbox/checks/c1': { body: mailCheck({ status: 'done', cancelled: true, total: 200, read: 37 }) } })
  view()
  expect(await screen.findByRole('note')).toHaveTextContent('Die Prüfung wurde nach 37 von 200 Mails abgebrochen.')
})

test('a check without new mails says so with the start date and can be dismissed', async () => {
  stubApi({ 'GET /mailbox': { body: CHECKED }, 'POST /mailbox/checks': { status: 202, body: { check_id: 'c1' } },
            'GET /mailbox/checks/c1': { body: mailCheck({ status: 'done' }) } })
  view()
  await userEvent.click(await screen.findByRole('button', { name: 'Postfach prüfen' }))
  expect(await screen.findByText('Keine neuen Mails seit dem 24.10.2026.')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Bericht ausblenden' }))
  expect(screen.queryByText(/Keine neuen Mails/)).toBeNull()
  expect(localStorage.getItem(CHECK_KEY)).toBeNull()
})

test('the account is read again when a check ends, so the start date and the last check show', async () => {
  let ended = false
  stubApi({ 'GET /mailbox': () => ({ body: ended ? CHECKED : MAILBOX }), 'POST /mailbox/checks': { status: 202, body: { check_id: 'c1' } },
            'GET /mailbox/checks/c1': () => ({ body: mailCheck({ status: 'done' }) }) })
  view()
  await screen.findByLabelText('Mails ab')
  ended = true
  await userEvent.click(checkButton())
  await screen.findByText(/Keine neuen Mails/)
  await vi.waitFor(() => expect(screen.queryByLabelText('Mails ab')).toBeNull())
  expect(screen.getByText(/Letzte Prüfung/)).toHaveTextContent('22.11.2026')
})

test.each([
  ['unreachable', /Der Server ist nicht erreichbar/],
  ['certificate', /Zertifikat/],
  ['login', /Anmeldung abgelehnt/],
  ['protocol', /IMAP-Server/],
  ['folder', /Ordner ließ sich nicht öffnen/],
  ['no key', /kein Schlüssel/],
  ['no password', /kein Passwort gespeichert/],
])('a check that failed with "%s" names the reason, offers a retry and the settings', async (reason, text) => {
  stubApi({ 'GET /mailbox': { body: { ...MAILBOX, check_id: 'c1' } },
            'GET /mailbox/checks/c1': { body: mailCheck({ status: 'failed', reason }) } })
  view()
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent(text)
  expect(within(alert).getByRole('button', { name: 'Erneut versuchen' })).toBeVisible()
  expect(within(alert).getByRole('link', { name: 'Einstellungen öffnen' })).toHaveAttribute('href', '#/einstellungen/postfach')
})

test('"Erneut versuchen" starts a new check and sends the start date again while none is stored', async () => {
  const calls = stubApi({ 'GET /mailbox': { body: { ...MAILBOX, check_id: 'c1' } },
                          'GET /mailbox/checks/c1': { body: mailCheck({ status: 'failed', reason: 'unreachable' }) },
                          'POST /mailbox/checks': { status: 202, body: { check_id: 'c2' } },
                          'GET /mailbox/checks/c2': { body: mailCheck({ check_id: 'c2' }) } })
  view()
  await userEvent.click(await screen.findByRole('button', { name: 'Erneut versuchen' }))
  await screen.findByRole('region', { name: 'Stand der Prüfung' })
  expect(calls.find((call) => call.method === 'POST')!.body).toEqual({ since: '2026-10-25' })
  expect(localStorage.getItem(CHECK_KEY)).toBe('c2')
})

test('a stored password the key cannot open is named, with a link to enter it again', async () => {
  stubApi({ 'GET /mailbox': { body: { ...MAILBOX, check_id: 'c1' } },
            'GET /mailbox/checks/c1': { body: mailCheck({ status: 'failed', reason: 'password unreadable' }) } })
  view()
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('lässt sich nicht lesen')
  expect(within(alert).getByRole('link', { name: 'Passwort neu eingeben' })).toHaveAttribute('href', '#/einstellungen/postfach')
})

test('a crashed worker says so without a reason code', async () => {
  stubApi({ 'GET /mailbox': { body: { ...MAILBOX, check_id: 'c1' } },
            'GET /mailbox/checks/c1': { body: mailCheck({ status: 'failed', error: 'KeyError' }) } })
  view()
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('Fehler in der App')
  expect(alert).not.toHaveTextContent('KeyError')
})

test('a check that runs elsewhere is followed after a reload', async () => {
  const calls = stubApi({ 'GET /mailbox': { body: { ...CHECKED, check_id: 'c9' } }, 'GET /mailbox/checks/c9': { body: mailCheck({ check_id: 'c9', total: 4, read: 1 }) } })
  view()
  expect(await screen.findByText(/4 neue Mails gefunden, 1 gelesen/)).toBeVisible()
  expect(calls.some((call) => call.method === 'POST')).toBe(false)
  expect(localStorage.getItem(CHECK_KEY)).toBe('c9')
})

test('a second tab that starts a check follows the running one', async () => {
  stubApi({ 'GET /mailbox': { body: CHECKED },
            'POST /mailbox/checks': { status: 409, body: { error: 'check in progress', detail: 'x', check_id: 'c5' } },
            'GET /mailbox/checks/c5': { body: mailCheck({ check_id: 'c5', total: 3, read: 2 }) } })
  view()
  await userEvent.click(await screen.findByRole('button', { name: 'Postfach prüfen' }))
  expect(await screen.findByText(/3 neue Mails gefunden, 2 gelesen/)).toBeVisible()
  expect(screen.queryByRole('alert')).toBeNull()
})

test('a refused start says so and keeps the button usable', async () => {
  stubApi({ 'GET /mailbox': { body: CHECKED }, 'POST /mailbox/checks': { status: 500 } })
  view()
  await userEvent.click(await screen.findByRole('button', { name: 'Postfach prüfen' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('konnte nicht gestartet werden')
  expect(checkButton()).toBeEnabled()
})

test('a check that ended is shown again after a reload until it is dismissed', async () => {
  localStorage.setItem(CHECK_KEY, 'c1')
  stubApi({ 'GET /mailbox': { body: CHECKED }, 'GET /mailbox/checks/c1': { body: mailCheck({ status: 'done' }) } })
  view()
  expect(await screen.findByText('Keine neuen Mails seit dem 24.10.2026.')).toBeVisible()
})

test('a stored check that reads finished gives way to the one the mailbox names', async () => {
  localStorage.setItem(CHECK_KEY, 'old')
  let named: string | null = null
  stubApi({ 'GET /mailbox': () => ({ body: { ...CHECKED, check_id: named } }),
            'GET /mailbox/checks/old': () => { named = 'c2'; return { body: mailCheck({ check_id: 'old', status: 'finished' }) } },
            'GET /mailbox/checks/c2': { body: mailCheck({ check_id: 'c2', total: 2, read: 0 }) } })
  view()
  expect(await screen.findByText(/2 neue Mails gefunden, 0 gelesen/)).toBeVisible()
  expect(localStorage.getItem(CHECK_KEY)).toBe('c2')
})

test('a running check the server forgot says so and offers a new one', async () => {
  let known = true
  stubApi({ 'GET /mailbox': () => ({ body: { ...CHECKED, check_id: known ? 'c1' : null } }),
            'GET /mailbox/checks/c1': () => (known ? { body: RUNNING } : { status: 404, body: { error: 'not found', detail: 'x' } }) })
  view()
  await screen.findByText(/12 neue Mails gefunden/)
  known = false
  await tick()
  expect(await screen.findByText(/dem Server nicht mehr bekannt/)).toBeVisible()
  expect(localStorage.getItem(CHECK_KEY)).toBeNull()
  expect(checkButton()).toBeEnabled()
})

test('a stored check the server does not know is dropped without a notice', async () => {
  localStorage.setItem(CHECK_KEY, 'gone')
  stubApi({ 'GET /mailbox': { body: CHECKED }, 'GET /mailbox/checks/gone': { status: 404, body: { error: 'not found', detail: 'x' } } })
  view()
  await screen.findByRole('button', { name: 'Postfach prüfen' })
  await vi.waitFor(() => expect(localStorage.getItem(CHECK_KEY)).toBeNull())
  expect(screen.queryByText(/nicht mehr bekannt/)).toBeNull()
})

test('failed polls offer a retry while the check may still run', async () => {
  let failing = false
  stubApi({ 'GET /mailbox': { body: { ...CHECKED, check_id: 'c1' } }, 'GET /mailbox/checks/c1': () => (failing ? { status: 500 } : { body: RUNNING }) })
  view()
  await screen.findByText(/12 neue Mails gefunden/)
  failing = true
  await tick(3)
  expect(await screen.findByText(/Der Stand der Prüfung ist gerade nicht abrufbar/)).toBeVisible()
  failing = false
  await userEvent.click(screen.getByRole('button', { name: 'Erneut versuchen' }))
  expect(await screen.findByText(/12 neue Mails gefunden/)).toBeVisible()
})

test('the source has no accessibility violations while a check runs and after a failure', async () => {
  stubApi({ 'GET /mailbox': { body: { ...MAILBOX, check_id: 'c1' } }, 'GET /mailbox/checks/c1': { body: RUNNING } })
  const { container } = view()
  await screen.findByText(/12 neue Mails gefunden/)
  expect(await axe(container, { rules: { region: { enabled: false } } })).toHaveNoViolations()
})

// ---- 9.3: report notes and the pick list ----

const RUN_KEY = 'jobadvaisor.mailbox-run'
const dup = { posting_id: 'p-9', title: 'Stelle 6' }

/** Three mails with seven entries, the first of the third already stored. */
const THREE = () => mailCheck({
  status: 'done', total: 3, read: 3,
  mails: [mailItem('m1', 3), mailItem('m2', 2, {}, 4), mailItem('m3', 2, {}, 6)].map((mail, i) => i < 2 ? mail
    : { ...mail, preview: { ...mail.preview!, entries: [{ ...mail.preview!.entries[0], duplicate: dup }, mail.preview!.entries[1]] } }),
})

/** Open the pick list of `state` through the check `GET /mailbox` names. */
async function openPicks(state = THREE(), routes: Parameters<typeof stubApi>[0] = {}) {
  const calls = stubApi({ 'GET /mailbox': { body: { ...CHECKED, check_id: 'c1' } }, 'GET /mailbox/checks/c1': { body: state }, ...routes })
  view()
  await screen.findByRole('list', { name: 'Mails der Prüfung' })
  return calls
}

const mailItemOf = (subject: string) => screen.getByRole('listitem', { name: `Mail „${subject}“` })
const headBox = (subject: string) => screen.getByRole('checkbox', { name: `Alle Anzeigen der Mail „${subject}“` })
/** The checkbox of an unread oversized mail: ticking it reads the mail. */
const unreadBox = (subject: string) => screen.getByRole('checkbox', { name: `Mail „${subject}“ lesen` })
const addButton = (n: number) => screen.getByRole('button', { name: `${n === 1 ? '1 Anzeige' : `${n} Anzeigen`} hinzufügen` })
const finishes = (calls: Call[]) => calls.filter((call) => call.path.endsWith('/finish'))

test('the entries of all mails are grouped by mail, the new ones selected', async () => {
  await openPicks()
  const heads = screen.getAllByRole('listitem', { name: /^Mail „/ })
  expect(heads).toHaveLength(3)
  expect(within(mailItemOf('Neue Stellen m1')).getAllByRole('checkbox')).toHaveLength(4)
  expect(within(mailItemOf('Neue Stellen m3')).getByRole('checkbox', { name: 'Stelle 6' })).toBeDisabled()
  expect(within(mailItemOf('Neue Stellen m3')).getByText('Schon gespeichert')).toBeVisible()
  expect(addButton(6)).toBeEnabled()
  expect(within(mailItemOf('Neue Stellen m1')).getByText('3 von 3 ausgewählt')).toBeVisible()
  expect(within(mailItemOf('Neue Stellen m3')).getByText('1 von 1 ausgewählt')).toBeVisible()
})

test('an entry another mail of the list offers names that mail, cannot be picked and is not counted', async () => {
  const first = mailItem('m1', 3)
  const second = mailItem('m2', 2, {}, 4)
  const copy = { ...first.preview!.entries[0], offered_in: { key: 'm1', sender: 'LinkedIn Job Alerts <jobalerts@linkedin.com>', subject: 'Neue Stellen m1' } }
  await openPicks(mailCheck({ status: 'done', total: 2, read: 2,
    mails: [first, { ...second, preview: { ...second.preview!, entries: [copy, ...second.preview!.entries] } }] }))
  const head = mailItemOf('Neue Stellen m2')
  const box = within(head).getByRole('checkbox', { name: 'Stelle 1' })
  expect(box).toBeDisabled()
  expect(box).not.toBeChecked()
  expect(box).toHaveAccessibleDescription('Auch in der Mail von LinkedIn Job Alerts <jobalerts@linkedin.com>, „Neue Stellen m1“. Dort auswählbar.')
  expect(within(head).getByText('2 von 2 ausgewählt')).toBeVisible()
  expect(addButton(5)).toBeEnabled()
})

test('"Postfach prüfen" stays offered beside a pick list, and a new check replaces the list', async () => {
  let started = false
  const calls = await openPicks(THREE(), {
    'POST /mailbox/checks': () => { started = true; return { status: 202, body: { check_id: 'c2' } } },
    'GET /mailbox/checks/c2': { body: mailCheck({ check_id: 'c2', status: 'running', total: 4, read: 1 }) },
    'GET /mailbox': () => ({ body: { ...CHECKED, check_id: started ? 'c2' : 'c1' } }),
  })
  await userEvent.click(screen.getByRole('button', { name: 'Postfach prüfen' }))
  expect(calls.some((call) => call.method === 'POST' && call.path === '/mailbox/checks')).toBe(true)
  await vi.waitFor(() => expect(screen.queryByRole('list', { name: 'Mails der Prüfung' })).toBeNull())
  expect(screen.getByRole('button', { name: 'Postfach prüfen' })).toBeDisabled()
})

test('a mail head shows the sender and, below it, subject, date and folder', async () => {
  await openPicks()
  const head = mailItemOf('Neue Stellen m1')
  expect(within(head).getByText('LinkedIn Job Alerts <jobalerts@linkedin.com>')).toBeVisible()
  const meta = within(head).getByText('Neue Stellen m1').parentElement!
  expect(meta).toHaveTextContent('22.11.2026, 08:15')
  expect(meta).toHaveTextContent('Posteingang')
  expect(meta.className).toMatch(/max-sm:flex-col/)
})

test('pressing the add button adds the selected entries as one run, shown like a pasted mail\'s run, and forgets the check', async () => {
  const runRows = [{ url: mailEntry(1).url, title: 'Stelle 1', state: 'waiting' }]
  const calls = await openPicks(THREE(), {
    'POST /mailbox/checks/c1/finish': { status: 202, body: { run_id: 'r1' } },
    'GET /alert-mails/runs/r1': { body: { run_id: 'r1', status: 'running', error: null, total: 1, done: 0, entries: runRows } },
  })
  await userEvent.click(addButton(6))
  const [finish] = finishes(calls)
  expect((finish.body as { entries: { url: string; title: string; force: boolean }[] }).entries).toHaveLength(6)
  expect((finish.body as { entries: unknown[] }).entries[0]).toEqual({ url: mailEntry(1).url, title: 'Stelle 1', force: false })
  expect(await screen.findByRole('list', { name: 'Stand je Anzeige' })).toBeVisible()
  expect(sessionStorage.getItem(RUN_KEY)).toBe('r1')
  expect(localStorage.getItem(CHECK_KEY)).toBeNull()
  expect(screen.queryByRole('list', { name: 'Mails der Prüfung' })).toBeNull()
})

test('a finished run leads back to the mailbox', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /mailbox': { body: CHECKED },
            'GET /alert-mails/runs/r1': { body: { run_id: 'r1', status: 'done', error: null, total: 1, done: 1,
              entries: [{ url: mailEntry(1).url, title: 'Stelle 1', state: 'stored', posting_id: 'p-1' }] } } })
  view()
  await userEvent.click(await screen.findByRole('button', { name: 'Zurück zum Postfach' }))
  expect(await screen.findByRole('button', { name: 'Postfach prüfen' })).toBeVisible()
  expect(sessionStorage.getItem(RUN_KEY)).toBeNull()
  expect(screen.queryByRole('button', { name: 'Andere Mail einfügen' })).toBeNull()
})

const mailEntry = (n: number) => mailEntries(1, n)[0]

test('"Nichts hinzufügen" adds nothing, says the mails count as handled and returns to the mailbox', async () => {
  const calls = await openPicks(THREE(), { 'POST /mailbox/checks/c1/finish': { status: 202, body: { run_id: null } } })
  expect(screen.getByText(/Eine Mail gilt danach als gelesen, wenn ihre hinzugefügten Anzeigen gespeichert sind; eine Mail, aus der du nichts hinzufügst, sofort\. Eine Mail mit einer Anzeige, die nicht gelesen werden konnte, bietet die nächste Prüfung wieder an\./)).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Nichts hinzufügen' }))
  expect(finishes(calls)[0].body).toEqual({ entries: [] })
  expect(await screen.findByText(/Nichts hinzugefügt/)).toHaveTextContent(/nicht noch einmal angeboten/)
  expect(screen.queryByRole('list', { name: 'Mails der Prüfung' })).toBeNull()
  expect(await screen.findByRole('button', { name: 'Postfach prüfen' })).toBeVisible()
  expect(localStorage.getItem(CHECK_KEY)).toBeNull()
})

test('a refused finish, because another alert run computes, shows that run and keeps the pick list for later', async () => {
  let runStatus = 'running'
  const calls = await openPicks(THREE(), {
    'POST /mailbox/checks/c1/finish': () => (runStatus === 'running'
      ? { status: 409, body: { error: 'alert run in progress', detail: 'x', run_id: 'r7' } }
      : { status: 202, body: { run_id: 'r8' } }),
    'GET /alert-mails/runs/r7': () => ({ body: { run_id: 'r7', status: runStatus, error: null, total: 4, done: runStatus === 'running' ? 1 : 4, entries: [] } }),
    'GET /alert-mails/runs/r8': { body: { run_id: 'r8', status: 'running', error: null, total: 1, done: 0, entries: [] } },
  })
  await userEvent.click(addButton(6))
  const busy = await screen.findByRole('region', { name: 'Ein anderer Lauf rechnet' })
  expect(busy).toHaveTextContent('1 von 4 erledigt')
  expect(screen.getByRole('list', { name: 'Mails der Prüfung' })).toBeVisible()
  expect(addButton(6)).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Warum ist Hinzufügen nicht möglich?' })).toBeVisible()
  expect(localStorage.getItem(CHECK_KEY)).toBe('c1')
  runStatus = 'done'
  await tick()
  await vi.waitFor(() => expect(screen.queryByRole('region', { name: 'Ein anderer Lauf rechnet' })).toBeNull())
  expect(addButton(6)).toBeEnabled()
  await userEvent.click(addButton(6))
  expect(finishes(calls)).toHaveLength(2)
  expect(await screen.findByRole('heading', { name: /erledigt/ })).toBeVisible()
})

test('a mailbox run with failed entries says that the next check offers their mails again', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /mailbox': { body: CHECKED },
            'GET /alert-mails/runs/r1': { body: { run_id: 'r1', status: 'done', error: null, cancel_requested: false, total: 4, done: 4,
              entries: [{ url: mailEntry(1).url, title: 'Stelle 1', state: 'stored', posting_id: 'p-1' },
                        ...[2, 3, 4].map((n) => ({ url: mailEntry(n).url, title: `Stelle ${n}`, state: 'failed' }))] } } })
  view()
  expect(await screen.findByText(/1 hinzugefügt, 3 nicht gelesen/)).toBeVisible()
  expect(screen.getByText('Die nächste Prüfung bietet die Mails dieser Anzeigen wieder an.')).toBeVisible()
})

test('a mailbox run whose entries all ended well does not say it', async () => {
  sessionStorage.setItem(RUN_KEY, 'r1')
  stubApi({ 'GET /mailbox': { body: CHECKED },
            'GET /alert-mails/runs/r1': { body: { run_id: 'r1', status: 'done', error: null, cancel_requested: false, total: 1, done: 1,
              entries: [{ url: mailEntry(1).url, title: 'Stelle 1', state: 'stored', posting_id: 'p-1' }] } } })
  view()
  await screen.findByRole('list', { name: 'Stand je Anzeige' })
  expect(screen.queryByText(/Die nächste Prüfung/)).toBeNull()
})

test('a check refused because an alert run computes shows that run and lets the check start again once it ended', async () => {
  let runStatus = 'running'
  const calls = stubApi({
    'GET /mailbox': { body: CHECKED },
    'POST /mailbox/checks': () => (runStatus === 'running'
      ? { status: 409, body: { error: 'alert run in progress', detail: 'x', run_id: 'r7' } }
      : { status: 202, body: { check_id: 'c2' } }),
    'GET /alert-mails/runs/r7': () => ({ body: { run_id: 'r7', status: runStatus, error: null, cancel_requested: false, total: 4,
                                                 done: runStatus === 'running' ? 1 : 4, entries: [] } }),
    'GET /mailbox/checks/c2': { body: mailCheck({ check_id: 'c2', total: 3, read: 1 }) },
  })
  view()
  await userEvent.click(await screen.findByRole('button', { name: 'Postfach prüfen' }))
  const busy = await screen.findByRole('region', { name: 'Ein anderer Lauf rechnet' })
  expect(busy).toHaveTextContent('1 von 4 erledigt')
  expect(busy).toHaveTextContent('Ein anderer Lauf rechnet noch: 1 von 4 erledigt. Die Prüfung kann starten, sobald er fertig ist.')
  expect(screen.queryByRole('alert')).toBeNull()
  expect(localStorage.getItem(CHECK_KEY)).toBeNull()
  runStatus = 'done'
  await tick()
  await vi.waitFor(() => expect(screen.queryByRole('region', { name: 'Ein anderer Lauf rechnet' })).toBeNull())
  expect(checkButton()).toBeEnabled()
  await userEvent.click(checkButton())
  expect(await screen.findByText(/3 neue Mails gefunden, 1 gelesen/)).toBeVisible()
  expect(calls.filter((call) => call.path === '/mailbox/checks')).toHaveLength(2)
})

test('a failed finish keeps the pick list and says so', async () => {
  await openPicks(THREE(), { 'POST /mailbox/checks/c1/finish': { status: 500 } })
  await userEvent.click(addButton(6))
  expect(await screen.findByRole('alert')).toHaveTextContent('konnten nicht hinzugefügt werden')
  expect(addButton(6)).toBeEnabled()
})

test('a finish refused because the check was finished elsewhere reads the check again and drops it', async () => {
  let finished = false
  await openPicks(THREE(), {
    'GET /mailbox/checks/c1': () => ({ body: finished ? mailCheck({ status: 'finished' }) : THREE() }),
    'POST /mailbox/checks/c1/finish': () => { finished = true; return { status: 409, body: { error: 'check not done', detail: 'x' } } },
  })
  await userEvent.click(addButton(6))
  expect(await screen.findByRole('button', { name: 'Postfach prüfen' })).toBeVisible()
  expect(screen.queryByRole('list', { name: 'Mails der Prüfung' })).toBeNull()
})

test('clearing a mail\'s checkbox clears its entries, the head counts and the add button follows', async () => {
  await openPicks()
  const head = mailItemOf('Neue Stellen m1')
  expect(headBox('Neue Stellen m1')).toBeChecked()
  await userEvent.click(headBox('Neue Stellen m1'))
  expect(within(head).getByText('0 von 3 ausgewählt')).toBeVisible()
  expect(within(head).getAllByRole('checkbox').slice(1).every((box) => !(box as HTMLInputElement).checked)).toBe(true)
  expect(headBox('Neue Stellen m1')).not.toBeChecked()
  expect(addButton(3)).toBeVisible()
  await userEvent.click(headBox('Neue Stellen m1'))
  expect(within(head).getByText('3 von 3 ausgewählt')).toBeVisible()
  expect(addButton(6)).toBeVisible()
})

test('a mail with some entries selected shows a dash and selects all on the next press', async () => {
  await openPicks()
  await userEvent.click(screen.getByRole('checkbox', { name: 'Stelle 4' }))
  expect(headBox('Neue Stellen m2')).toBePartiallyChecked()
  expect(within(mailItemOf('Neue Stellen m2')).getByText('1 von 2 ausgewählt')).toBeVisible()
  await userEvent.click(headBox('Neue Stellen m2'))
  expect(headBox('Neue Stellen m2')).toBeChecked()
  expect(within(mailItemOf('Neue Stellen m2')).getByText('2 von 2 ausgewählt')).toBeVisible()
})

test('a collapsed mail hides its entries, keeps its selection and its head', async () => {
  await openPicks()
  await userEvent.click(screen.getByRole('checkbox', { name: 'Stelle 3' }))
  const toggle = screen.getByRole('button', { name: 'Anzeigen der Mail „Neue Stellen m1“' })
  const list = screen.getByRole('list', { name: 'Anzeigen der Mail „Neue Stellen m1“' })
  expect(toggle).toHaveAttribute('aria-expanded', 'true')
  expect(toggle).toHaveAttribute('aria-controls', list.id)
  await userEvent.click(toggle)
  expect(toggle).toHaveAttribute('aria-expanded', 'false')
  expect(list).not.toBeVisible()
  expect(document.getElementById(list.id)).toBe(list)
  expect(within(mailItemOf('Neue Stellen m1')).getByText('2 von 3 ausgewählt')).toBeVisible()
  expect(addButton(5)).toBeVisible()
  await userEvent.click(toggle)
  expect(list).toBeVisible()
  expect(screen.getByRole('checkbox', { name: 'Stelle 3' })).not.toBeChecked()
})

test('the report names the mails left, missing folders, failed, held and unscreened mails and an interrupted connection', async () => {
  const head = { folder: 'Jobs', date: '2026-11-21T10:00:00+01:00' }
  await openPicks({
    ...THREE(), remaining: 60, missing_folders: ['Alt'], interrupted: 'unreachable',
    failed: [{ ...head, sender: 'Firma A', subject: 'Angebote A', reason: 'finder failed' }],
    held: [{ ...head, sender: 'Firma B', subject: 'Angebote B' }],
    not_screened: [{ ...head, sender: 'Firma C', subject: 'Angebote C' }],
  })
  const notes = screen.getAllByRole('note').map((note) => note.textContent)
  expect(notes.some((text) => /60 Mails sind für die nächste Prüfung übrig/.test(text!))).toBe(true)
  expect(notes.some((text) => /Alt/.test(text!) && /gibt es nicht mehr/.test(text!))).toBe(true)
  expect(notes.some((text) => /Firma A, „Angebote A“/.test(text!) && /Nicht gelesen/.test(text!))).toBe(true)
  expect(notes.some((text) => /Firma B, „Angebote B“/.test(text!) && /zurückgehalten/.test(text!))).toBe(true)
  expect(notes.some((text) => /Firma C, „Angebote C“/.test(text!) && /Inhaltsprüfung aus/.test(text!))).toBe(true)
  expect(notes.some((text) => /Verbindung unterbrochen/.test(text!) && /nicht erreichbar/.test(text!))).toBe(true)
  expect(screen.queryByRole('listitem', { name: /Angebote A/ })).toBeNull()
})

test('a check without a pick list still shows its report notes, with the dismiss button', async () => {
  const head = { folder: 'Jobs', date: '2026-11-21T10:00:00+01:00' }
  stubApi({ 'GET /mailbox': { body: { ...CHECKED, check_id: 'c1' } },
            'GET /mailbox/checks/c1': { body: mailCheck({ status: 'done', total: 2, read: 2,
              failed: [{ ...head, sender: 'Firma A', subject: 'Angebote A', reason: 'screening failed' }],
              held: [{ ...head, sender: 'Firma B', subject: 'Angebote B' }] }) } })
  view()
  expect(await screen.findByText(/Firma A, „Angebote A“/)).toBeVisible()
  expect(screen.getByText(/Firma B, „Angebote B“/)).toBeVisible()
  expect(screen.getByText(/enthalten keine Anzeigen zum Auswählen/)).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Bericht ausblenden' }))
  expect(screen.queryByText(/Firma A/)).toBeNull()
})

test('a mail head carries the notes of a pasted mail: hosts not read and more than 100 entries', async () => {
  const mail = mailItem('m1', 2)
  mail.preview = { ...mail.preview!, unread_hosts: [{ host: 'jobs.example.com', links: 3 }], truncated: true }
  await openPicks(mailCheck({ status: 'done', total: 1, read: 1, mails: [mail] }))
  const notes = within(mailItemOf('Neue Stellen m1')).getAllByRole('note').map((note) => note.textContent)
  expect(notes.some((text) => /jobs\.example\.com \(3 Links\)/.test(text!))).toBe(true)
  expect(notes.some((text) => /mehr als 100 Stellen/.test(text!))).toBe(true)
})

/** A pick list with an oversized mail `big` (not read) beside a mail `m1` with two entries. */
const WITH_BIG = (big: Partial<ReturnType<typeof mailItem>> = {}) => mailCheck({
  status: 'done', total: 2, read: 2,
  mails: [mailItem('m1', 2), mailItem('big', 0, { oversized: true, preview: null, subject: 'Riesige Mail', ...big })],
})

test('an oversized mail is its own head, not read, with an unticked checkbox, and is not added unticked', async () => {
  const calls = await openPicks(WITH_BIG(), { 'POST /mailbox/checks/c1/finish': { status: 202, body: { run_id: null } } })
  const head = mailItemOf('Riesige Mail')
  expect(within(head).getByText('Zu groß, nicht gelesen')).toBeVisible()
  expect(unreadBox('Riesige Mail')).not.toBeChecked()
  expect(within(head).queryByText(/ausgewählt/)).toBeNull()
  await userEvent.click(addButton(2))
  expect((finishes(calls)[0].body as { entries: unknown[] }).entries).toHaveLength(2)
})

test('ticking an oversized mail reads it, shows that it is read and then its entries below the head', async () => {
  let release: (value: { body: unknown }) => void = () => {}
  const read = new Promise<{ body: unknown }>((resolve) => { release = resolve })
  const calls = await openPicks(WITH_BIG(), { 'POST /mailbox/checks/c1/mails/big/read': () => read })
  await userEvent.click(unreadBox('Riesige Mail'))
  const head = mailItemOf('Riesige Mail')
  expect(within(head).getByText('Wird gelesen …')).toBeVisible()
  expect(addButton(2)).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Nichts hinzufügen' })).toBeDisabled()
  expect(screen.getAllByRole('button', { name: 'Warum ist Hinzufügen nicht möglich?' })).not.toHaveLength(0)
  expect(calls.filter((call) => call.path.endsWith('/read'))).toHaveLength(1)
  await act(async () => release({ body: mailItem('big', 3, { subject: 'Riesige Mail' }, 10) }))
  expect(await within(head).findByRole('checkbox', { name: 'Stelle 10' })).toBeChecked()
  expect(within(head).queryByText('Zu groß, nicht gelesen')).toBeNull()
  expect(within(head).getByText('3 von 3 ausgewählt')).toBeVisible()
  expect(addButton(5)).toBeEnabled()
  expect(screen.getByRole('button', { name: 'Nichts hinzufügen' })).toBeEnabled()
})

test.each([['screening failed', /Inhaltsprüfung hat nicht geantwortet/], ['finder failed', /Modell hat nicht geantwortet/]])(
  'a failed reading of an oversized mail (%s) shows its reason at the head and leaves the box unticked', async (error, text) => {
    await openPicks(WITH_BIG(), { 'POST /mailbox/checks/c1/mails/big/read': { status: 502, body: { error, detail: 'x' } } })
    await userEvent.click(unreadBox('Riesige Mail'))
    expect(await within(mailItemOf('Riesige Mail')).findByText(text)).toBeVisible()
    expect(unreadBox('Riesige Mail')).not.toBeChecked()
    expect(within(mailItemOf('Riesige Mail')).getByText('Zu groß, nicht gelesen')).toBeVisible()
    expect(addButton(2)).toBeEnabled()
  })

test('an oversized mail whose reading failed before shows the reason after a reload', async () => {
  await openPicks(WITH_BIG({ read_failed: 'finder failed' }))
  expect(within(mailItemOf('Riesige Mail')).getByText(/Modell hat nicht geantwortet/)).toBeVisible()
})

test('an oversized mail read in another tab shows as being read, the buttons wait, and its entries come with the next poll', async () => {
  let reads = 0
  await openPicks(WITH_BIG({ reading: true }), {
    'GET /mailbox/checks/c1': () => ({ body: ++reads < 2 ? WITH_BIG({ reading: true })
      : mailCheck({ status: 'done', total: 2, read: 2, mails: [mailItem('m1', 2), mailItem('big', 3, { subject: 'Riesige Mail' }, 10)] }) }),
  })
  expect(within(mailItemOf('Riesige Mail')).getByText('Wird gelesen …')).toBeVisible()
  expect(addButton(2)).toBeDisabled()
  await tick()
  expect(await screen.findByRole('checkbox', { name: 'Stelle 10' })).toBeVisible()
  expect(addButton(5)).toBeEnabled()
})

test('ticking an oversized mail that is being read elsewhere reads the check again and shows it as being read', async () => {
  let reading = false
  await openPicks(WITH_BIG(), {
    'GET /mailbox/checks/c1': () => ({ body: WITH_BIG({ reading }) }),
    'POST /mailbox/checks/c1/mails/big/read': () => { reading = true; return { status: 409, body: { error: 'read in progress', detail: 'x' } } },
  })
  await userEvent.click(unreadBox('Riesige Mail'))
  expect(await within(mailItemOf('Riesige Mail')).findByText('Wird gelesen …')).toBeVisible()
  expect(addButton(2)).toBeDisabled()
})

test('a finish refused while a mail is read elsewhere shows that mail as being read', async () => {
  let reading = false
  await openPicks(WITH_BIG(), {
    'GET /mailbox/checks/c1': () => ({ body: WITH_BIG({ reading }) }),
    'POST /mailbox/checks/c1/finish': () => { reading = true; return { status: 409, body: { error: 'read in progress', detail: 'x' } } },
  })
  await userEvent.click(addButton(2))
  expect(await within(mailItemOf('Riesige Mail')).findByText('Wird gelesen …')).toBeVisible()
})

test('a cancelled check shows its pick list with the note of how far it got', async () => {
  await openPicks({ ...THREE(), cancelled: true, total: 200, read: 37 })
  expect(screen.getAllByRole('note').some((note) => /nach 37 von 200 Mails abgebrochen/.test(note.textContent!))).toBe(true)
  expect(screen.getByRole('list', { name: 'Mails der Prüfung' })).toBeVisible()
})

// ---- final review: stale source, stale failures, notes for read outcomes ----

/** Leave or enter a route as the browser does: the hash changes and `hashchange` fires. */
const goTo = (hash: string) => act(async () => {
  window.history.replaceState(null, '', hash)
  window.dispatchEvent(new HashChangeEvent('hashchange'))
})

test('the source reads the account again when the user comes back from the settings page', async () => {
  let configured = false
  const calls = stubApi({ 'GET /mailbox': () => ({ body: configured ? MAILBOX : NO_MAILBOX }) })
  view()
  expect(await screen.findByText(/Noch kein Postfach eingerichtet/)).toBeVisible()
  await goTo('#/einstellungen/postfach')
  configured = true // the mailbox is set up on the settings page
  expect(calls.filter((call) => call.path === '/mailbox')).toHaveLength(1)
  await goTo('#/hinzufuegen')
  expect(await screen.findByRole('button', { name: 'Postfach prüfen' })).toBeVisible()
  expect(screen.getByText(/name@example\.org/)).toHaveTextContent('imap.example.org')
  expect(screen.queryByText(/Noch kein Postfach eingerichtet/)).toBeNull()
})

test('a pick list the settings dropped is gone after coming back from the settings page', async () => {
  let dropped = false
  await openPicks(THREE(), { 'GET /mailbox/checks/c1': () => ({ body: dropped ? { ...THREE(), status: 'finished' } : THREE() }) })
  await goTo('#/einstellungen/postfach')
  dropped = true
  await goTo('#/hinzufuegen')
  await vi.waitFor(() => expect(screen.queryByRole('list', { name: 'Mails der Prüfung' })).toBeNull())
})

test('the account is not read again by a hash change while the source never was shown', async () => {
  const calls = stubApi({ 'GET /mailbox': { body: MAILBOX } })
  view({ active: false })
  await goTo('#/hinzufuegen')
  expect(calls).toHaveLength(0)
})

test('a failed reading of an oversized mail does not stay on the same mail of the next check', async () => {
  let started = false
  await openPicks(WITH_BIG(), {
    'POST /mailbox/checks/c1/mails/big/read': { status: 502, body: { error: 'finder failed', detail: 'x' } },
    'POST /mailbox/checks': () => { started = true; return { status: 202, body: { check_id: 'c2' } } },
    'GET /mailbox/checks/c2': { body: { ...WITH_BIG(), check_id: 'c2' } },
    'GET /mailbox': () => ({ body: { ...CHECKED, check_id: started ? 'c2' : 'c1' } }),
  })
  await userEvent.click(unreadBox('Riesige Mail'))
  expect(await within(mailItemOf('Riesige Mail')).findByText(/Modell hat nicht geantwortet/)).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Postfach prüfen' }))
  await vi.waitFor(() => expect(screen.getByRole('list', { name: 'Mails der Prüfung' })).toBeVisible())
  await vi.waitFor(() => expect(within(mailItemOf('Riesige Mail')).getByText('Zu groß, nicht gelesen')).toBeVisible())
  expect(within(mailItemOf('Riesige Mail')).queryByText(/Modell hat nicht geantwortet/)).toBeNull()
})

test('a failure shows only for an unread oversized mail, and the server\'s read failure wins over a local one', async () => {
  await openPicks(WITH_BIG({ read_failed: 'screening failed' }), {
    'POST /mailbox/checks/c1/mails/big/read': { status: 502, body: { error: 'finder failed', detail: 'x' } },
  })
  const head = mailItemOf('Riesige Mail')
  expect(within(head).getByText(/Inhaltsprüfung hat nicht geantwortet/)).toBeVisible()
  await userEvent.click(unreadBox('Riesige Mail'))
  expect(await within(head).findByText(/Modell hat nicht geantwortet|Inhaltsprüfung hat nicht geantwortet/)).toBeVisible()
  expect(within(head).queryByText(/Modell hat nicht geantwortet/)).toBeNull()
})

const NO_ENTRIES = { entries: [], read_by: ['model'], unread_hosts: [], held: false, model_skipped: null, truncated: false }

test.each([
  ['finds no postings', NO_ENTRIES, /keine Anzeigen/],
  ['is held by the content guard', { ...NO_ENTRIES, held: true }, /Inhaltsprüfung zurückgehalten/],
  ['waits for the screening', { ...NO_ENTRIES, model_skipped: 'screening off' }, /Inhaltsprüfung aus/],
])('an oversized mail read on request that %s says so and explains the disabled checkbox', async (_name, preview, note) => {
  await openPicks(WITH_BIG(), {
    'POST /mailbox/checks/c1/mails/big/read': { body: mailItem('big', 0, { subject: 'Riesige Mail', preview }) },
  })
  await userEvent.click(unreadBox('Riesige Mail'))
  const head = mailItemOf('Riesige Mail')
  expect(await within(head).findByText(note)).toBeVisible()
  const box = within(head).getByRole('checkbox', { name: 'Alle Anzeigen der Mail „Riesige Mail“' })
  expect(box).toBeDisabled()
  expect(box).toHaveAccessibleDescription(/keine Anzeige, die du auswählen kannst/)
  expect(within(head).getByRole('button', { name: 'Warum ist die Mail nicht auswählbar?' })).toBeVisible()
})

test('a mail whose entries are all stored has a disabled head checkbox with its reason', async () => {
  await openPicks()
  const head = mailItemOf('Neue Stellen m3')
  expect(within(head).getByRole('checkbox', { name: 'Alle Anzeigen der Mail „Neue Stellen m3“' })).toBeEnabled()
  const locked = { ...mailItem('m1', 1), preview: { ...mailItem('m1', 1).preview!, entries: [{ ...mailEntries(1)[0], duplicate: dup }] } }
  cleanup()
  await openPicks(mailCheck({ status: 'done', total: 1, read: 1, mails: [locked] }))
  expect(within(mailItemOf('Neue Stellen m1')).getByRole('checkbox', { name: 'Alle Anzeigen der Mail „Neue Stellen m1“' })).toBeDisabled()
  expect(within(mailItemOf('Neue Stellen m1')).getByRole('button', { name: 'Warum ist die Mail nicht auswählbar?' })).toBeVisible()
})

test('a new check is announced to replace an open pick list', async () => {
  await openPicks()
  expect(screen.getByText('Eine neue Prüfung ersetzt die offene Auswahlliste.')).toBeVisible()
  expect(checkButton()).toHaveAccessibleDescription('Eine neue Prüfung ersetzt die offene Auswahlliste.')
})

test('without an open pick list there is no replace hint', async () => {
  stubApi({ 'GET /mailbox': { body: CHECKED } })
  view()
  await screen.findByRole('button', { name: 'Postfach prüfen' })
  expect(screen.queryByText(/ersetzt die offene Auswahlliste/)).toBeNull()
})

test('the pick list has unique ids and no accessibility violations', async () => {
  await openPicks()
  const container = document.body
  const ids = Array.from(container.querySelectorAll('[id]'), (element) => element.id)
  expect(new Set(ids).size).toBe(ids.length)
  expect(await axe(container, { rules: { region: { enabled: false } } })).toHaveNoViolations()
})
