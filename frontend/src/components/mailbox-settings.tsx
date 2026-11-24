import { useEffect, useId, useState, type FormEvent } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { api, ApiError, type MailboxAccount, type MailboxBody, type MailboxFolder } from '@/api'
import { ErrorWithRetry, Loading } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { WhyDisabled } from '@/components/why'
import { mailboxReason } from '@/lib/mailbox'

const DOTS = '••••••••'
const LIMIT_PROBLEM = 'Gib eine ganze Zahl von 1 bis 1000 an.'
const PORT_PROBLEM = 'Der Port muss eine ganze Zahl von 1 bis 65535 sein.'

/** German text for a failed `PUT /mailbox`. */
function saveFailure(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.error === 'no key') return mailboxReason('no key')
    if (error.error === 'check in progress') return 'Eine Prüfung läuft gerade. Server oder Benutzername lassen sich erst danach ändern.'
    if (error.error === 'read in progress') return 'Eine zu große Mail wird gerade gelesen. Versuch es danach noch einmal.'
    if (error.status === 422) return 'Die Angaben wurden nicht angenommen. Prüfe Server, Port und Benutzername.'
  }
  return 'Die Einstellungen wurden nicht gespeichert. Ist der Server erreichbar?'
}

/** German text for a failed `POST /mailbox/folders`: the reason of the answer, else a general one. */
function connectFailure(error: unknown): string {
  if (error instanceof ApiError && (error.status === 502 || error.status === 409)) return mailboxReason(error.error)
  return 'Die Ordner konnten nicht geladen werden. Ist der Server erreichbar?'
}

/** The section „Postfach“ of the settings page: loads `GET /mailbox`, then shows the form. A
 * failed load offers a retry. */
export function MailboxSettings() {
  const [account, setAccount] = useState<MailboxAccount | null>(null)
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let stale = false
    api<MailboxAccount>('/mailbox').then((next) => { if (!stale) setAccount(next) },
                                          () => { if (!stale) setFailed(true) })
    return () => { stale = true }
  }, [attempt])
  if (failed) {
    return <ErrorWithRetry title="Das Postfach konnte nicht geladen werden"
                           onRetry={() => { setFailed(false); setAttempt(attempt + 1) }} />
  }
  if (account === null) return <Loading label="Postfach wird geladen" />
  return <MailboxForm initial={account} />
}

/** The mailbox account as a form: server, port (993 when empty), user name, the password with
 * its eye button, the limit of mails per check and, after „Verbinden und Ordner laden“, the
 * folder choice. `initial` is the stored account. Without a key (`key_configured` false) the
 * password field and the connect action are disabled, each with its info icon. The password is
 * never filled in: a stored one shows as dots in the placeholder, and a field left empty keeps
 * it. Connecting stores the account (`PUT /mailbox`) and then lists the folders
 * (`POST /mailbox/folders`); „Speichern“ stores the account with the folder choice and the limit.
 * The typed password is dropped after every request. */
