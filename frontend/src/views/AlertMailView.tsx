import { useEffect, useId, useState, type ClipboardEvent, type ReactNode } from 'react'
import { Check, CircleAlert, Clock, Copy, Info, LoaderCircle, Lock, ShieldAlert, ShieldCheck, ShieldOff } from 'lucide-react'
import {
  api, ApiError, type AlertEntry, type AlertPreview, type AlertRunEntry, type AlertRunState, type PostingPageData,
} from '@/api'
import { AttemptList } from '@/components/attempts'
import { Badge } from '@/components/posting'
import { ErrorWithRetry } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { POLL_FAILURES, POLL_MS } from '@/views/PoolView'

const RUN_KEY = 'jobadvaisor.alert-run'
const BASE_KEY = 'jobadvaisor.alert-run-base'

/** The alert run's ID kept across a reload, so the view attaches to the run again. Storage may
 * be blocked, so every access is guarded. */
const storedRun = {
  get: () => {
    try {
      return sessionStorage.getItem(RUN_KEY)
    } catch {
      return null
    }
  },
  /** For a run of one stored-anyway entry: the original run and the row it replaces. */
  getBase: (): { id: string; index: number } | null => {
    try {
      return JSON.parse(sessionStorage.getItem(BASE_KEY) ?? 'null')
    } catch {
      return null
    }
  },
  /** Keeps run `id` (`null` drops it), and with `base` the original run its single row belongs to. */
  set: (id: string | null, base?: { id: string; index: number }) => {
    try {
      if (id) sessionStorage.setItem(RUN_KEY, id)
      else sessionStorage.removeItem(RUN_KEY)
      if (id && base) sessionStorage.setItem(BASE_KEY, JSON.stringify(base))
      else sessionStorage.removeItem(BASE_KEY)
    } catch { /* storage blocked: a reload simply does not resume */ }
  },
}

/** What each fixed rule (`read_by`) is called in the sentence "Gelesen über …". */
const RULES: Record<string, string> = {
  linkedin: 'LinkedIn',
  bundesagentur: 'die Jobbörse der Bundesagentur',
  career_site: 'Karriereseiten mit /job/-Links',
}

