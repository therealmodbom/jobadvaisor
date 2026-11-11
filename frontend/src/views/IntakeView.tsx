import { useEffect, useState, type FormEvent } from 'react'
import { Check, CircleAlert, LoaderCircle, ShieldAlert, ShieldCheck, ShieldOff, Upload, X } from 'lucide-react'
import { api, ApiError, type Attempt, type BatchResult, type IntakeAnswer, type Posting } from '@/api'
import { PostingFields } from '@/components/posting'
import { ImportView } from '@/views/ImportView'
import { ErrorWithRetry, Loading } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { categoryNames } from '@/lib/german'
import { cn } from '@/lib/utils'

type Source = 'url' | 'text' | 'pdf'
type Status =
  | { kind: 'idle' }
  | { kind: 'running' }
  | { kind: 'failed'; attempts: Attempt[] }
  | { kind: 'error'; message: string }
  | { kind: 'done'; answer: IntakeAnswer }
  | { kind: 'batch'; results: BatchResult[] }

const SOURCES: [Source, string][] = [['url', 'Link(s)'], ['text', 'Text einfügen'], ['pdf', 'PDF']]

const STEPS: Record<string, string> = {
  bundesagentur: 'Jobbörse der Bundesagentur',
  plain: 'Einfacher Abruf',
  rendered: 'Abruf im Browser',
  login_wall: 'Seite mit Login-Pflicht',
  'loop:fetch_plain': 'Weitere Seite, einfacher Abruf',
  'loop:fetch_rendered': 'Weitere Seite, Abruf im Browser',
  'loop:search_alternative_source': 'Websuche nach einer anderen Quelle',
}

/** German text for a failed intake request; the API's own detail is English and stays out. */
function intakeError(error: unknown): string {
  if (!(error instanceof ApiError) || error.status === 0) return 'Der Server ist nicht erreichbar.'
  if (error.error === 'no posting text') return 'Darin wurde kein Anzeigentext gefunden.'
  if (error.error === 'invalid request') {
    return 'Die Eingabe wurde nicht angenommen. Ein Link muss mit http:// oder https:// beginnen.'
  }
  return 'Beim Speichern ist ein Fehler aufgetreten.'
}

/** The intake view: submit a posting by link (several at once, one per line), text or PDF, check
 * the fields the app filled, release a flagged posting, and edit the hosts that are never
 * fetched anonymously. With `list` (route `#/importieren`) it shows the source "Liste", the list
 * import (`ImportView`), which stays mounted while another source shows, so an import keeps
 * polling; choosing "Liste" or leaving it changes the route. */
