import { useEffect, useId, useState, type ReactNode } from 'react'
import { Check, CircleAlert, CircleSlash, Clock, Copy, Info, LoaderCircle } from 'lucide-react'
import { api, ApiError, type AlertRunEntry, type AlertRunState, type PostingPageData } from '@/api'
import { AttemptList } from '@/components/attempts'
import { Notice, StartFailed } from '@/components/alert-pick'
import { ErrorWithRetry } from '@/components/states'
import { Button } from '@/components/ui/button'
import { PANEL, PASTE_WORDS, ROW, ROW_BUTTON, type RunWords } from '@/lib/alert'
import type { AlertRun, RunEntry, RunRowRef } from '@/lib/alert-run'
import { cn } from '@/lib/utils'

/** The run of an alert mail, pasted or read from the mailbox: the state `run` (`useAlertRun`) as
 * its report. A run the server forgot shows a notice, a run whose polling failed offers a retry,
 * a run not read yet says so, and else the rows come with `RunPanel`. `words` name what leaving
 * the run means (`onOver`) for where the entries came from; `onText` and `onPdf` switch the
 * intake view to the other sources, for an entry that could not be read. */
export function AlertRunView({ run, words = PASTE_WORDS, onText, onPdf, onOver }: {
  run: AlertRun
  words?: RunWords
  onText: () => void
  onPdf: () => void
  onOver: () => void
}) {
  if (run.gone) {
    return (
      <Notice title="Lauf nicht mehr bekannt" Icon={Info} text={words.lost}>
        <Button type="button" onClick={onOver} className="self-start">{words.lostAction}</Button>
      </Notice>
    )
  }
  const { forced, progress } = run
  const shown = forced
    ? forced.base.map((entry, index) => index === forced.index ? (progress?.entries[0] ?? { ...entry, state: 'running' as const }) : entry)
    : progress?.entries
  return (
    <div className="flex flex-col gap-6">
      {run.startError && <StartFailed />}
      {run.pollFailed ? (
        <ErrorWithRetry title="Der Stand des Laufs ist gerade nicht abrufbar"
                        detail="Der Server antwortet nicht. Der Lauf rechnet vielleicht weiter."
                        onRetry={run.retryPoll} />
      ) : shown === undefined ? (
        <div role="status" className="flex items-center gap-3 py-4 text-muted-foreground">
          <LoaderCircle className="size-5 motion-safe:animate-spin" aria-hidden="true" />
          <span>Lauf wird geladen</span>
        </div>
      ) : (
        <RunPanel entries={shown} status={progress?.status ?? 'running'} words={words} start={run.start}
                  runId={run.runId} cancelRequested={progress?.cancel_requested ?? false}
                  onText={onText} onPdf={onPdf} onOver={onOver} />
      )}
    </div>
  )
}

/** The run: "x von y erledigt", a bar while it computes, one row per entry, and at the end the
 * summary or, for a run that crashed, the notice, and for a cancelled one how far it got. `entries`
 * are the rows to show; `status` is the run's, `runId` its ID and `cancelRequested` whether a
 * cancel was asked for. `start` runs a text duplicate again with `force`; `onOver` leaves the
 * run, its button and the crash notice say it in `words`. */
function RunPanel({ entries, status, words, start, runId, cancelRequested, onText, onPdf, onOver }: {
  entries: AlertRunEntry[]
  status: AlertRunState['status']
  words: RunWords
  runId: string | null
  cancelRequested: boolean
  start: (entries: RunEntry[], row: RunRowRef) => void
  onText: () => void
  onPdf: () => void
  onOver: () => void
}) {
  const crashId = useId()
  const runHeadingId = useId()
  const ended = (entry: AlertRunEntry) => ['stored', 'duplicate', 'closed', 'failed'].includes(entry.state)
  const finished = entries.filter(ended).length
  const count = (state: AlertRunEntry['state']) => entries.filter((entry) => entry.state === state).length
  const unclear = entries.filter((entry) => entry.state === 'failed' && entry.unclear).length
  const summary = [
    count('stored') > 0 && `${count('stored')} hinzugefügt`,
    count('duplicate') > 0 && `${count('duplicate')} schon gespeichert`,
    count('closed') > 0 && `${count('closed')} geschlossen`,
    count('failed') > unclear && `${count('failed') - unclear} nicht gelesen`,
    unclear > 0 && `${unclear} nicht beurteilbar`,
  ].filter(Boolean).join(', ')
  return (
    <>
      <div role="status" className="sr-only">
        {status === 'running' && 'Der Lauf läuft.'}
        {status === 'done' && 'Der Lauf ist fertig.'}
        {status === 'cancelled' && 'Der Lauf wurde abgebrochen.'}
      </div>
      {status === 'failed' && (
        <section role="alert" aria-labelledby={crashId} className={cn(PANEL, 'border-danger bg-danger-soft')}>
          <div className="flex items-start gap-2.5">
            <CircleAlert className="mt-0.5 size-[22px] flex-none text-danger" aria-hidden="true" />
            <div>
              <h2 id={crashId} className="text-lg font-bold">Der Lauf ist abgebrochen</h2>
              <p className="mt-1">
                Ein Fehler hat ihn nach {finished} von {entries.length} Anzeigen beendet. Was bis dahin gespeichert ist,
                bleibt gespeichert. {words.crash}
              </p>
            </div>
          </div>
          <Button type="button" variant="outline" onClick={onOver} className="self-start">{words.over}</Button>
        </section>
      )}
      <section aria-labelledby={runHeadingId} className={PANEL}>
        <div>
          <h2 id={runHeadingId} className="text-lg font-bold">{finished} von {entries.length} erledigt</h2>
          {status === 'running' && (
            <p className="mt-0.5 text-[15px] text-muted-foreground">
              Die Anzeigen werden nacheinander abgerufen. Eine Anzeige, die nicht klappt, hält die anderen nicht auf.
            </p>
          )}
          {status === 'cancelled' && (
            <p className="mt-0.5 font-bold">Abgebrochen nach {finished} von {entries.length} Anzeigen</p>
          )}
          {(status === 'done' || status === 'cancelled') && summary && (
            <p className="mt-0.5 text-[15px] text-muted-foreground">
              {summary}.{count('stored') > 0 && ' Prüfe Titel, Firma und Ort der neuen Anzeigen auf ihren Seiten.'}
            </p>
          )}
          {status === 'cancelled' && words.cancelled && (
            <p className="mt-0.5 text-[15px] text-muted-foreground">{words.cancelled}</p>
          )}
          {(status === 'done' || status === 'cancelled') && words.again && count('failed') + count('waiting') > 0 && (
            <p className="mt-0.5 text-[15px] text-muted-foreground">{words.again}</p>
          )}
        </div>
        {status === 'running' && runId && <CancelRun key={runId} runId={runId} requested={cancelRequested} />}
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
          <Button type="button" variant="outline" onClick={onOver} className="self-start">{words.over}</Button>
        )}
      </section>
    </>
  )
}

