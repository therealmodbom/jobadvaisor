import { useState, type ClipboardEvent } from 'react'
import { CircleAlert, Info, LoaderCircle, ShieldAlert, ShieldCheck, ShieldOff } from 'lucide-react'
import { api, ApiError, type AlertPreview } from '@/api'
import { Note, Notice, PickRow, StartFailed } from '@/components/alert-pick'
import { AlertRunView } from '@/components/alert-run'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { PANEL, plural, preselected } from '@/lib/alert'
import { runStore, useAlertRun } from '@/lib/alert-run'

const store = runStore('jobadvaisor.alert-run', 'jobadvaisor.alert-run-base')

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


/** The source "Alert-Mail" of the intake view: paste a job alert mail (the clipboard's HTML part
 * is kept, so the links behind titles survive), pick from the postings found in it
 * (`POST /alert-mails/preview`, nothing fetched yet), add the chosen ones in a background run
 * (`POST /alert-mails/runs`, polled) and see each entry's outcome. The run's ID stays in
 * `sessionStorage`, so a reload, or leaving the source and coming back, shows the run again; a
 * 409 attaches to the computing run; a 404 means the server forgot it. `onUrl`, `onText` and
 * `onPdf` switch the intake view to the other sources, for what the mail could not deliver. */
export function AlertMailView({ onUrl, onText, onPdf }: { onUrl: () => void; onText: () => void; onPdf: () => void }) {
  const run = useAlertRun(store)
  const [text, setText] = useState('')
  /** The clipboard's HTML part of the last paste; null after typing into an empty field, a plain paste or a clear. */
  const [html, setHtml] = useState<string | null>(null)
  /** The plain text of the last paste, to tell an edit of it. */
  const [pasted, setPasted] = useState('')
  const [finding, setFinding] = useState(false)
  const [readError, setReadError] = useState('')
  const [answer, setAnswer] = useState<AlertPreview | null>(null)
  /** Whether screening is on, as the last answer said; null before the first one. */
  const [screening, setScreening] = useState<boolean | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())

  /** Back to an empty paste field: the mail, the pick list and the run are dropped. */
  function startOver() {
    run.clear()
    setText('')
    setHtml(null)
    setAnswer(null)
    setReadError('')
  }

  function onPaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const plain = event.clipboardData.getData('text/plain')
    const markup = event.clipboardData.getData('text/html')
    if (!plain && !markup) return
    event.preventDefault() // a paste replaces both parts, it does not insert at the caret
    setText(plain)
    setPasted(plain)
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

  const chosen = answer ? answer.entries.flatMap((entry, index) => selected.has(index) ? [entry] : []) : []
  const screeningLine = screening === null ? null : screening
    ? { Icon: ShieldCheck, lead: 'Inhaltsprüfung ist an.', rest: 'Mails von Absendern ohne feste Regel liest ein Modell erst nach der Prüfung.' }
    : { Icon: ShieldOff, lead: 'Inhaltsprüfung ist aus.', rest: 'Gelesen werden nur Mails von LinkedIn, der Jobbörse der Bundesagentur und Karriereseiten mit /job/-Links.' }

  if (run.gone || run.runId) return <AlertRunView run={run} onText={onText} onPdf={onPdf} onOver={startOver} />

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
        {run.startError && <StartFailed />}
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
              <PickRow key={index} entry={entry} id={`alert-entry-${index}`} checked={selected.has(index)} onText={onText}
                       onToggle={() => setSelected((now) => {
                         const next = new Set(now)
                         if (!next.delete(index)) next.add(index)
                         return next
                       })} />
            ))}
          </ul>
          <div className="flex flex-col gap-2 border-t pt-3.5 sm:flex-row sm:flex-wrap sm:items-center">
            <Button type="button" disabled={chosen.length === 0 || run.starting}
                    onClick={() => run.start(chosen.map((entry) => ({ url: entry.url, title: entry.title, force: false })))}>
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
            {html !== null && text !== pasted && (
              <> Änderungen am Text wirken sich nicht aus: Gefunden wird, was du eingefügt hast. Leere das Feld, um
              eine andere Mail einzufügen.</>
            )}
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