/** The sentence that says which finder read the mail. */
function readBySentence(readBy: string[]): string {
  if (readBy.includes('model')) return 'Gelesen von einem Modell nach der Inhaltsprüfung.'
  const rules = readBy.map((name) => RULES[name] ?? name)
  return `Gelesen über ${rules.length === 1 ? 'die feste Regel' : 'die festen Regeln'} für ${rules.join(' und ')}.`
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

/** German text for a failed preview, by the API's error; the API's own detail is English and
 * stays out. */
function readFailure(error: unknown): string {
  if (!(error instanceof ApiError) || error.status === 0) return 'Der Server ist nicht erreichbar. Deine Mail bleibt eingefügt.'
  if (error.error === 'screening failed') {
    return 'Die Inhaltsprüfung hat nicht geantwortet, deshalb hat kein Modell die Mail gelesen. Deine Mail bleibt eingefügt.'
  }
  if (error.error === 'finder failed') return 'Das Modell hat nicht geantwortet. Deine Mail bleibt eingefügt.'
  return 'Die Mail wurde nicht angenommen, vielleicht ist sie zu groß. Füge die Anzeigen einzeln als Link oder Text ein.'
}

/** An entry the pick list selects at first: a new posting on a host the app fetches. */
const preselected = (entry: AlertEntry) => !entry.duplicate && !entry.login_walled && !entry.ambiguous

const PANEL = 'flex flex-col gap-3.5 rounded-xl border bg-card p-5 shadow-card'
const ROW = 'flex items-start gap-3 rounded-[10px] border px-4 py-3'
/** For a small button inside a row: its label wraps instead of overflowing the row, and on a
 * phone it is as wide as the row and 44px high. */
const ROW_BUTTON = 'h-auto min-h-8 whitespace-normal text-center max-sm:min-h-11 max-sm:w-full'

/** The source "Alert-Mail" of the intake view: paste a job alert mail (the clipboard's HTML part
 * is kept, so the links behind titles survive), pick from the postings found in it
 * (`POST /alert-mails/preview`, nothing fetched yet), add the chosen ones in a background run
 * (`POST /alert-mails/runs`, polled) and see each entry's outcome. The run's ID stays in
 * `sessionStorage`, so a reload, or leaving the source and coming back, shows the run again; a
 * 409 attaches to the computing run; a 404 means the server forgot it. `onUrl`, `onText` and
 * `onPdf` switch the intake view to the other sources, for what the mail could not deliver. */
export function AlertMailView({ onUrl, onText, onPdf }: { onUrl: () => void; onText: () => void; onPdf: () => void }) {
  const [text, setText] = useState('')
  /** The clipboard's HTML part of the last paste; null after typing into an empty field, a plain paste or a clear. */
  const [html, setHtml] = useState<string | null>(null)
  const [finding, setFinding] = useState(false)
  const [readError, setReadError] = useState('')
  const [answer, setAnswer] = useState<AlertPreview | null>(null)
  /** Whether screening is on, as the last answer said; null before the first one. */
  const [screening, setScreening] = useState<boolean | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState(false)
  const [runId, setRunId] = useState<string | null>(storedRun.get)
  const [progress, setProgress] = useState<AlertRunState | null>(null)
  const [pollFailed, setPollFailed] = useState(false)
  /** The server no longer knows the run (it restarted). */
  const [gone, setGone] = useState(false)
  /** A text duplicate stored anyway: the report it belongs to and its row, whose outcome the run of that one entry replaces. */
  const [forced, setForced] = useState<{ index: number; base: AlertRunEntry[] } | null>(null)

  const running = runId !== null && (progress === null || progress.status === 'running')

  useEffect(() => {
    // After a reload: put the single row of a stored-anyway run back into its original report.
    const base = storedRun.getBase()
    if (!base) return
    let stale = false
    api<AlertRunState>(`/alert-mails/runs/${base.id}`).then((original) => {
      if (!stale) setForced({ index: base.index, base: original.entries })
    }, () => {})
    return () => { stale = true }
  }, [])

  useEffect(() => {
    if (!runId || !running || pollFailed) return
    let failures = 0
    let stale = false
    const poll = () => api<AlertRunState>(`/alert-mails/runs/${runId}`).then((next) => {
      if (stale) return
      failures = 0
      setProgress(next)
    }, (error) => {
      if (stale) return
      if (error instanceof ApiError && error.status === 404) {
        storedRun.set(null)
        setRunId(null)
        setProgress(null)
        setForced(null)
        setGone(true)
      } else if (++failures >= POLL_FAILURES) {
        clearInterval(timer)
        setPollFailed(true)
      }
    })
    const timer = setInterval(poll, POLL_MS)
    poll() // at once, so a reload does not show a finished run as running for an interval
    return () => {
      stale = true
      clearInterval(timer)
    }
  }, [runId, running, pollFailed])

  /** Back to an empty paste field: the mail, the pick list and the run are dropped. */
  function startOver() {
    storedRun.set(null)
    setText('')
    setHtml(null)
    setAnswer(null)
    setReadError('')
    setRunId(null)
    setProgress(null)
    setForced(null)
    setGone(false)
    setStartError(false)
  }

  function onPaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const plain = event.clipboardData.getData('text/plain')
    const markup = event.clipboardData.getData('text/html')
    if (!plain && !markup) return
    event.preventDefault() // a paste replaces both parts, it does not insert at the caret
    setText(plain)
    setHtml(markup || null)
  }

  async function find() {
    if (finding || (!text.trim() && !(html ?? '').trim())) return
    setFinding(true)
    setReadError('')
    try {
      const next = await api<AlertPreview>('/alert-mails/preview', { method: 'POST', json: { html, text } })
      setScreening(next.screening)
      setSelected(new Set(next.entries.flatMap((entry, index) => preselected(entry) ? [index] : [])))
      setAnswer(next)
    } catch (error) {
      setReadError(readFailure(error))
    } finally {
      setFinding(false)
    }
  }

  /** Starts a run of `entries`, as the first run of the mail or, with `row`, a run of one text duplicate stored anyway. */
  async function start(entries: { url: string; title: string; force: boolean }[], row?: { index: number; base: AlertRunEntry[] }) {
    if (starting || running) return
    setStarting(true)
    setStartError(false)
    try {
      const { run_id: id } = await api<{ run_id: string }>('/alert-mails/runs', { method: 'POST', json: { entries } })
      storedRun.set(id, row && runId ? { id: storedRun.getBase()?.id ?? runId, index: row.index } : undefined)
      setForced(row ?? null)
      setPollFailed(false)
      setProgress({ run_id: id, status: 'running', error: null, total: entries.length, done: 0,
                    entries: entries.map((entry) => ({ url: entry.url, title: entry.title, state: row ? 'running' : 'waiting' })) })
      setRunId(id)
    } catch (error) {
      if (error instanceof ApiError && error.status === 409 && typeof error.body.run_id === 'string') {
        storedRun.set(error.body.run_id)
        setProgress(null)
        setForced(null)
        setPollFailed(false)
        setRunId(error.body.run_id)
      } else {
        setStartError(true)
      }
    } finally {
      setStarting(false)
    }
  }

  const chosen = answer ? answer.entries.flatMap((entry, index) => selected.has(index) ? [entry] : []) : []
  const screeningLine = screening === null ? null : screening
    ? { Icon: ShieldCheck, lead: 'Inhaltsprüfung ist an.', rest: 'Mails von Absendern ohne feste Regel liest ein Modell erst nach der Prüfung.' }
    : { Icon: ShieldOff, lead: 'Inhaltsprüfung ist aus.', rest: 'Gelesen werden nur Mails von LinkedIn, der Jobbörse der Bundesagentur und Karriereseiten mit /job/-Links.' }

  if (gone) {
    return (
      <Notice title="Lauf nicht mehr bekannt" Icon={Info}
              text="Die App wurde neu gestartet, der Stand dieses Laufs ist weg. Schon gespeicherte Anzeigen bleiben gespeichert. Füge die Mail noch einmal ein: Gespeicherte Stellen sind dann markiert, die übrigen kannst du erneut hinzufügen.">
        <Button type="button" onClick={startOver} className="self-start">Mail noch einmal einfügen</Button>
      </Notice>
    )
  }

  if (runId) {
    const shown = forced
      ? forced.base.map((entry, index) => index === forced.index ? (progress?.entries[0] ?? { ...entry, state: 'running' as const }) : entry)
      : progress?.entries
    return (
      <div className="flex flex-col gap-6">
        {startError && <StartFailed />}
        {pollFailed ? (
          <ErrorWithRetry title="Der Stand des Laufs ist gerade nicht abrufbar"
                          detail="Der Server antwortet nicht. Der Lauf rechnet vielleicht weiter."
                          onRetry={() => setPollFailed(false)} />
        ) : shown === undefined ? (
          <div role="status" className="flex items-center gap-3 py-4 text-muted-foreground">
            <LoaderCircle className="size-5 motion-safe:animate-spin" aria-hidden="true" />
            <span>Lauf wird geladen</span>
          </div>
        ) : (
          <RunPanel entries={shown} status={progress?.status ?? 'running'} start={start}
                    onText={onText} onPdf={onPdf} onOver={startOver} />
        )}
      </div>
    )
  }

  if (answer?.held) {
    return (
      <Notice title="Mail von der Inhaltsprüfung zurückgehalten" Icon={ShieldAlert} danger
              text="Die Mail enthält Text, der sich an ein KI-System richtet. Kein Modell hat sie gelesen, es wurde keine Stelle übernommen. Vertraust du der Mail, füge ihre Anzeigen einzeln ein.">
        <Button type="button" variant="outline" onClick={startOver} className="self-start">Andere Mail einfügen</Button>
      </Notice>
    )
  }

  if (answer && answer.entries.length === 0 && answer.model_skipped === 'screening off') {
    return (
      <Notice title="Nur bekannte Absender, solange die Inhaltsprüfung aus ist" Icon={ShieldOff}
              text="Für den Absender dieser Mail gibt es keine feste Regel. Ohne Inhaltsprüfung liest kein Modell die Mail, damit keine darin versteckte Anweisung ein Modell erreicht. Feste Regeln gibt es für LinkedIn, die Jobbörse der Bundesagentur und Karriereseiten, deren Links auf /job/ zeigen. Füge die Anzeigen dieser Mail einzeln als Link oder Text ein.">
        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={onUrl}>Link einfügen</Button>
          <Button type="button" variant="outline" onClick={startOver}>Andere Mail einfügen</Button>
        </div>
      </Notice>
    )
  }

  if (answer && answer.entries.length === 0) {
    return (
      <Notice title="Keine Stellen gefunden" Icon={Info}
              text="In dieser Mail wurde kein Link zu einer Stellenanzeige gefunden. Prüfe, ob du die ganze Mail kopiert hast, oder füge die Anzeigen einzeln als Link oder Text ein.">
        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={onUrl}>Link einfügen</Button>
          <Button type="button" variant="outline" onClick={onText}>Text einfügen</Button>
          <Button type="button" variant="outline" onClick={startOver}>Andere Mail einfügen</Button>
        </div>
      </Notice>
    )
  }

  if (answer) {
    const entries = answer.entries
    return (
      <div className="flex flex-col gap-6">
        {startError && <StartFailed />}
        <section aria-labelledby="alert-found" className={PANEL}>
          <div>
            <h2 id="alert-found" className="text-lg font-bold">
              {plural(entries.length, 'Stelle', 'Stellen')} in der Mail gefunden
            </h2>
            <p className="mt-0.5 text-[15px] text-muted-foreground">
              {readBySentence(answer.read_by)} Neue Stellen sind ausgewählt, nichts wurde bisher abgerufen.
            </p>
          </div>
          {answer.unread_hosts.length > 0 && (
            <Note>
              <strong>Nicht gelesen:</strong>{' '}
              {answer.unread_hosts.map((item) => `${item.host} (${plural(item.links, 'Link', 'Links')})`).join(', ')}.
              {' '}Diese Links passen zu keiner festen Regel.{' '}
              {answer.screening ? 'Füge diese Mail einzeln ein, dann liest ein Modell sie.' : 'Füge diese Mail einzeln ein.'}
            </Note>
          )}
          {answer.truncated && <Note>Die Mail enthält mehr als 100 Stellen. Nur die ersten 100 sind aufgeführt.</Note>}
          <ul aria-label="Gefundene Stellen" className="flex flex-col gap-2.5">
            {entries.map((entry, index) => (
              <PickRow key={index} entry={entry} index={index} checked={selected.has(index)} onText={onText}
                       onToggle={() => setSelected((now) => {
                         const next = new Set(now)
                         if (!next.delete(index)) next.add(index)
                         return next
                       })} />
            ))}
          </ul>
          <div className="flex flex-col gap-2 border-t pt-3.5 sm:flex-row sm:flex-wrap sm:items-center">
            <Button type="button" disabled={chosen.length === 0 || starting}
                    onClick={() => start(chosen.map((entry) => ({ url: entry.url, title: entry.title, force: false })))}>
              {plural(chosen.length, 'Anzeige', 'Anzeigen')} hinzufügen
            </Button>
            <Button type="button" variant="outline" onClick={startOver}>Andere Mail einfügen</Button>
            <span className="text-sm text-muted-foreground">
              Die Anzeigen werden nacheinander abgerufen. Du kannst die Seite verlassen, der Lauf geht weiter.
            </span>
          </div>
          {screeningLine && <ScreeningLine {...screeningLine} />}
        </section>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <section className={PANEL}>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="alert-mail" className="font-bold">Alert-Mail</label>
          <Textarea id="alert-mail" rows={8} value={text} disabled={finding} aria-describedby="alert-mail-hint"
                    placeholder="Öffne die Mail, markiere alles, kopiere es und füge es hier ein."
                    onPaste={onPaste}
                    onChange={(event) => {
                      setText(event.target.value)
                      if (!event.target.value) setHtml(null)
                    }} />
          <span id="alert-mail-hint" className="text-[13px] text-muted-foreground">
            Die Links hinter Titeln und Buttons bleiben beim Einfügen erhalten. Es wird noch nichts abgerufen: Du siehst
            zuerst, welche Stellen in der Mail stehen.
          </span>
        </div>
        <Button type="button" disabled={finding} onClick={find} className="self-start">
          {finding ? 'Stellen werden gesucht…' : 'Stellen finden'}
        </Button>
        {finding && (
          <div role="status" className="flex items-center gap-3 rounded-[10px] bg-muted px-4 py-3.5">
            <LoaderCircle className="size-5 flex-none motion-safe:animate-spin" aria-hidden="true" />
            <span>
              <strong>Stellen werden gesucht.</strong> Bekannte Absender sind in einem Augenblick gelesen. Bei anderen
              liest ein Modell die Mail, das dauert einige Sekunden.
            </span>
          </div>
        )}
        {!finding && screeningLine && <ScreeningLine {...screeningLine} />}
      </section>
      {readError && (
        <section role="alert" className="flex flex-col gap-3.5 rounded-xl border border-danger bg-danger-soft p-5">
          <div className="flex items-start gap-2.5">
            <CircleAlert className="mt-0.5 size-[22px] flex-none text-danger" aria-hidden="true" />
            <div>
              <h2 className="text-lg font-bold">Mail konnte nicht gelesen werden</h2>
              <p className="mt-1">{readError}</p>
            </div>
          </div>
          <Button type="button" variant="outline" onClick={find} className="self-start">Erneut versuchen</Button>
        </section>
      )}
    </div>
  )
}

/** A line that says whether content screening is on, with what that means for unknown senders. */
function ScreeningLine({ Icon, lead, rest }: { Icon: typeof ShieldCheck; lead: string; rest: string }) {
  return (
    <p className="flex items-start gap-2.5 text-[15px]">
      <Icon className="mt-0.5 size-[18px] flex-none" aria-hidden="true" />
      <span><strong>{lead}</strong> {rest}</span>
    </p>
  )
}

/** A hint above the pick list, in the muted box of the intake view. */
function Note({ children }: { children: ReactNode }) {
  return (
    <div role="note" className="flex items-start gap-2.5 rounded-[10px] bg-muted px-3.5 py-3 text-[15px]">
      <Info className="mt-0.5 size-[18px] flex-none" aria-hidden="true" />
      <span>{children}</span>
    </div>
  )
}

/** A panel with a heading and a sentence for a state without a list: nothing found, held, lost.
 * `danger` makes it an alert; `children` are its actions. */
function Notice({ title, text, Icon, danger = false, children }: {
  title: string
  text: string
  Icon: typeof Info
  danger?: boolean
  children: ReactNode
}) {
  return (
    <section role={danger ? 'alert' : undefined} aria-labelledby="alert-notice"
             className={cn(PANEL, danger && 'border-danger bg-danger-soft')}>
      <div className="flex items-start gap-2.5">
        <Icon className={cn('mt-0.5 size-[22px] flex-none', danger && 'text-danger')} aria-hidden="true" />
        <div>
          <h2 id="alert-notice" className="text-lg font-bold">{title}</h2>
          <p className="mt-1">{text}</p>
        </div>
      </div>
      {children}
    </section>
  )
}

function StartFailed() {
  return (
    <p role="alert" className="rounded-xl border border-danger bg-danger-soft px-4 py-3">
      Der Lauf konnte nicht gestartet werden. Ist der Server erreichbar? Die Auswahl bleibt, du kannst es noch einmal versuchen.
    </p>
  )
}

/** One entry of the pick list: a checkbox named by the title, the cleaned link, and what keeps
 * the entry from being picked or preselected. */
function PickRow({ entry, index, checked, onToggle, onText }: {
  entry: AlertEntry
  index: number
  checked: boolean
  onToggle: () => void
  onText: () => void
}) {
  const locked = Boolean(entry.duplicate) || entry.ambiguous
  const why = `alert-entry-${index}-why`
  return (
    <li className={cn(ROW, locked && 'bg-background')}>
      <input type="checkbox" id={`alert-entry-${index}`} checked={checked && !locked} disabled={locked}
             aria-describedby={locked || entry.login_walled ? why : undefined} onChange={onToggle}
             className="mt-0.5 size-[22px] flex-none accent-primary disabled:cursor-not-allowed disabled:opacity-50" />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <label htmlFor={`alert-entry-${index}`} className="font-bold">{entry.title || entry.url}</label>
        <span className="font-mono text-sm break-all text-muted-foreground">{entry.url}</span>
        {entry.duplicate && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <Badge id={why} className="bg-muted text-foreground">Schon gespeichert</Badge>
            <a href={`#/anzeigen/${encodeURIComponent(entry.duplicate.posting_id)}`}
               className="text-[15px] text-primary underline">Gespeicherte Anzeige ansehen</a>
          </div>
        )}
        {entry.login_walled && !entry.duplicate && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <Badge className="bg-muted text-foreground">
              <Lock className="size-4" aria-hidden="true" />Seite mit Login-Pflicht
            </Badge>
            <span id={why} className="text-sm text-muted-foreground">
              Nicht vorausgewählt: Die Seite selbst wird nicht abgerufen, die Anzeige wird über eine Websuche gesucht.
            </span>
          </div>
        )}
        {entry.ambiguous && !entry.duplicate && (
          <>
            <Badge className="self-start bg-muted text-foreground">Link nicht eindeutig</Badge>
            <span id={why} className="text-sm text-muted-foreground">
              Mehrere Stellen der Mail führen über dieselbe Adresse. Über diesen Link lässt sich die Anzeige nicht
              hinzufügen. Füge ihren Text ein.
            </span>
            <Button type="button" size="sm" variant="outline" onClick={onText}
                    className={cn(ROW_BUTTON, 'sm:self-start')}>Text einfügen</Button>
          </>
        )}
      </div>
    </li>
  )
}