export function IntakeView({ list = false }: { list?: boolean }) {
  const [source, setSource] = useState<Source>('url')
  const [url, setUrl] = useState('')
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [status, setStatus] = useState<Status>({ kind: 'idle' })
  const running = status.kind === 'running'

  async function submit(event?: FormEvent) {
    event?.preventDefault()
    if (running) return
    const links = url.split('\n').map((line) => line.trim()).filter(Boolean)
    const form = new FormData()
    if (source === 'url' && links.length > 1) {
      setStatus({ kind: 'running' })
      try {
        const { results } = await api<{ results: BatchResult[] }>('/postings/batch',
                                                                   { method: 'POST', json: { urls: links } })
        setStatus({ kind: 'batch', results })
      } catch (error) {
        setStatus({ kind: 'error', message: intakeError(error) })
      }
      return
    }
    if (source === 'url' && links.length === 1) form.set('url', links[0])
    else if (source === 'text' && text.trim()) form.set('text', text)
    else if (source === 'pdf' && file) form.set('file', file)
    else return
    setStatus({ kind: 'running' })
    try {
      setStatus({ kind: 'done', answer: await api<IntakeAnswer>('/postings', { method: 'POST', form }) })
    } catch (error) {
      setStatus(error instanceof ApiError && error.error === 'posting not found'
        ? { kind: 'failed', attempts: (error.body.attempts as Attempt[]) ?? [] }
        : { kind: 'error', message: intakeError(error) })
    }
  }

  function switchTo(next: Source) {
    if (list) window.location.assign('#/hinzufuegen')
    setSource(next)
    setStatus({ kind: 'idle' })
  }

  const submitLabel = running ? 'Wird hinzugefügt…' : 'Hinzufügen'
  const chosen = list ? 'list' : source
  return (
    <div className="mx-auto flex max-w-[760px] flex-col gap-6">
      <div>
        <h1 className="text-3xl leading-tight font-bold tracking-tight">Anzeige hinzufügen</h1>
        <p className="mt-1.5 text-muted-foreground">
          Gib einen Link, den Anzeigentext oder ein PDF an, oder importiere eine ganze Liste. Titel,
          Firma und Ort werden ausgefüllt, du prüfst sie danach.
        </p>
      </div>

      <div role="group" aria-label="Quelle der Anzeige"
           className="inline-flex flex-wrap gap-1 self-start rounded-[10px] bg-muted p-1">
        {[...SOURCES, ['list', 'Liste'] as const].map(([id, label]) => (
          <button key={id} type="button" aria-pressed={chosen === id} disabled={running}
                  onClick={() => id === 'list' ? window.location.assign('#/importieren') : switchTo(id)}
                  className={cn('min-h-10 rounded-[7px] px-3.5 disabled:opacity-60',
                    chosen === id ? 'bg-card font-bold text-foreground shadow-card'
                      : 'font-medium text-muted-foreground')}>
            {label}
          </button>
        ))}
      </div>

      <div hidden={!list}><ImportView /></div>

      <div hidden={list} className="flex flex-col gap-6">
        <form onSubmit={submit} className="flex flex-col gap-4 rounded-xl border bg-card p-5 shadow-card">
          {source === 'url' && (
            <div className="flex flex-col gap-1.5">
              <label htmlFor="posting-url" className="font-bold">Link zur Anzeige</label>
              <Textarea id="posting-url" rows={3} placeholder="https://" value={url} disabled={running}
                        aria-describedby="posting-url-hint" onChange={(event) => setUrl(event.target.value)} />
              <span id="posting-url-hint" className="text-[13px] text-muted-foreground">
                Mehrere Links gehen auf einmal: einer pro Zeile.
              </span>
              <Button type="submit" disabled={running} className="self-start">{submitLabel}</Button>
            </div>
          )}
          {source === 'text' && (
            <div className="flex flex-col gap-1.5">
              <label htmlFor="posting-text" className="font-bold">Anzeigentext</label>
              <Textarea id="posting-text" rows={8} value={text} disabled={running}
                        placeholder="Füge die ganze Anzeige ein, mit Firma und Ort, falls sie darin stehen."
                        onChange={(event) => setText(event.target.value)} />
              <Button type="submit" disabled={running} className="self-start">{submitLabel}</Button>
            </div>
          )}
          {source === 'pdf' && (
            <div className="flex flex-col items-start gap-2.5 rounded-xl border-2 border-dashed p-6">
              <label htmlFor="posting-pdf" className="inline-flex items-center gap-2 font-bold">
                <Upload className="size-5" aria-hidden="true" />Anzeige als PDF
              </label>
              <input id="posting-pdf" type="file" accept="application/pdf" disabled={running}
                     onChange={(event) => setFile(event.target.files?.[0] ?? null)} className="text-[15px]" />
              <p className="text-sm text-muted-foreground">
                Praktisch, wenn die Jobseite einen Login verlangt. Drucke die Anzeige im Browser als PDF.
              </p>
              <Button type="submit" disabled={running}>{submitLabel}</Button>
            </div>
          )}

          {running && (
            <div role="status" className="flex items-center gap-3 rounded-[10px] bg-muted px-4 py-3.5">
              <LoaderCircle className="size-5 flex-none motion-safe:animate-spin" aria-hidden="true" />
              <span>
                <strong>Anzeige wird hinzugefügt.</strong> Ein Link kann bis zu einer Minute dauern: Die
                Seite wird abgerufen, wenn nötig in einem Browser, danach werden Titel, Firma und Ort
                ausgefüllt.
              </span>
            </div>
          )}
        </form>

        {status.kind === 'failed' && (
          <FailedLink attempts={status.attempts} onText={() => switchTo('text')}
                      onPdf={() => switchTo('pdf')} onRetry={() => submit()} />
        )}
        {status.kind === 'error' && (
          <ErrorWithRetry title="Anzeige konnte nicht hinzugefügt werden" detail={status.message}
                          onRetry={() => submit()} />
        )}
        {status.kind === 'done' && (
          <IntakeResult key={status.answer.posting_id} answer={status.answer} />
        )}
        {status.kind === 'batch' && (
          <BatchResults results={status.results} onText={() => switchTo('text')}
                        onPdf={() => switchTo('pdf')} />
        )}
      </div>

      <LoginWallHosts />
    </div>
  )
}

