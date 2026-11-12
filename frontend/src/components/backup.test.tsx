import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { BackupControl, BackupStrip } from '@/components/backup'
import type { BackupState, BackupStatus } from '@/lib/backup'
import { axe } from '@/test-axe'

// "Now" is 12 November 2026, 15:00 local time; times below are local, so the tests hold in any
// time zone.
const NOW = new Date(2026, 10, 12, 15, 0, 0)
const at = (day: number, hour: number, minute: number, second = 0) =>
  new Date(2026, 10, day, hour, minute, second).toISOString()

beforeEach(() => { vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(NOW) })
afterEach(() => vi.useRealTimers())

const QUIET: BackupStatus = {
  pending: false, uncommitted: 0, unpushed: 0, branch: 'main', remote: 'origin/main',
  operation: null, running: false, progress: null, last_result: null,
  last_success: at(12, 14, 32), last_failure: null,
}
const PENDING: BackupStatus = {
  ...QUIET, pending: true, uncommitted: 3, last_success: at(12, 9, 12),
}

/** A control state around `status`, with `press` recorded. */
function state(status: BackupStatus | null, extra: Partial<BackupState> = {}) {
  const press = vi.fn()
  return {
    press,
    value: { status, unavailable: null, refusal: null, pressFailed: null, press, ...extra } as BackupState,
  }
}

const button = () => screen.getAllByRole('button')[0]

test('pending changes highlight the button, with their number, and say so in words', () => {
  render(<BackupControl state={state(PENDING).value} />)
  expect(screen.getByRole('button', { name: 'Sichern (3)' })).toHaveAttribute('data-variant', 'default')
  expect(screen.getByText('3 Änderungen nicht gesichert · zuletzt heute, 09:12')).toBeVisible()
})

test('one change is named in the singular', () => {
  render(<BackupControl state={state({ ...PENDING, uncommitted: 1 }).value} />)
  expect(screen.getByText(/^1 Änderung nicht gesichert/)).toBeVisible()
  expect(screen.getByRole('button', { name: 'Sichern (1)' })).toBeVisible()
})

test('commits the remote lacks count with the uncommitted files', () => {
  render(<BackupControl state={state({ ...PENDING, uncommitted: 1, unpushed: 2 }).value} />)
  expect(screen.getByRole('button', { name: 'Sichern (3)' })).toBeVisible()
})

test('nothing pending is a quiet button that still backs up when pressed, and the time', async () => {
  const { press, value } = state(QUIET)
  render(<BackupControl state={value} />)
  const quiet = screen.getByRole('button', { name: 'Gesichert – jetzt erneut sichern' })
  expect(quiet).toHaveAttribute('data-variant', 'outline')
  expect(quiet).toBeEnabled()
  expect(screen.getByText('zuletzt heute, 14:32')).toBeVisible()
  await userEvent.click(quiet)
  expect(press).toHaveBeenCalledOnce()
})

test('a backup that has never succeeded says so', () => {
  render(<BackupControl state={state({ ...PENDING, last_success: null }).value} />)
  expect(screen.getByText('3 Änderungen nicht gesichert · noch keine Sicherung')).toBeVisible()
})

test('yesterday and older times name the day', () => {
  const { rerender } = render(
    <BackupControl state={state({ ...QUIET, last_success: at(11, 21, 5) }).value} />)
  expect(screen.getByText('zuletzt gestern, 21:05')).toBeVisible()
  rerender(<BackupControl state={state({ ...QUIET, last_success: at(3, 8, 30) }).value} />)
  expect(screen.getByText('zuletzt 3.11., 08:30')).toBeVisible()
})

test('while a backup runs the button is disabled and the line says so', () => {
  render(<BackupControl state={state({
    ...PENDING, running: true, progress: { step: 'pushing', files: 3, percent: 60 } }).value} />)
  expect(screen.getByRole('button', { name: /Sichern \(3\)/ })).toBeDisabled()
  expect(screen.getByText('wird gesichert…')).toBeVisible()
})