/** The run: "x von y erledigt", a bar while it computes, one row per entry, and at the end the
 * summary or, for a run that crashed, the notice. `entries` are the rows to show; `status` is
 * the run's. `start` runs a text duplicate again with `force` (`onOver` starts a new mail). */
function RunPanel({ entries, status, start, onText, onPdf, onOver }: {
  entries: AlertRunEntry[]
  status: AlertRunState['status']
  start: (entries: { url: string; title: string; force: boolean }[], row: { index: number; base: AlertRunEntry[] }) => void
  onText: () => void
  onPdf: () => void
  onOver: () => void
}) {
  const ended = (entry: AlertRunEntry) => ['stored', 'duplicate', 'failed'].includes(entry.state)
  const finished = entries.filter(ended).length
  const count = (state: AlertRunEntry['state']) => entries.filter((entry) => entry.state === state).length
  const summary = [
    count('stored') > 0 && `${count('stored')} hinzugefügt`,
    count('duplicate') > 0 && `${count('duplicate')} schon gespeichert`,
    count('failed') > 0 && `${count('failed')} nicht gelesen`,
  ].filter(Boolean).join(', ')
  return (
    <>
      <div role="status" className="sr-only">
        {status === 'running' && 'Der Lauf läuft.'}
        {status === 'done' && 'Der Lauf ist fertig.'}
      </div>
      {status === 'failed' && (
        <section role="alert" aria-labelledby="alert-crash" className={cn(PANEL, 'border-danger bg-danger-soft')}>
          <div className="flex items-start gap-2.5">
            <CircleAlert className="mt-0.5 size-[22px] flex-none text-danger" aria-hidden="true" />
            <div>
              <h2 id="alert-crash" className="text-lg font-bold">Der Lauf ist abgebrochen</h2>
              <p className="mt-1">
                Ein Fehler hat ihn nach {finished} von {entries.length} Anzeigen beendet. Was bis dahin gespeichert ist,
                bleibt gespeichert. Füge die Mail noch einmal ein: Gespeicherte Stellen sind dann markiert.
              </p>
            </div>
          </div>
          <Button type="button" variant="outline" onClick={onOver} className="self-start">Andere Mail einfügen</Button>
        </section>
      )}
      <section aria-labelledby="alert-run" className={PANEL}>
        <div>
          <h2 id="alert-run" className="text-lg font-bold">{finished} von {entries.length} erledigt</h2>
          {status === 'running' && (
            <p className="mt-0.5 text-[15px] text-muted-foreground">
              Die Anzeigen werden nacheinander abgerufen. Eine Anzeige, die nicht klappt, hält die anderen nicht auf.
            </p>
          )}
          {status === 'done' && summary && (
            <p className="mt-0.5 text-[15px] text-muted-foreground">
              {summary}.{count('stored') > 0 && ' Prüfe Titel, Firma und Ort der neuen Anzeigen auf ihren Seiten.'}
            </p>
          )}
        </div>
        {status === 'running' && (
          <progress aria-label="Fortschritt" className="h-2 w-full accent-primary" value={finished} max={entries.length} />
        )}
        <ul aria-label="Stand je Anzeige" className="flex flex-col gap-2.5">
          {entries.map((entry, index) => (
            <RunRow key={index} entry={entry} ended={status !== 'running'}
                    onText={onText} onPdf={onPdf}
                    onForce={() => start([{ url: entry.url, title: entry.title, force: true }], { index, base: entries })} />
          ))}
        </ul>
        {status !== 'running' && (
          <Button type="button" variant="outline" onClick={onOver} className="self-start">Andere Mail einfügen</Button>
        )}
      </section>
    </>
  )
}

