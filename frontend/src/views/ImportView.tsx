import { useEffect, useRef, useState, type FormEvent } from 'react'
import { LoaderCircle, Upload } from 'lucide-react'
import {
  api, ApiError, type ImportChoice, type ImportConflict, type ImportMapping, type ImportPreview, type ImportState,
  type NotImported, type Status,
} from '@/api'
import { Badge, OriginalLink } from '@/components/posting'
import { ErrorWithRetry } from '@/components/states'
import { Button } from '@/components/ui/button'
import { STATUSES } from '@/lib/german'
import { POLL_FAILURES, POLL_MS } from '@/views/PoolView'

const IMPORT_KEY = 'jobadvaisor.import'

const RUNNING_KEY = 'jobadvaisor.import.running'

/** The import ID kept across a reload, and whether it was last seen running (then a 404 means the
 * import was interrupted, else the server merely forgot a finished one). Storage may be blocked,
 * so every access is guarded. */
const storedImport = {
  get: () => {
    try {
      return sessionStorage.getItem(IMPORT_KEY)
    } catch {
      return null
    }
  },
  wasRunning: () => {
    try {
      return sessionStorage.getItem(RUNNING_KEY) === '1'
    } catch {
      return false
    }
  },
  set: (id: string | null, running = false) => {
    try {
      if (id) sessionStorage.setItem(IMPORT_KEY, id)
      else sessionStorage.removeItem(IMPORT_KEY)
      if (id && running) sessionStorage.setItem(RUNNING_KEY, '1')
      else sessionStorage.removeItem(RUNNING_KEY)
    } catch { /* storage blocked: a reload simply does not resume */ }
  },
}

const COUNT_LABELS: [keyof ImportState['counts'], string][] = [
  ['imported', 'Importiert'],
  ['duplicate', 'Schon vorhanden'],
  ['skipped_status', 'Übersprungen (Status)'],
  ['skipped_gone', 'Übersprungen, Link nicht mehr erreichbar'],
  ['failed', 'Fehlgeschlagen'],
]

const INTERRUPTED = 'Der Import wurde unterbrochen, etwa weil der Server neu gestartet wurde. '
  + 'Du kannst die Datei noch einmal hochladen: Was schon gespeichert ist, zählt dann als vorhanden.'

/** German text for a refused or failed preview or start; the API's own detail is English and stays out. */
function uploadError(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) return 'Es läuft schon ein Import. Warte, bis er fertig ist.'
  if (error instanceof ApiError && error.error === 'invalid mapping') return 'Die Zuordnung wurde nicht angenommen. Prüfe sie und versuche es noch einmal.'
  if (error instanceof ApiError && error.status === 422) return 'Die Datei konnte nicht als Text gelesen werden. Wähle eine Markdown-Datei.'
  return 'Der Import konnte nicht gestartet werden. Ist der Server erreichbar?'
}

const STATUS_NAMES = Object.fromEntries(STATUSES) as Record<Status, string>

/** What each entry's outcome is called in the list of entries not imported. */
const OUTCOME_LABELS: Record<NotImported['outcome'], string> = {
  skipped_status: 'Übersprungen (Status)',
  skipped_gone: 'Link nicht mehr erreichbar',
  failed: 'Fehlgeschlagen',
}

/** The choices for a status value of the list, with their German names. */
const CHOICES: [ImportChoice, string][] = [...STATUSES, ['skip', 'überspringen']]

const SELECT = 'min-h-11 rounded-lg border border-input bg-background px-2.5 text-[15px]'

/** Names compare trimmed and without case, as the backend matches them. */
const norm = (name: string) => name.trim().toLowerCase()

/** The non-empty `names` by normalised name, keeping each one's first spelling and position. */
function byName(names: string[]): Map<string, string> {
  const unique = new Map<string, string>()
  for (const name of names) if (name.trim() && !unique.has(norm(name))) unique.set(norm(name), name)
  return unique
}