function MailboxForm({ initial }: { initial: MailboxAccount }) {
  const [stored, setStored] = useState(initial)
  const [host, setHost] = useState(initial.host)
  const [port, setPort] = useState(initial.configured ? String(initial.port) : '')
  const [user, setUser] = useState(initial.user)
  const [password, setPassword] = useState('')
  const [shown, setShown] = useState(false)
  const [limit, setLimit] = useState(String(initial.max_mails))
  const [all, setAll] = useState(initial.folders.names === undefined)
  const [names, setNames] = useState<Set<string>>(new Set(initial.folders.names ?? []))
  const [folders, setFolders] = useState<MailboxFolder[] | null>(null)
  const [busy, setBusy] = useState<'connect' | 'save' | null>(null)
  const [problems, setProblems] = useState<{ account?: string; port?: string; limit?: string; folders?: string }>({})
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const ids = { password: useId(), whyPassword: useId(), whyConnect: useId(), limit: useId(), port: useId() }

  const keyMissing = !stored.key_configured
  const passwordStored = stored.password === 'stored' && !keyMissing

  /** The request body, or `null` after showing what is wrong. `withFolders` adds the folder choice. */
  function read(withFolders: boolean): MailboxBody | null {
    const found: typeof problems = {}
    const portNumber = port.trim() === '' ? 993 : Number(port)
    const limitNumber = limit.trim() === '' ? NaN : Number(limit)
    if (!host.trim() || !user.trim()) found.account = 'Gib Server und Benutzername an.'
    if (!Number.isInteger(portNumber) || portNumber < 1 || portNumber > 65535) found.port = PORT_PROBLEM
    if (!Number.isInteger(limitNumber) || limitNumber < 1 || limitNumber > 1000) found.limit = LIMIT_PROBLEM
    const chosen = folders?.filter((folder) => names.has(folder.name)).map((folder) => folder.name) ?? []
    if (withFolders && folders && !all && chosen.length === 0) found.folders = 'Wähle mindestens einen Ordner.'
    setProblems(found)
    if (Object.keys(found).length > 0) return null
    return {
      host: host.trim(), port: portNumber, user: user.trim(), max_mails: limitNumber,
      ...(password ? { password } : {}),
      ...(withFolders && folders ? { folders: all ? { all: true as const } : { names: chosen } } : {}),
    }
  }

  async function send(connect: boolean, event?: FormEvent) {
    event?.preventDefault()
    if (busy) return
    setError('')
    setStatus('')
    const body = read(!connect)
    if (!body) return
    setBusy(connect ? 'connect' : 'save')
    try {
      const answer = await api<MailboxAccount>('/mailbox', { method: 'PUT', json: body })
      setStored(answer)
      setPassword('')
      if (!connect) {
        setStatus('Gespeichert.')
        return
      }
      try {
        const listed = await api<{ folders: MailboxFolder[] }>('/mailbox/folders', { method: 'POST' })
        setFolders(listed.folders)
        setStatus(`Verbunden. ${listed.folders.length === 1 ? '1 Ordner' : `${listed.folders.length} Ordner`} gefunden.`)
      } catch (failure) {
        setFolders(null)
        setError(connectFailure(failure))
      }
    } catch (failure) {
      setError(saveFailure(failure))
    } finally {
      setBusy(null)
    }
  }

  const describedBy = [keyMissing && ids.whyPassword, stored.password === 'unreadable' && !keyMissing && ids.password]
    .filter(Boolean).join(' ') || undefined
  return (
    <form onSubmit={(event) => send(false, event)} noValidate className="flex flex-col gap-4">
      <p className="text-[15px] text-muted-foreground">
        Nimm ein App-Passwort, das dein Anbieter getrennt widerrufen kann, statt des Passworts deines Kontos.
      </p>
      <div className="flex flex-wrap gap-4">
        <div className="flex min-w-0 flex-[3_1_14rem] flex-col gap-1">
          <label htmlFor="mailbox-host" className="text-sm font-bold">Server</label>
          <Input id="mailbox-host" value={host} autoComplete="off" placeholder="imap.example.org"
                 onChange={(event) => setHost(event.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="mailbox-port" className="text-sm font-bold">Port</label>
          <Input id="mailbox-port" type="number" min={1} max={65535} value={port} placeholder="993"
                 aria-describedby={problems.port ? ids.port : undefined} className="w-28 tabular-nums"
                 onChange={(event) => setPort(event.target.value)} />
          {problems.port && <p id={ids.port} role="alert" className="max-w-28 text-sm text-danger">{problems.port}</p>}
        </div>
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="mailbox-user" className="text-sm font-bold">Benutzername</label>
        <Input id="mailbox-user" value={user} autoComplete="off" onChange={(event) => setUser(event.target.value)} />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="mailbox-password" className="text-sm font-bold">
          {passwordStored ? 'Passwort · gespeichert' : 'Passwort'}
        </label>
        <div className="flex items-center gap-1">
          <div className="relative flex-1">
            <Input id="mailbox-password" type={shown ? 'text' : 'password'} value={password} disabled={keyMissing}
                   autoComplete="new-password" placeholder={passwordStored ? DOTS : ''} aria-describedby={describedBy}
                   className="pr-12" onChange={(event) => setPassword(event.target.value)} />
            <button type="button" aria-label="Passwort anzeigen" aria-pressed={shown} disabled={keyMissing}
                    onClick={() => setShown(!shown)}
                    className="absolute top-0 right-0 inline-flex size-11 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground disabled:opacity-50">
              {shown ? <EyeOff className="size-5" aria-hidden="true" /> : <Eye className="size-5" aria-hidden="true" />}
            </button>
          </div>
          {keyMissing && (
            <WhyDisabled id={ids.whyPassword} label="Warum ist das Passwortfeld gesperrt?" reason={mailboxReason('no key')} />
          )}
        </div>
        {stored.password === 'unreadable' && !keyMissing && (
          <p id={ids.password} className="text-sm text-muted-foreground">{mailboxReason('password unreadable')}</p>
        )}
        {stored.password === 'missing' && stored.configured && !keyMissing && (
          <p id={ids.password} className="text-sm text-muted-foreground">Kein Passwort gespeichert. Gib es ein, damit sich die App anmelden kann.</p>
        )}
      </div>
      {problems.account && <p role="alert" className="text-danger">{problems.account}</p>}
      <div className="flex flex-wrap items-center gap-1">
        <Button type="button" disabled={keyMissing || busy !== null} aria-describedby={keyMissing ? ids.whyConnect : undefined}
                onClick={() => send(true)}>
          {busy === 'connect' ? 'Verbindung wird aufgebaut…' : 'Verbinden und Ordner laden'}
        </Button>
        {keyMissing && <WhyDisabled id={ids.whyConnect} label="Warum ist Verbinden nicht möglich?" reason={mailboxReason('no key')} />}
      </div>
      {error && <p role="alert" className="rounded-xl border border-danger bg-danger-soft px-4 py-3">{error}</p>}
      {status && <p role="status" className="font-bold">{status}</p>}

      {folders && (
        <fieldset className="flex flex-col gap-2.5 rounded-[10px] border p-4">
          <legend className="px-1 font-bold">Ordner</legend>
          <p className="text-[15px]">Wähle nur Ordner, in denen ausschließlich Job-Alert-Mails liegen.</p>
          <div className="flex items-start gap-2.5">
            <input type="radio" id="folders-all" name="folder-mode" checked={all} aria-describedby="folders-all-hint"
                   onChange={() => setAll(true)} className="mt-1 size-5 flex-none accent-primary" />
            <div className="flex flex-col">
              <label htmlFor="folders-all" className="font-bold">Alle Ordner</label>
              <span id="folders-all-hint" className="text-sm text-muted-foreground">
                Auch Ordner, die später entstehen. Systemordner wie Papierkorb und Spam bleiben ausgenommen.
              </span>
            </div>
          </div>
          <div className="flex items-start gap-2.5">
            <input type="radio" id="folders-some" name="folder-mode" checked={!all}
                   onChange={() => setAll(false)} className="mt-1 size-5 flex-none accent-primary" />
            <label htmlFor="folders-some" className="font-bold">Nur diese Ordner</label>
          </div>
          {!all && (
            <ul aria-label="Ordner des Postfachs" className="ml-7 flex flex-col gap-1">
              {folders.map((folder, index) => (
                <li key={folder.name} className="flex items-center gap-2.5">
                  <input type="checkbox" id={`folder-${index}`} checked={names.has(folder.name)}
                         onChange={() => setNames((now) => {
                           const next = new Set(now)
                           if (!next.delete(folder.name)) next.add(folder.name)
                           return next
                         })} className="size-5 flex-none accent-primary" />
                  <label htmlFor={`folder-${index}`}>
                    {folder.name}
                    {folder.system && <span className="ml-2 rounded-md bg-muted px-1.5 py-0.5 text-sm text-muted-foreground">Systemordner</span>}
                  </label>
                </li>
              ))}
            </ul>
          )}
          {problems.folders && <p role="alert" className="text-danger">{problems.folders}</p>}
        </fieldset>
      )}

      <div className="flex flex-col gap-1">
        <label htmlFor="mailbox-limit" className="text-sm font-bold">Höchstens Mails pro Prüfung</label>
        <Input id="mailbox-limit" type="number" min={1} max={1000} value={limit} className="w-28 tabular-nums"
               aria-describedby={problems.limit ? ids.limit : undefined}
               onChange={(event) => setLimit(event.target.value)} />
        {problems.limit && <p id={ids.limit} role="alert" className="text-sm text-danger">{problems.limit}</p>}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" variant="outline" disabled={busy !== null}>
          {busy === 'save' ? 'Wird gespeichert…' : 'Speichern'}
        </Button>
      </div>
    </form>
  )
}
