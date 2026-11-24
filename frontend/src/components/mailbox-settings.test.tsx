import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import type { MailboxAccount } from '@/api'
import { axe } from '@/test-axe'
import { stubApi } from '@/test-api'
import { MAILBOX, NO_MAILBOX } from '@/test-fixtures'
import { MailboxSettings } from './mailbox-settings'

afterEach(() => vi.unstubAllGlobals())

const FOLDERS = [{ name: 'Posteingang', system: false }, { name: 'Jobs', system: false },
                 { name: 'Papierkorb', system: true }]
const CONNECT = 'Verbinden und Ordner laden'
const LIMIT = 'Höchstens Mails pro Prüfung'

/** Render the section over `account` and wait for its fields; `routes` add to the stub. */
async function open(account: MailboxAccount = MAILBOX, routes: Parameters<typeof stubApi>[0] = {}) {
  const calls = stubApi({ 'GET /mailbox': { body: account }, ...routes })
  render(<MailboxSettings />)
  await screen.findByLabelText('Server')
  return calls
}

const puts = (calls: { method: string; body: unknown }[]) => calls.filter((call) => call.method === 'PUT')

/** Fill the account of a fresh mailbox. */
async function fill(password = 'geheim') {
  await userEvent.type(screen.getByLabelText('Server'), 'imap.example.org')
  await userEvent.type(screen.getByLabelText('Benutzername'), 'name@example.org')
  if (password) await userEvent.type(screen.getByLabelText('Passwort'), password)
}

test('the fields start empty without a mailbox, with 993 as the port hint and the app password advice', async () => {
  await open(NO_MAILBOX)
  expect(screen.getByLabelText('Server')).toHaveValue('')
  expect(screen.getByLabelText('Port')).toHaveValue(null)
  expect(screen.getByLabelText('Port')).toHaveAttribute('placeholder', '993')
  expect(screen.getByLabelText('Benutzername')).toHaveValue('')
  expect(screen.getByText(/App-Passwort/)).toBeVisible()
  expect(screen.queryByRole('group', { name: 'Ordner' })).toBeNull()
})

test('first connection: stores the account, logs in and shows the folder choice', async () => {
  const calls = await open(NO_MAILBOX, {
    'PUT /mailbox': { body: { ...MAILBOX, password: 'stored' } },
    'POST /mailbox/folders': { body: { folders: FOLDERS } },
  })
  await fill()
  await userEvent.click(screen.getByRole('button', { name: CONNECT }))
  expect(await screen.findByText(/Verbunden/)).toHaveTextContent('3 Ordner')
  expect(puts(calls)[0].body).toEqual({ host: 'imap.example.org', port: 993, user: 'name@example.org',
                                       password: 'geheim', max_mails: 200 })
  expect(calls.map((call) => `${call.method} ${call.path}`).slice(-2)).toEqual(['PUT /mailbox', 'POST /mailbox/folders'])
  expect(screen.getByRole('group', { name: 'Ordner' })).toBeVisible()
  expect(screen.getByLabelText('Passwort · gespeichert')).toHaveValue('')
})