/** „Lauf abbrechen“ of the computing run `runId`: it cancels at once, without a confirm step, and
 * from then on (or when the run reports it, `requested`) it is disabled and says „Wird abgebrochen …“.
 * It stays focusable (`aria-disabled`), like the check's cancel. A request that fails says so and
 * offers the button again; a refusal because the run ended is left to the next poll. */
function CancelRun({ runId, requested }: { runId: string; requested: boolean }) {
  const [asked, setAsked] = useState(false)
  const [failed, setFailed] = useState(false)
  const hintId = useId()
  const waiting = asked || requested
  async function cancel() {
    if (waiting) return
    setAsked(true)
    setFailed(false)
    try {
      await api(`/alert-mails/runs/${encodeURIComponent(runId)}/cancel`, { method: 'POST' })
    } catch (error) {
      if (!(error instanceof ApiError && (error.status === 409 || error.status === 404))) {
        setAsked(false)
        setFailed(true)
      }
    }
  }
  return (
    <div className="flex flex-col gap-1.5">
      <Button type="button" variant="outline" aria-describedby={hintId} aria-disabled={waiting || undefined}
              onClick={() => void cancel()}
              className={cn('self-start max-sm:min-h-11 max-sm:w-full', waiting && 'cursor-default text-muted-foreground hover:bg-card')}>
        {waiting ? 'Wird abgebrochen …' : 'Lauf abbrechen'}
      </Button>
      <p id={hintId} className="text-sm text-muted-foreground">
        Der Lauf stoppt nach der aktuellen Anzeige. Was gespeichert ist, bleibt gespeichert.
      </p>
      {failed && <p role="alert" className="text-danger">Das Abbrechen hat nicht geklappt. Versuch es noch einmal.</p>}
    </div>
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
        {entry.state === 'closed' && <Label tone="text-muted-foreground" text="Stelle geschlossen"
                                            icon={<CircleSlash className={ICON} aria-hidden="true" />} />}
        {entry.state === 'failed' && <Label tone="text-danger" text={entry.unclear ? 'Nicht beurteilbar' : 'Nicht gelesen'}
                                            icon={<CircleAlert className={ICON} aria-hidden="true" />} />}
        {entry.state === 'running' && <Label text="wird abgerufen…"
                                             icon={<LoaderCircle className={cn(ICON, 'motion-safe:animate-spin')} aria-hidden="true" />} />}
        {entry.state === 'waiting' && <Label tone="text-muted-foreground" text={ended ? 'nicht gestartet' : 'wartet'}
                                             icon={<Clock className={ICON} aria-hidden="true" />} />}
        {entry.title && <span className="font-bold">{entry.title}</span>}
        <span className="font-mono text-sm break-all text-muted-foreground">{entry.url}</span>

        {entry.same_as !== undefined && (
          <p className="text-[15px] text-muted-foreground">Gleicher Link wie oben, nur einmal abgerufen.</p>
        )}
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
        {entry.state === 'closed' && (
          <>
            <p className="text-[15px]">Nichts gespeichert. Diese Versuche wurden gemacht:</p>
            <AttemptList attempts={entry.attempts ?? []} className="text-[15px]" />
          </>
        )}
        {entry.state === 'failed' && (
          <>
            {entry.unclear && (
              <p className="text-[15px]">
                Der Link hat einmal geantwortet, die Stelle sei geschlossen, andere Abrufe wurden aber abgewiesen. Ob sie
                wirklich geschlossen ist, ist unklar.
              </p>
            )}
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
