import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { MailboxAccount } from '@/api'
import { axe } from '@/test-axe'
import { stubApi } from '@/test-api'
import { mailCheck, MAILBOX, NO_MAILBOX } from '@/test-fixtures'
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
  const progress = await screen.findByRole('region', { name: 'Stand der Prüfung' })
  expect(progress).toHaveTextContent('12 neue Mails gefunden, 5 gelesen')
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