/** One posting whose app status differs from the list's (`conflict`): its title (link), company,
 * both statuses and the choice. "Aus Liste übernehmen" sends `PATCH /postings/{id}` with the
 * list's status (`aria-disabled` while saving, not `disabled`, so keyboard focus stays on the
 * button; an error with retry on failure); "App behalten" sends nothing. A decided row keeps its
 * place and moves focus to its result line. */
function ConflictRow({ conflict }: { conflict: ImportConflict }) {
  const { posting_id: id, title, company, status, list_status: listStatus } = conflict
  const [decision, setDecision] = useState<'list' | 'app' | null>(null)
  const [saving, setSaving] = useState(false)
  const [failed, setFailed] = useState(false)
  const result = useRef<HTMLParagraphElement>(null)
  useEffect(() => { if (decision) result.current?.focus() }, [decision])

  async function takeFromList() {
    if (saving) return
    setSaving(true)
    setFailed(false)
    try {
      await api(`/postings/${encodeURIComponent(id)}`, { method: 'PATCH', json: { status: listStatus } })
      setDecision('list')
    } catch {
      setFailed(true)
    } finally {
      setSaving(false)
    }
  }

  return (
    <li aria-label={title} className="flex flex-col gap-1.5 rounded-lg border p-3">
      <a href={`#/anzeigen/${encodeURIComponent(id)}`} className="font-bold text-foreground">{title}</a>
      <span className="text-muted-foreground">{company}</span>
      <span>App: {STATUS_NAMES[status]} · Liste: {STATUS_NAMES[listStatus]}</span>
      {decision === 'list' && <p ref={result} role="status" tabIndex={-1}>Übernommen: {STATUS_NAMES[listStatus]}</p>}
      {decision === 'app' && <p ref={result} tabIndex={-1}>App-Status bleibt: {STATUS_NAMES[status]}</p>}
      {failed && <p role="alert" className="text-danger">Der Status wurde nicht gespeichert.</p>}
      {!decision && (
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" aria-disabled={saving}
                  className="aria-disabled:pointer-events-none aria-disabled:opacity-50" onClick={takeFromList}>
            Aus Liste übernehmen
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => setDecision('app')}>App behalten</Button>
        </div>
      )}
    </li>
  )
}

/** Step 2 of the import: what the list's columns mean, for the `preview` of `POST /imports/preview`.
 * Shows the tables found, the status column (prefilled from the stored mapping), one choice per
 * distinct value of that column (values differing only in case share a row) and the optional
 * assessment column. Nothing drifts silently: a table lacking the chosen status column is marked
 * as not imported, a value the stored mapping does not name gets a "neu" badge (only with a
 * stored mapping), and "keine" warns while the stored mapping names a status column. "Import
 * starten" hands the confirmed `ImportMapping` to `onStart`, "Andere Datei" calls `onBack`. A
 * list without tables offers only `onBack`. */