/** A link no step could read: the attempts made, then the text and PDF options and a retry. */
function FailedLink({ attempts, onText, onPdf, onRetry }: {
  attempts: Attempt[]
  onText: () => void
  onPdf: () => void
  onRetry: () => void
}) {
  const walled = attempts.some((attempt) => attempt.step === 'login_wall')
  return (
    <section role="alert" className="flex flex-col gap-3.5 rounded-xl border border-danger bg-danger-soft p-5">
      <div className="flex items-start gap-2.5">
        <CircleAlert className="mt-0.5 size-[22px] flex-none text-danger" aria-hidden="true" />
        <div>
          <h2 className="text-lg font-bold">Anzeige konnte nicht gelesen werden</h2>
          <p className="mt-1">
            {walled ? 'Der Link führt zu einer Seite mit Login-Pflicht. ' : ''}Diese Versuche wurden gemacht:
          </p>
        </div>
      </div>
      <AttemptList attempts={attempts} className="ml-8" />
      <p className="ml-8">Füge stattdessen den Text ein oder lade ein PDF hoch.</p>
      <div className="ml-8 flex flex-wrap gap-2">
        <Button type="button" onClick={onText}>Text einfügen</Button>
        <Button type="button" variant="outline" onClick={onPdf}>PDF hochladen</Button>
        <Button type="button" variant="outline" onClick={onRetry}>Link erneut versuchen</Button>
      </div>
    </section>
  )
}

/** The steps tried for a link, one line each, with their outcome in German. */
function AttemptList({ attempts, className }: { attempts: Attempt[]; className?: string }) {
  return (
    <ol className={cn('flex list-decimal flex-col gap-1 pl-5', className)}>
      {attempts.map((attempt, index) => (
        <li key={index}>
          {STEPS[attempt.step] ?? attempt.step}:{' '}
          {attempt.outcome === 'skipped' ? 'übersprungen'
            : attempt.outcome === 'ok' ? 'keine Anzeige gefunden'
              : <>fehlgeschlagen <span lang="en" className="text-sm text-muted-foreground">({attempt.outcome})</span></>}
        </li>
      ))}
    </ol>
  )
}

const OUTCOMES = { stored: 'Hinzugefügt', duplicate: 'Schon gespeichert', failed: 'Nicht gelesen' }

/** The outcome of each link of a batch: stored or duplicate with a link to the posting's page,
 * failed with the attempts made and the text and PDF options. A failed link never hides the rest. */