test('login refused: says so beside the form, keeps the fields and empties the password', async () => {
  await open(NO_MAILBOX, {
    'PUT /mailbox': { body: { ...MAILBOX, password: 'stored' } },
    'POST /mailbox/folders': { status: 502, body: { error: 'login', detail: 'login refused' } },
  })
  await fill()
  await userEvent.click(screen.getByRole('button', { name: CONNECT }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Anmeldung abgelehnt')
  expect(screen.getByLabelText('Server')).toHaveValue('imap.example.org')
  expect(screen.getByLabelText('Benutzername')).toHaveValue('name@example.org')
  expect(screen.getByLabelText('Passwort · gespeichert')).toHaveValue('')
  expect(screen.queryByRole('group', { name: 'Ordner' })).toBeNull()
})

test.each([['unreachable', /nicht erreichbar/], ['certificate', /Zertifikat/], ['protocol', /Port/]])(
  'a %s failure of the login is named', async (error, text) => {
    await open(MAILBOX, { 'PUT /mailbox': { body: MAILBOX },
                          'POST /mailbox/folders': { status: 502, body: { error, detail: 'x' } } })
    await userEvent.click(screen.getByRole('button', { name: CONNECT }))
    expect(await screen.findByRole('alert')).toHaveTextContent(text)
  })

test('connecting without a stored or typed password asks for it', async () => {
  await open({ ...MAILBOX, password: 'missing' }, {
    'PUT /mailbox': { body: { ...MAILBOX, password: 'missing' } },
    'POST /mailbox/folders': { status: 409, body: { error: 'no password', detail: 'x' } },
  })
  await userEvent.click(screen.getByRole('button', { name: CONNECT }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Gib das Passwort ein')
})

test('the port defaults to 993 when empty and is checked otherwise', async () => {
  const calls = await open(NO_MAILBOX, { 'PUT /mailbox': { body: MAILBOX }, 'POST /mailbox/folders': { body: { folders: FOLDERS } } })
  await fill()
  await userEvent.type(screen.getByLabelText('Port'), '99999')
  await userEvent.click(screen.getByRole('button', { name: CONNECT }))
  expect(await screen.findByRole('alert')).toHaveTextContent(/Port.*1 bis 65535/)
  expect(puts(calls)).toHaveLength(0)
  await userEvent.clear(screen.getByLabelText('Port'))
  await userEvent.type(screen.getByLabelText('Port'), '143')
  await userEvent.click(screen.getByRole('button', { name: CONNECT }))
  await screen.findByText(/Verbunden/)
  expect((puts(calls)[0].body as { port: number }).port).toBe(143)
})

test('the eye button shows and hides the typed password', async () => {
  await open(NO_MAILBOX)
  const password = screen.getByLabelText('Passwort')
  const eye = screen.getByRole('button', { name: 'Passwort anzeigen' })
  expect(password).toHaveAttribute('type', 'password')
  expect(eye).toHaveAttribute('aria-pressed', 'false')
  await userEvent.type(password, 'geheim')
  await userEvent.click(eye)
  expect(password).toHaveAttribute('type', 'text')
  expect(password).toHaveValue('geheim')
  expect(eye).toHaveAttribute('aria-pressed', 'true')
  await userEvent.click(eye)
  expect(password).toHaveAttribute('type', 'password')
  expect(eye).toHaveAttribute('aria-pressed', 'false')
})

test('a stored password shows as eight dots, labelled as stored, and is never filled in', async () => {
  await open()
  const password = screen.getByLabelText('Passwort · gespeichert')
  expect(password).toHaveAttribute('placeholder', '••••••••')
  expect(password).toHaveValue('')
})

test('a stored password is kept when only the folder choice is saved', async () => {
  const calls = await open(MAILBOX, {
    'PUT /mailbox': { body: { ...MAILBOX, folders: { names: ['Jobs'] } } },
    'POST /mailbox/folders': { body: { folders: FOLDERS } },
  })
  await userEvent.click(screen.getByRole('button', { name: CONNECT }))
  await screen.findByRole('group', { name: 'Ordner' })
  await userEvent.click(screen.getByRole('radio', { name: 'Nur diese Ordner' }))
  await userEvent.click(screen.getByRole('checkbox', { name: 'Jobs' }))
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  expect(await screen.findByText('Gespeichert.')).toBeVisible()
  for (const call of puts(calls)) expect(call.body).not.toHaveProperty('password')
  expect(puts(calls).at(-1)!.body).toMatchObject({ folders: { names: ['Jobs'] } })
  expect(screen.getByLabelText('Passwort · gespeichert')).toHaveAttribute('placeholder', '••••••••')
})

test('a changed server without a password leaves the field empty and asks for the password', async () => {
  const calls = await open(MAILBOX, { 'PUT /mailbox': { body: { ...MAILBOX, host: 'imap.other.org', password: 'missing' } } })
  await userEvent.clear(screen.getByLabelText('Server'))
  await userEvent.type(screen.getByLabelText('Server'), 'imap.other.org')
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  expect(await screen.findByText(/Kein Passwort gespeichert/)).toBeVisible()
  expect(screen.getByLabelText('Passwort')).toHaveValue('')
  expect(screen.queryByLabelText('Passwort · gespeichert')).toBeNull()
  expect(puts(calls)[0].body).not.toHaveProperty('password')
})

test('a stored password the key cannot open is named and asked for again', async () => {
  await open({ ...MAILBOX, password: 'unreadable' })
  expect(screen.getByText(/lässt sich nicht lesen/)).toBeVisible()
  expect(screen.queryByLabelText('Passwort · gespeichert')).toBeNull()
})

test('without a key the password field and the connect button are disabled, each with an info icon', async () => {
  await open({ ...MAILBOX, key_configured: false, password: 'unreadable' })
  expect(screen.getByLabelText('Passwort')).toBeDisabled()
  expect(screen.getByRole('button', { name: CONNECT })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Passwort anzeigen' })).toBeDisabled()
  const icons = screen.getAllByRole('button', { name: /Warum/ })
  expect(icons).toHaveLength(2)
  await userEvent.hover(icons[0])
  expect(screen.getAllByRole('tooltip', { hidden: false })[0]).toHaveTextContent(/kein Schlüssel.*README/)
  expect(screen.getByLabelText('Passwort')).toHaveAccessibleDescription(/kein Schlüssel/)
  expect(screen.getByRole('button', { name: 'Speichern' })).toBeEnabled()
})

test('with a key there is no info icon and the fields work', async () => {
  await open()
  expect(screen.queryByRole('button', { name: /Warum/ })).toBeNull()
  expect(screen.getByLabelText('Passwort · gespeichert')).toBeEnabled()
})

test('the folder choice follows a connection: the hint, all folders at first, system folders unticked', async () => {
  await open(MAILBOX, { 'PUT /mailbox': { body: MAILBOX }, 'POST /mailbox/folders': { body: { folders: FOLDERS } } })
  await userEvent.click(screen.getByRole('button', { name: CONNECT }))
  const group = await screen.findByRole('group', { name: 'Ordner' })
  expect(within(group).getByText('Wähle nur Ordner, in denen ausschließlich Job-Alert-Mails liegen.')).toBeVisible()
  expect(within(group).getByRole('radio', { name: 'Alle Ordner' })).toBeChecked()
  expect(within(group).queryByRole('checkbox')).toBeNull()
  await userEvent.click(within(group).getByRole('radio', { name: 'Nur diese Ordner' }))
  expect(within(group).getAllByRole('checkbox').map((box) => (box as HTMLInputElement).checked)).toEqual([false, false, false])
  expect(within(group).getByRole('checkbox', { name: /Papierkorb/ })).toHaveAccessibleName(/Systemordner/)
})

test('a selection of folders is stored', async () => {
  const calls = await open(MAILBOX, { 'PUT /mailbox': { body: MAILBOX }, 'POST /mailbox/folders': { body: { folders: FOLDERS } } })
  await userEvent.click(screen.getByRole('button', { name: CONNECT }))
  await screen.findByRole('group', { name: 'Ordner' })
  await userEvent.click(screen.getByRole('radio', { name: 'Nur diese Ordner' }))
  await userEvent.click(screen.getByRole('checkbox', { name: 'Jobs' }))
  await userEvent.click(screen.getByRole('checkbox', { name: 'Posteingang' }))
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  await screen.findByText('Gespeichert.')
  expect(puts(calls).at(-1)!.body).toMatchObject({ folders: { names: ['Posteingang', 'Jobs'] } })
})

test('all folders is stored as such', async () => {
  const calls = await open({ ...MAILBOX, folders: { names: ['Jobs'] } }, {
    'PUT /mailbox': { body: MAILBOX }, 'POST /mailbox/folders': { body: { folders: FOLDERS } } })
  await userEvent.click(screen.getByRole('button', { name: CONNECT }))
  await screen.findByRole('group', { name: 'Ordner' })
  expect(screen.getByRole('radio', { name: 'Nur diese Ordner' })).toBeChecked()
  expect(screen.getByRole('checkbox', { name: 'Jobs' })).toBeChecked()
  await userEvent.click(screen.getByRole('radio', { name: 'Alle Ordner' }))
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  await screen.findByText('Gespeichert.')
  expect(puts(calls).at(-1)!.body).toMatchObject({ folders: { all: true } })
})

test('a selection without a folder is refused inline', async () => {
  const calls = await open(MAILBOX, { 'PUT /mailbox': { body: MAILBOX }, 'POST /mailbox/folders': { body: { folders: FOLDERS } } })
  await userEvent.click(screen.getByRole('button', { name: CONNECT }))
  await screen.findByRole('group', { name: 'Ordner' })
  const before = puts(calls).length
  await userEvent.click(screen.getByRole('radio', { name: 'Nur diese Ordner' }))
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('mindestens einen Ordner')
  expect(puts(calls)).toHaveLength(before)
})

test('the limit is preset to 200 and stored with the account', async () => {
  const calls = await open(MAILBOX, { 'PUT /mailbox': { body: { ...MAILBOX, max_mails: 50 } } })
  const limit = screen.getByLabelText(LIMIT)
  expect(limit).toHaveValue(200)
  expect(limit).toHaveAttribute('min', '1')
  expect(limit).toHaveAttribute('max', '1000')
  await userEvent.clear(limit)
  await userEvent.type(limit, '50')
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  expect(await screen.findByText('Gespeichert.')).toBeVisible()
  expect(puts(calls)[0].body).toMatchObject({ max_mails: 50 })
  expect(screen.getByLabelText(LIMIT)).toHaveValue(50)
})

test.each(['5000', '0', '2.5', ''])('a limit of "%s" is refused beside the field and nothing is stored', async (value) => {
  const calls = await open()
  const limit = screen.getByLabelText(LIMIT)
  await userEvent.clear(limit)
  if (value) await userEvent.type(limit, value)
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  expect(await screen.findByText(/ganze Zahl von 1 bis 1000/)).toBeVisible()
  expect(limit).toHaveAccessibleDescription(/von 1 bis 1000/)
  expect(puts(calls)).toHaveLength(0)
})

test('a failed save keeps the input and says so', async () => {
  await open(MAILBOX, { 'PUT /mailbox': { status: 500 } })
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('nicht gespeichert')
  expect(screen.getByLabelText('Server')).toHaveValue('imap.example.org')
})

test('a failed load of the account offers a retry', async () => {
  let failing = true
  stubApi({ 'GET /mailbox': () => (failing ? { status: 500 } : { body: MAILBOX }) })
  render(<MailboxSettings />)
  failing = false
  await userEvent.click(await screen.findByRole('button', { name: 'Erneut versuchen' }))
  expect(await screen.findByLabelText('Server')).toHaveValue('imap.example.org')
})

test('a password change without a key is refused by the server and said so', async () => {
  await open(NO_MAILBOX, { 'PUT /mailbox': { status: 409, body: { error: 'no key', detail: 'x' } } })
  await fill()
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('kein Schlüssel')
})

test('the section has no accessibility violations, also with the folder choice open', async () => {
  await open(MAILBOX, { 'PUT /mailbox': { body: MAILBOX }, 'POST /mailbox/folders': { body: { folders: FOLDERS } } })
  expect(await axe(document.body, { rules: { region: { enabled: false } } })).toHaveNoViolations()
  await userEvent.click(screen.getByRole('button', { name: CONNECT }))
  await userEvent.click(await screen.findByRole('radio', { name: 'Nur diese Ordner' }))
  expect(await axe(document.body, { rules: { region: { enabled: false } } })).toHaveNoViolations()
})