test('a push that just finished says so, quiet', () => {
  render(<BackupControl state={state({
    ...QUIET, last_success: at(12, 14, 59, 30),
    last_result: { at: at(12, 14, 59, 30), result: 'pushed', commit: 'abc' } }).value} />)
  expect(screen.getByText('Gepusht, gerade eben')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Gesichert – jetzt erneut sichern' })).toBeVisible()
})

test('a push that finished a while ago shows only the time', () => {
  render(<BackupControl state={state({
    ...QUIET, last_result: { at: at(12, 14, 32), result: 'pushed', commit: 'abc' } }).value} />)
  expect(screen.getByText('zuletzt heute, 14:32')).toBeVisible()
  expect(screen.queryByText(/gerade eben/)).toBeNull()
})

test('a repository without a remote says the changes were committed and not pushed', () => {
  render(<BackupControl state={state({
    ...QUIET, remote: null,
    last_result: { at: at(12, 14, 59, 30), result: 'committed', commit: 'abc' } }).value} />)
  expect(screen.getByText(/Nur lokal committet – kein Remote eingerichtet/)).toBeVisible()
})

test('a failed push shows a toggle in place of the line, which opens git\'s reason', async () => {
  const failure = { at: at(12, 14, 35), step: 'push' as const,
                    reason: 'ssh: connect to host remote port 22: Connection timed out' }
  const { press, value } = state({ ...PENDING, uncommitted: 0, unpushed: 1, last_failure: failure })
  render(<BackupControl state={value} />)
  const toggle = screen.getByRole('button', { name: 'Nicht gepusht' })
  expect(toggle).toHaveAttribute('aria-expanded', 'false')
  expect(screen.queryByText(/nicht gesichert · zuletzt/)).toBeNull()
  expect(screen.queryByText(/Connection timed out/)).toBeNull()
  await userEvent.click(toggle)
  expect(toggle).toHaveAttribute('aria-expanded', 'true')
  const panel = screen.getByRole('dialog', { name: 'Push fehlgeschlagen' })
  expect(panel).toHaveTextContent('Deine Änderungen sind lokal committet und gehen nicht verloren')
  expect(panel).toHaveTextContent('ssh: connect to host remote port 22: Connection timed out')
  expect(panel).toHaveTextContent('Letzter Versuch: heute, 14:35 · zuletzt gesichert: heute, 09:12')
  const retry = screen.getByRole('button', { name: 'Erneut sichern (1)' })
  expect(retry).toBeEnabled()
  expect(retry).toHaveAttribute('data-variant', 'default')
  await userEvent.click(retry)
  expect(press).toHaveBeenCalledOnce()
})

test('the failure panel closes on a second press of the toggle, Escape and a click outside', async () => {
  const failure = { at: at(12, 14, 35), step: 'push' as const, reason: 'rejected' }
  render(<div><p>elsewhere</p><BackupControl state={state({ ...PENDING, last_failure: failure }).value} /></div>)
  const toggle = screen.getByRole('button', { name: 'Nicht gepusht' })
  await userEvent.click(toggle)
  await userEvent.click(toggle)
  expect(screen.queryByRole('dialog')).toBeNull()
  await userEvent.click(toggle)
  await userEvent.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).toBeNull()
  await userEvent.click(toggle)
  await userEvent.click(screen.getByText('elsewhere'))
  expect(screen.queryByRole('dialog')).toBeNull()
})

test('a rejected push says a retry cannot help and points to the manual recovery', async () => {
  const failure = { at: at(12, 14, 35), step: 'push' as const,
                    reason: '! [rejected] main -> main (fetch first)' }
  render(<BackupControl state={state({ ...PENDING, last_failure: failure }).value} />)
  await userEvent.click(screen.getByRole('button', { name: 'Nicht gepusht' }))
  const panel = screen.getByRole('dialog', { name: 'Push fehlgeschlagen' })
  expect(panel).toHaveTextContent('Der Remote hat Änderungen, die hier fehlen')
  expect(panel).not.toHaveTextContent('versuch es noch einmal')
})