function BatchResults({ results, onText, onPdf }: {
  results: BatchResult[]
  onText: () => void
  onPdf: () => void
}) {
  const failed = results.filter((result) => result.outcome === 'failed').length
  return (
    <section aria-labelledby="batch-title" className="flex flex-col gap-3.5 rounded-xl border bg-card p-5">
      <div>
        <h2 id="batch-title" className="text-lg font-bold">
          {results.length - failed} von {results.length} Links gespeichert
        </h2>
        {failed > 0 && (
          <p className="mt-1 text-muted-foreground">
            Bei {failed === 1 ? 'einem Link' : `${failed} Links`} hat das nicht geklappt. Die anderen sind
            gespeichert.
          </p>
        )}
      </div>
      <ul aria-label="Ergebnis je Link" className="flex flex-col gap-3">
        {results.map((result, index) => (
          <li key={index} className={cn('flex flex-col gap-2 rounded-[10px] border px-4 py-3',
                                        result.outcome === 'failed' && 'border-danger bg-danger-soft')}>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <strong className="inline-flex items-center gap-1.5">
                {result.outcome === 'failed'
                  ? <CircleAlert className="size-4 text-danger" aria-hidden="true" />
                  : <Check className="size-4 text-success" strokeWidth={3} aria-hidden="true" />}
                {OUTCOMES[result.outcome]}
              </strong>
              <span className="min-w-0 break-all font-mono text-sm">{result.url}</span>
              {result.outcome !== 'failed' && (
                <a href={`#/anzeigen/${encodeURIComponent(result.posting_id)}`}
                   className="text-primary underline">Anzeige ansehen</a>
              )}
            </div>
            {result.outcome === 'failed' && (
              <>
                {result.attempts && result.attempts.length > 0 ? (
                  <>
                    <p>Diese Versuche wurden gemacht:</p>
                    <AttemptList attempts={result.attempts} />
                  </>
                ) : (
                  <p>Dieser Link wurde nicht angenommen. Er muss mit http:// oder https:// beginnen.</p>
                )}
                <div className="flex flex-wrap gap-2">
                  <Button type="button" size="sm" onClick={onText}>Text einfügen</Button>
                  <Button type="button" size="sm" variant="outline" onClick={onPdf}>PDF hochladen</Button>
                </div>
              </>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

/** A stored posting: its screening state, a release action when flagged, and its title,
 * company and location for correction (`PostingFields`). */
function IntakeResult({ answer }: { answer: IntakeAnswer }) {
  const [posting, setPosting] = useState<Posting>(answer.posting)
  const [releaseError, setReleaseError] = useState(false)

  async function patch(body: object): Promise<Posting> {
    const updated = await api<{ posting: Posting }>(`/postings/${answer.posting_id}`,
                                                    { method: 'PATCH', json: body })
    setPosting(updated.posting)
    return updated.posting
  }

  async function release() {
    setReleaseError(false)
    try {
      await patch({ release: true })
    } catch {
      setReleaseError(true)
    }
  }

  const guard = posting.guard
  return (
    <section aria-labelledby="result-title" className="flex flex-col gap-4 rounded-xl border bg-card p-5">
      <div className="flex items-start gap-2.5">
        <span className="inline-flex size-7 flex-none items-center justify-center rounded-full bg-success-soft text-success">
          <Check className="size-4" strokeWidth={3} aria-hidden="true" />
        </span>
        <div>
          <h2 id="result-title" className="text-lg font-bold">
            {answer.duplicate ? 'Schon gespeichert' : 'Anzeige hinzugefügt'}
          </h2>
          <p className="mt-0.5 text-muted-foreground">
            {answer.duplicate
              ? 'Diese Anzeige wurde schon einmal hinzugefügt, es wurde nichts Neues gespeichert. Das sind die gespeicherten Felder.'
              : 'Prüfe diese drei Felder. Ausschlussregeln lesen sie, eine falsche Firma kann eine Anzeige also verstecken. Die nächste Bewertung der Anzeigen nimmt sie mit.'}
          </p>
        </div>
      </div>

      {!answer.screening && !guard ? (
        <div className="flex items-start gap-2.5 rounded-[10px] bg-muted px-3.5 py-3 text-[15px]">
          <ShieldOff className="mt-0.5 size-[18px] flex-none" aria-hidden="true" />
          <p>
            <strong>Inhaltsprüfung ist aus.</strong> Es ist kein Prüfmodell eingerichtet, diese Anzeige
            wurde also nicht geprüft. Beim Bewerten der Anzeigen wirst du nach ihr gefragt, bevor ein Modell sie liest.
          </p>
        </div>
      ) : guard?.flagged ? (
        <div className="flex flex-col gap-2.5 rounded-[10px] border border-danger bg-danger-soft px-4 py-3.5">
          <div className="flex items-start gap-2.5">
            <ShieldAlert className="mt-0.5 size-5 flex-none text-danger" aria-hidden="true" />
            <div>
              <p>
                <strong>Von der Inhaltsprüfung markiert:</strong>{' '}
                {categoryNames(guard.categories)}.
              </p>
              <p className="mt-1 text-[15px]">
                Die Anzeige ist gespeichert, bleibt aber bei jeder Bewertung außen vor. Gib sie nur frei,
                wenn du den Text gelesen hast und es eine normale Anzeige ist.
              </p>
            </div>
          </div>
          {guard.released_at ? (
            <p role="status" className="ml-[30px] inline-flex items-center gap-1.5 font-bold text-success">
              <Check className="size-4" strokeWidth={3} aria-hidden="true" />
              Freigegeben. Die nächste Bewertung der Anzeigen nimmt sie mit.
            </p>
          ) : (
            <Button type="button" variant="outline" onClick={release}
                    className="ml-[30px] self-start border-danger text-danger">
              Anzeige freigeben
            </Button>
          )}
          {releaseError && (
            <p role="alert" className="ml-[30px] text-danger">Freigeben hat nicht geklappt. Versuch es noch einmal.</p>
          )}
        </div>
      ) : (
        <p className="inline-flex items-center gap-2 text-[15px]">
          <ShieldCheck className="size-[18px] text-success" aria-hidden="true" />
          Inhaltsprüfung ist an. In dieser Anzeige wurde nichts gefunden.
        </p>
      )}

      <PostingFields postingId={answer.posting_id} posting={posting} onSaved={setPosting}>
        {posting.urls[0] && <a href={posting.urls[0]} target="_blank" rel="noreferrer" className="text-primary underline">Anzeige öffnen</a>}
      </PostingFields>
    </section>
  )
}

/** Normalizes what the user typed into a bare host name: no scheme, `www.`, path, port or
 * spaces. A host covers its subdomains, so `www.` would only narrow it. */
function hostName(typed: string): string {
  return typed.trim().toLowerCase().replace(/^[a-z]+:\/\//, '').replace(/^www\./, '')
    .replace(/[/:?#].*$/, '')
}

/** The editor for the policy pack's login-walled hosts, read and saved through
 * `/policy-pack/login-wall-hosts`. */
function LoginWallHosts() {
  const [hosts, setHosts] = useState<string[] | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)
  const [typed, setTyped] = useState('')
  const [state, setState] = useState<'clean' | 'dirty' | 'saving' | 'saved' | 'error'>('clean')
  const [invalid, setInvalid] = useState('')

  function load() {
    api<{ hosts: string[] }>('/policy-pack/login-wall-hosts')
      .then((answer) => setHosts(answer.hosts), () => setLoadFailed(true))
  }
  useEffect(load, [])

  function change(next: string[]) {
    setHosts(next)
    setState('dirty')
  }

  function add(event: FormEvent) {
    event.preventDefault()
    const host = hostName(typed)
    setTyped('')
    if (host && hosts && !hosts.includes(host)) change([...hosts, host])
  }

  async function save() {
    if (!hosts) return
    setState('saving')
    try {
      setHosts((await api<{ hosts: string[] }>('/policy-pack/login-wall-hosts',
                                               { method: 'PUT', json: { hosts } })).hosts)
      setState('saved')
    } catch (error) {
      setInvalid(error instanceof ApiError && error.error === 'invalid host'
        ? error.detail.replace(/^not a host name: /, '') : '')
      setState('error')
    }
  }

  return (
    <section aria-labelledby="hosts-title" className="flex flex-col gap-3.5 rounded-xl border bg-card p-5">
      <div>
        <h2 id="hosts-title" className="text-lg font-bold">Seiten mit Login-Pflicht</h2>
        <p className="mt-1 text-muted-foreground">
          Links auf diese Seiten werden nie abgerufen, weil sie nur ein Login-Formular zeigen. Füge dort
          den Text ein oder lade ein PDF hoch. Eine Seite schließt ihre Subdomains ein.
        </p>
      </div>
      {loadFailed ? (
        <ErrorWithRetry title="Liste konnte nicht geladen werden"
                        detail="Der Server ist nicht erreichbar."
                        onRetry={() => { setLoadFailed(false); load() }} />
      ) : hosts === null ? (
        <Loading label="Liste wird geladen" />
      ) : (
        <>
          {hosts.length === 0 ? (
            <p className="text-[15px] text-muted-foreground">Keine Seiten eingetragen. Jeder Link wird abgerufen.</p>
          ) : (
            <ul aria-label="Seiten mit Login-Pflicht" className="flex flex-wrap gap-2">
              {hosts.map((host) => (
                <li key={host} className="inline-flex min-h-10 items-center gap-1 rounded-full border bg-background pr-1 pl-3">
                  <span className="font-mono text-sm">{host}</span>
                  <button type="button" aria-label={`${host} entfernen`}
                          onClick={() => change(hosts.filter((item) => item !== host))}
                          className="inline-flex size-8 items-center justify-center rounded-full hover:bg-muted">
                    <X className="size-4" aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <form onSubmit={add} className="flex flex-col gap-1.5">
            <label htmlFor="new-host" className="text-sm font-bold">Neue Seite</label>
            <div className="flex flex-wrap gap-2">
              <Input id="new-host" value={typed} placeholder="jobs.example.com" aria-describedby="new-host-hint"
                     onChange={(event) => setTyped(event.target.value)} className="min-w-0 flex-[1_1_240px]" />
              <Button type="submit" variant="outline">Seite hinzufügen</Button>
            </div>
            <span id="new-host-hint" className="text-[13px] text-muted-foreground">
              Nur der Hostname, ohne https:// und ohne Pfad.
            </span>
          </form>
          <div className="flex flex-wrap items-center gap-3 border-t pt-3.5">
            <Button type="button" onClick={save} disabled={state === 'saving'}>Liste speichern</Button>
            {state === 'dirty' && <span className="text-[15px] text-muted-foreground">Ungespeicherte Änderungen</span>}
            {state === 'saved' && (
              <span role="status" className="inline-flex items-center gap-1.5 font-bold text-success">
                <Check className="size-4" strokeWidth={3} aria-hidden="true" />
                Gespeichert. Der nächste Link nutzt diese Liste.
              </span>
            )}
            {state === 'error' && (
              <span role="alert" className="text-danger">
                {invalid ? `Kein gültiger Hostname: ${invalid}` : 'Speichern hat nicht geklappt. Versuch es noch einmal.'}
              </span>
            )}
          </div>
        </>
      )}
    </section>
  )
}