function MappingForm({ preview, onStart, onBack }: {
  preview: ImportPreview
  onStart: (mapping: ImportMapping) => void
  onBack: () => void
}) {
  const { tables, mapping } = preview
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => heading.current?.focus(), []) // the pressed "Weiter" is gone: focus lands here
  const columns = [...byName(tables.flatMap((table) => table.columns)).values()]
  const known = (name: string | null | undefined) => columns.find((column) => norm(column) === norm(name ?? '')) ?? ''
  const [statusColumn, setStatusColumn] = useState(known(mapping?.status_column))
  const [assessmentColumn, setAssessmentColumn] = useState(known(mapping?.assessment_column))
  /** Choices the user changed since the status column was picked, by normalised value. */
  const [changed, setChanged] = useState<Record<string, ImportChoice>>({})

  const valuesByColumn = new Map(Object.entries(preview.values).map(([column, values]) => [norm(column), values]))
  const distinct = valuesByColumn.get(norm(statusColumn))
  const rows = byName(distinct ?? [])
  const storedChoices = new Map(Object.entries(mapping?.values ?? {}).map(([value, choice]) => [norm(value), choice]))
  const choiceOf = (key: string): ImportChoice => changed[key] ?? storedChoices.get(key) ?? 'open'

  function submit(event: FormEvent) {
    event.preventDefault()
    onStart({
      status_column: statusColumn || null,
      assessment_column: assessmentColumn || null,
      values: {
        // remembered choices for values this file does not have stay
        ...Object.fromEntries(Object.entries(mapping?.values ?? {}).filter(([value]) => !rows.has(norm(value)))),
        ...Object.fromEntries([...rows].map(([key, value]) => [value, choiceOf(key)])),
      },
    })
  }

  const columnOptions = (
    <>
      <option value="">keine</option>
      {columns.map((column) => <option key={column} value={column}>{column}</option>)}
    </>
  )
  return (
    <form onSubmit={submit} aria-labelledby="import-mapping"
          className="flex flex-col items-start gap-4 rounded-xl border bg-card p-5 shadow-card">
      <h2 id="import-mapping" ref={heading} tabIndex={-1} className="text-xl font-bold">Spalten zuordnen</h2>
      {tables.length === 0 ? (
        <p>In der Datei wurde keine Tabelle mit Links gefunden. Jede Zeile braucht einen Link zur Anzeige.</p>
      ) : (
        <>
          <ul aria-label="Tabellen in der Datei" className="list-inside list-disc">
            {tables.map((table, index) => (
              <li key={index}>
                {table.name || 'Tabelle ohne Überschrift'} · {table.entries} {table.entries === 1 ? 'Eintrag' : 'Einträge'}
                {statusColumn && !table.columns.some((column) => norm(column) === norm(statusColumn)) && (
                  <strong> · wird nicht importiert (Spalte „{statusColumn}“ fehlt)</strong>
                )}
              </li>
            ))}
          </ul>
          <div className="flex flex-col gap-1">
            <label htmlFor="import-status-column" className="text-sm font-bold">Status-Spalte</label>
            <select id="import-status-column" value={statusColumn} className={SELECT}
                    onChange={(event) => { setStatusColumn(event.target.value); setChanged({}) }}>
              {columnOptions}
            </select>
            {statusColumn && (
              <p className="text-sm text-muted-foreground">Es werden nur Tabellen importiert, die die Status-Spalte haben.</p>
            )}
            {!statusColumn && mapping?.status_column && (
              <p role="alert" className="rounded-lg border border-danger bg-danger-soft px-3 py-2 text-sm">
                Ohne Status-Spalte wird jede Tabelle mit Links importiert, und jeder Eintrag wird „offen“.
                Beim letzten Import war „{mapping.status_column}“ die Status-Spalte.
              </p>
            )}
          </div>
          {statusColumn && distinct === undefined && (
            <p className="text-muted-foreground">
              Diese Spalte enthält die Links oder hat mehr als 30 verschiedene Werte und kann keinem Status
              zugeordnet werden. Wähle eine andere Status-Spalte oder „keine“.
            </p>
          )}
          {rows.size > 0 && (
            <fieldset className="flex flex-col gap-2.5">
              <legend className="mb-1 font-bold">Werte der Spalte „{statusColumn}“</legend>
              {[...rows].map(([key, value], index) => {
                const isNew = mapping !== null && !storedChoices.has(key) // the list's news, not the choice
                return (
                <div key={key} className="flex flex-wrap items-center gap-3">
                  <label htmlFor={`import-value-${index}`} className="min-w-32">{value}</label>
                  <select id={`import-value-${index}`} value={choiceOf(key)} className={SELECT}
                          aria-describedby={isNew ? `import-value-${index}-new` : undefined}
                          onChange={(event) => setChanged({ ...changed, [key]: event.target.value as ImportChoice })}>
                    {CHOICES.map(([choice, label]) => <option key={choice} value={choice}>{label}</option>)}
                  </select>
                  {isNew && <Badge id={`import-value-${index}-new`} className="bg-muted text-foreground">neu</Badge>}
                </div>
                )
              })}
            </fieldset>
          )}
          <div className="flex flex-col gap-1">
            <label htmlFor="import-assessment-column" className="text-sm font-bold">
              Spalte für deine Einschätzung (optional)
            </label>
            <select id="import-assessment-column" value={assessmentColumn} className={SELECT}
                    onChange={(event) => setAssessmentColumn(event.target.value)}>
              {columnOptions}
            </select>
          </div>
        </>
      )}
      <div className="flex flex-wrap gap-2">
        {tables.length > 0 && (
          // no values to map: starting would import every row as open
          <Button type="submit" disabled={Boolean(statusColumn) && distinct === undefined}>Import starten</Button>
        )}
        <Button type="button" variant="outline" onClick={onBack}>Andere Datei</Button>
      </div>
    </form>
  )
}