/** The title and company of a stored posting, read once; null until they arrive or when they cannot be read. */
function useStoredPosting(id: string | undefined): { title: string; company: string } | null {
  const [posting, setPosting] = useState<{ title: string; company: string } | null>(null)
  useEffect(() => {
    if (!id) return
    let stale = false
    api<PostingPageData>(`/postings/${encodeURIComponent(id)}`)
      .then((page) => { if (!stale) setPosting({ title: page.posting.title, company: page.posting.company }) }, () => {})
    return () => { stale = true }
  }, [id])
  return posting
}

const DUPLICATE_BY = {
  url: 'Schon gespeichert',
  text: 'Gleicher Text wie eine gespeicherte Anzeige',
  similar_text: 'Ähnlicher Text wie eine gespeicherte Anzeige',
}

/** The state word of a run row, with its icon. */
function Label({ icon, text, tone }: { icon: ReactNode; text: string; tone?: string }) {
  return <span className={cn('inline-flex items-center gap-1.5 font-bold', tone)}>{icon}{text}</span>
}

/** One row of a run: the entry's state and what follows from it. A text duplicate offers to be
 * stored anyway once the run is over (`ended`), after a confirmation that names the matching posting. */
function RunRow({ entry, ended, onText, onPdf, onForce }: {
  entry: AlertRunEntry
  ended: boolean
  onText: () => void
  onPdf: () => void
  onForce: () => void
}) {
  const [confirming, setConfirming] = useState(false)
  const confirmId = useId()
  const byText = entry.state === 'duplicate' && entry.duplicate_by !== 'url'
  const match = useStoredPosting(byText ? entry.posting_id : undefined)
  const postingHref = `#/anzeigen/${encodeURIComponent(entry.posting_id ?? '')}`
  const matchName = match ? `„${match.title}“ bei ${match.company}` : 'einer gespeicherten Anzeige'
  const ICON = 'size-4'
  return (
    <li className={cn(ROW, entry.state === 'failed' && 'border-danger bg-danger-soft',
                      entry.state === 'waiting' && 'bg-background')}>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        {entry.state === 'stored' && <Label tone="text-success" text="Hinzugefügt"
                                            icon={<Check className={ICON} strokeWidth={3} aria-hidden="true" />} />}
        {entry.state === 'duplicate' && <Label text={DUPLICATE_BY[entry.duplicate_by ?? 'url']}
                                               icon={<Copy className={ICON} aria-hidden="true" />} />}
        {entry.state === 'failed' && <Label tone="text-danger" text="Nicht gelesen"
                                            icon={<CircleAlert className={ICON} aria-hidden="true" />} />}
        {entry.state === 'running' && <Label text="wird abgerufen…"
                                             icon={<LoaderCircle className={cn(ICON, 'motion-safe:animate-spin')} aria-hidden="true" />} />}
        {entry.state === 'waiting' && <Label tone="text-muted-foreground" text={ended ? 'nicht gestartet' : 'wartet'}
                                             icon={<Clock className={ICON} aria-hidden="true" />} />}
        {entry.title && <span className="font-bold">{entry.title}</span>}
        <span className="font-mono text-sm break-all text-muted-foreground">{entry.url}</span>

        {entry.state === 'stored' && (
          <a href={postingHref} className="self-start text-[15px] text-primary underline">Anzeige ansehen</a>
        )}
        {entry.state === 'duplicate' && entry.duplicate_by === 'url' && (
          <p className="text-[15px]">
            Inzwischen über denselben Link gespeichert, es wurde nichts Neues angelegt.{' '}
            <a href={postingHref} className="text-primary underline">Gespeicherte Anzeige ansehen</a>
          </p>
        )}
        {byText && (
          <>
            <p className="text-[15px]">
              Der Link ist neu, aber der Anzeigentext {entry.duplicate_by === 'text' ? 'gleicht' : 'ähnelt'}{' '}
              <a href={postingHref} className="text-primary underline">{matchName}</a>. Es wurde nichts Neues angelegt.
            </p>
            {ended && !confirming && (
              <Button type="button" size="sm" variant="outline" onClick={() => setConfirming(true)}
                      className={cn(ROW_BUTTON, 'sm:self-start')}>
                Trotzdem als neue Anzeige speichern
              </Button>
            )}
            {ended && confirming && (
              <div role="group" aria-labelledby={confirmId}
                   className="flex flex-col gap-2.5 rounded-[10px] border border-primary bg-positive-soft px-3.5 py-3">
                <p id={confirmId}>
                  <strong>Als neue Anzeige speichern?</strong> Der Text {entry.duplicate_by === 'text' ? 'gleicht' : 'ähnelt'} {matchName}.
                  Die gespeicherte Anzeige bleibt, wie sie ist, und die Seite wird noch einmal abgerufen.
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button type="button" size="sm" onClick={onForce} className={ROW_BUTTON}>Ja, als neue Anzeige speichern</Button>
                  <Button type="button" size="sm" variant="outline" onClick={() => setConfirming(false)}
                          className={ROW_BUTTON}>Abbrechen</Button>
                </div>
              </div>
            )}
          </>
        )}
        {entry.state === 'failed' && (
          <>
            {entry.attempts && entry.attempts.length > 0 ? (
              <>
                <p className="text-[15px]">Diese Versuche wurden gemacht:</p>
                <AttemptList attempts={entry.attempts} className="text-[15px]" />
              </>
            ) : (
              <p className="text-[15px]">Diese Anzeige konnte nicht gelesen werden.</p>
            )}
            <p className="text-[15px]">Füge stattdessen den Text ein oder lade ein PDF hoch.</p>
            <div className="flex flex-wrap gap-2">
              <Button type="button" size="sm" onClick={onText} className={ROW_BUTTON}>Text einfügen</Button>
              <Button type="button" size="sm" variant="outline" onClick={onPdf} className={ROW_BUTTON}>PDF hochladen</Button>
            </div>
          </>
        )}
      </div>
    </li>
  )
}