test('no remote and no backup yet does not claim a local commit', () => {
  render(<BackupControl state={state({ ...QUIET, remote: null, last_success: null }).value} />)
  expect(screen.getByText('Kein Remote eingerichtet · noch keine Sicherung')).toBeVisible()
})

test('a failed commit is named as not backed up, not as not pushed', async () => {
  const failure = { at: at(12, 14, 35), step: 'commit' as const, reason: 'rejected by hook' }
  render(<BackupControl state={state({ ...PENDING, last_failure: failure }).value} />)
  await userEvent.click(screen.getByRole('button', { name: 'Nicht gesichert' }))
  expect(screen.getByRole('dialog', { name: 'Sichern fehlgeschlagen' })).toHaveTextContent('rejected by hook')
})

test('an unavailable backup disables the button and gives the reason on a focusable info icon', async () => {
  render(<BackupControl state={state(null, { unavailable: '/data is not a git repository' }).value} />)
  expect(screen.getByRole('button', { name: 'Sichern' })).toBeDisabled()
  expect(screen.queryByRole('tooltip')).toBeNull()
  await userEvent.tab()
  const info = screen.getByRole('button', { name: 'Warum ist Sichern nicht möglich?' })
  expect(info).toHaveFocus()
  expect(screen.getByRole('tooltip')).toHaveTextContent('Das Datenverzeichnis ist kein eigenes Git-Repository')
})

test('before the first status arrives the control shows nothing to press', () => {
  render(<BackupControl state={state(null).value} />)
  expect(screen.queryByRole('button')).toBeNull()
})

test('a refused press says why, in German', () => {
  render(<BackupControl state={state(PENDING, { refusal: 'on branch other' }).value} />)
  expect(screen.getByText(/Sichern geht nur auf main; das Repository steht auf „other“/)).toBeVisible()
})

test('a press that failed on the way says so, in place of the status line', () => {
  render(<BackupControl state={state(PENDING, { pressFailed: 'Der Server ist nicht erreichbar.' }).value} />)
  expect(screen.getByText('Sichern wurde nicht gestartet. Der Server ist nicht erreichbar.')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Sichern (3)' })).toBeEnabled()
})

test('a refusal for an operation in progress says why', () => {
  render(<BackupControl state={state(PENDING, { refusal: 'a merge is in progress' }).value} />)
  expect(screen.getByText(/ein merge ist noch nicht abgeschlossen/)).toBeVisible()
})

test('the strip shows the step, the files and the share of the push', () => {
  render(<BackupStrip status={{
    ...PENDING, running: true, progress: { step: 'pushing', files: 40, percent: 60 } }} />)
  const strip = screen.getByRole('status')
  expect(strip).toHaveTextContent('Schritt 3 von 3: Pushen zum Remote')
  expect(strip).toHaveTextContent('40 Dateien · 60 %')
})

test('the strip leaves out the share when git reports none, and counts two steps without a remote', () => {
  render(<BackupStrip status={{
    ...PENDING, remote: null, running: true, progress: { step: 'committing', files: 1, percent: null } }} />)
  const strip = screen.getByRole('status')
  expect(strip).toHaveTextContent('Schritt 2 von 2: Committen')
  expect(strip).toHaveTextContent('1 Datei')
  expect(strip).not.toHaveTextContent('%')
})

test('the strip is absent unless a backup runs', () => {
  const { container } = render(<BackupStrip status={PENDING} />)
  expect(container).toBeEmptyDOMElement()
})

test('every state of the control has no accessibility violations', async () => {
  for (const [status, extra] of [
    [PENDING, {}], [QUIET, {}], [{ ...PENDING, running: true }, {}], [null, { unavailable: 'x is not a git repository' }],
    [{ ...PENDING, last_failure: { at: at(12, 14, 35), step: 'push' as const, reason: 'r' } }, {}],
  ] as const) {
    const { container, unmount } = render(<BackupControl state={state(status, extra).value} />)
    expect(await axe(container)).toHaveNoViolations()
    unmount()
  }
})

test('the first button is the backup button', () => {
  render(<BackupControl state={state(PENDING).value} />)
  expect(button()).toHaveTextContent('Sichern (3)')
})