/** The list import, the source "Liste" of the intake view (`#/importieren`): upload a Markdown list (`POST /imports/preview`), confirm
 * what its columns mean (`MappingForm`, then `POST /imports`), progress while it runs (polled)
 * and, at the end, the report: counts, the section "Nicht importiert" with every entry left out
 * and why, "Nicht importierte Tabellen" for tables left out for lacking the status column, and
 * "Status weicht ab" for stored postings whose status differs from the list's
 * (title and company, never a URL). The import ID stays stored, so a reload shows the report and
 * the open discrepancies again (a reload during the mapping starts over: the file is not kept);
 * a new upload replaces it. A running import is the only one; the pool picks up the new
 * postings and taken-over statuses when it is opened again. */
export function ImportView() {
  const [file, setFile] = useState<File | null>(null)
  /** The preview of the chosen file while its mapping is confirmed (step 2), else null. */
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [importId, setImportId] = useState<string | null>(storedImport.get)
  /** The last answer of the poll; the report once its status is `done`. */
  const [progress, setProgress] = useState<ImportState | null>(null)
  const [notice, setNotice] = useState('')
  const [pollFailed, setPollFailed] = useState(false)
  const sending = useRef(false)
  /** The preview request is in flight. */
  const [reading, setReading] = useState(false)
  /** Where focus goes once the step that held it is replaced: the file input after "Andere
   * Datei", the progress line after "Import starten". */
  const refocus = useRef<'upload' | 'progress' | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const progressLine = useRef<HTMLParagraphElement>(null)
  useEffect(() => {
    if (refocus.current === 'upload' && !preview) fileInput.current?.focus()
    else if (refocus.current === 'progress' && importId) progressLine.current?.focus()
    else return
    refocus.current = null
  }, [preview, importId])
  /** A stored import counts as running until its first answer says otherwise. */
  const running = importId !== null && (progress === null || progress.status === 'running')

  useEffect(() => {
    if (!importId || !running || pollFailed) return
    let failures = 0
    let stale = false
    const poll = () => api<ImportState>(`/imports/${importId}`).then((next) => {
      if (stale) return
      failures = 0
      storedImport.set(importId, next.status === 'running')
      setProgress(next)
    }, (error) => {
      if (stale) return
      if (error instanceof ApiError && error.status === 404) {
        if (storedImport.wasRunning()) setNotice(INTERRUPTED)
        storedImport.set(null)
        setImportId(null)
      } else if (++failures >= POLL_FAILURES) {
        clearInterval(timer)
        setPollFailed(true)
      }
    })
    const timer = setInterval(poll, POLL_MS)
    poll() // at once, so a reload does not show a finished import as running for an interval
    return () => {
      stale = true
      clearInterval(timer)
    }
  }, [importId, running, pollFailed])

  /** Step 1: sends the chosen file to the preview; its answer opens the mapping form. */
  async function showMapping(event?: FormEvent) {
    event?.preventDefault()
    if (running || sending.current) return
    setNotice('')
    if (!file) return setNotice('Wähle zuerst eine Datei aus.')
    sending.current = true
    setReading(true)
    const form = new FormData()
    form.set('file', file)
    try {
      setPreview(await api<ImportPreview>('/imports/preview', { method: 'POST', form }))
    } catch (error) {
      setNotice(uploadError(error))
    } finally {
      sending.current = false
      setReading(false)
    }
  }

  /** Step 2: starts the import of the chosen file with the confirmed `mapping` and polls it. */
  async function start(mapping: ImportMapping) {
    if (running || sending.current || !file) return
    setNotice('')
    sending.current = true
    const form = new FormData()
    form.set('file', file)
    form.set('mapping', JSON.stringify(mapping))
    try {
      const answer = await api<{ import_id: string }>('/imports', { method: 'POST', form })
      storedImport.set(answer.import_id, true)
      setProgress(null)
      setPollFailed(false)
      setPreview(null)
      setFile(null)
      refocus.current = 'progress'
      setImportId(answer.import_id)
    } catch (error) {
      setNotice(uploadError(error))
    } finally {
      sending.current = false
    }
  }

  const done = progress?.status === 'done' ? progress : null
  const failed = !running && progress?.status === 'failed'
  return (
    <div className="flex flex-col gap-6">
      <p className="text-muted-foreground">
        Lade eine Liste mit deinen alten Anzeigen hoch: eine Markdown-Datei mit Tabellen, in jeder Zeile
        ein Link. Im nächsten Schritt sagst du, welche Spalte den Status enthält. Jeder Eintrag wird
        wie eine neu hinzugefügte Anzeige geprüft und gespeichert. Die Datei selbst wird nicht
        gespeichert, und du siehst am Ende, was mit jedem Eintrag geschehen ist.
      </p>

      {preview ? (
        <MappingForm preview={preview} onStart={start} onBack={() => {
          refocus.current = 'upload'
          setPreview(null)
          setFile(null) // the new, empty file input must not preview the old file
          setNotice('')
        }} />
      ) : (
        <form onSubmit={showMapping} className="flex flex-col items-start gap-2.5 rounded-xl border bg-card p-5 shadow-card">
          <label htmlFor="import-file" className="inline-flex items-center gap-2 font-bold">
            <Upload className="size-5" aria-hidden="true" />Liste als Markdown-Datei
          </label>
          <input id="import-file" ref={fileInput} type="file" accept=".md,text/markdown,text/plain" disabled={running}
                 onChange={(event) => setFile(event.target.files?.[0] ?? null)} className="text-[15px]" />
          {/* aria-disabled while reading, not `disabled`, so keyboard focus stays on the button */}
          <Button type="submit" disabled={running} aria-disabled={reading}
                  className="aria-disabled:pointer-events-none aria-disabled:opacity-50">
            {running ? 'Import läuft…' : reading ? 'Wird gelesen…' : 'Weiter'}
          </Button>
        </form>
      )}

      {/* The live region holds only text that does not change per poll, so it is read once; the
          visible counts sit outside it. */}
      <div role="status" className="sr-only">
        {running && 'Der Import läuft.'}
        {done && 'Der Import ist fertig.'}
      </div>
      {running && !pollFailed && (
        <div className="flex flex-col gap-2 rounded-xl bg-positive-soft px-4 py-3">
          <p ref={progressLine} tabIndex={-1} className="flex items-center gap-3">
            <LoaderCircle className="size-5 flex-none motion-safe:animate-spin" aria-hidden="true" />
            <strong>{progress ? `${progress.done} von ${progress.total} Einträgen` : 'Import läuft'}</strong>
          </p>
          <progress aria-label="Fortschritt des Imports" className="h-2 w-full accent-primary"
                    value={progress?.done} max={progress?.total} />
        </div>
      )}
      {running && pollFailed && (
        <ErrorWithRetry title="Der Stand des Imports ist gerade nicht abrufbar"
                        detail="Der Server antwortet nicht. Der Import rechnet vielleicht weiter."
                        onRetry={() => setPollFailed(false)} />
      )}
      {notice && <p role="alert" className="rounded-xl border border-danger bg-danger-soft px-4 py-3">{notice}</p>}
      {failed && (
        <p role="alert" className="rounded-xl border border-danger bg-danger-soft px-4 py-3">
          Der Import ist fehlgeschlagen. Du kannst dieselbe Datei noch einmal hochladen.
        </p>
      )}
      {done && (
        <section aria-labelledby="import-report" className="flex flex-col gap-3 rounded-xl border bg-card p-5 shadow-card">
          <h2 id="import-report" className="text-xl font-bold">Ergebnis</h2>
          <dl className="grid max-w-[480px] grid-cols-[1fr_auto] gap-x-6 gap-y-1.5">
            {COUNT_LABELS.map(([key, label]) => (
              <div key={key} className="col-span-2 grid grid-cols-subgrid">
                <dt>{label}</dt>
                <dd className="font-bold tabular-nums">{done.counts[key]}</dd>
              </div>
            ))}
          </dl>
          {done.counts.failed > 0 && (
            <p className="text-muted-foreground">
              Lade dieselbe Datei noch einmal hoch, um die fehlgeschlagenen Einträge erneut zu versuchen:
              Was schon gespeichert ist, zählt dann als vorhanden und wird nicht doppelt angelegt.
            </p>
          )}
          <Button asChild className="self-start"><a href="#/pool">Zu den Anzeigen</a></Button>
        </section>
      )}
      {done && done.not_imported.length > 0 && (
        <section aria-labelledby="import-not-imported" className="flex flex-col gap-3 rounded-xl border bg-card p-5 shadow-card">
          <h2 id="import-not-imported" className="text-xl font-bold">Nicht importiert</h2>
          <ul className="flex flex-col gap-2.5">
            {done.not_imported.map((entry, index) => (
              <li key={index} className="flex flex-col gap-1 rounded-lg border p-3">
                <span className="font-bold text-foreground [overflow-wrap:anywhere]">{entry.row}</span>
                <OriginalLink url={entry.url} label={entry.url ?? undefined} />
                <span className="text-muted-foreground">
                  {OUTCOME_LABELS[entry.outcome]}{entry.reason && `: ${entry.reason}`}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {done && done.tables_left_out.length > 0 && (
        <section aria-labelledby="import-left-out" className="flex flex-col gap-3 rounded-xl border bg-card p-5 shadow-card">
          <h2 id="import-left-out" className="text-xl font-bold">Nicht importierte Tabellen</h2>
          <ul className="list-inside list-disc">
            {done.tables_left_out.map((table, index) => (
              <li key={index}>
                {table.name || 'Tabelle ohne Überschrift'} · {table.entries} {table.entries === 1 ? 'Eintrag' : 'Einträge'} · Status-Spalte fehlt
              </li>
            ))}
          </ul>
        </section>
      )}
      {done && done.conflicts.length > 0 && (
        <section aria-labelledby="import-conflicts" className="flex flex-col gap-3 rounded-xl border bg-card p-5 shadow-card">
          <h2 id="import-conflicts" className="text-xl font-bold">Status weicht ab</h2>
          <p>Diese Anzeigen sind schon gespeichert, aber deine Liste nennt einen anderen Status. Welcher gilt?</p>
          <ul className="flex flex-col gap-2.5">
            {done.conflicts.map((conflict) => <ConflictRow key={conflict.posting_id} conflict={conflict} />)}
          </ul>
        </section>
      )}
    </div>
  )
}
