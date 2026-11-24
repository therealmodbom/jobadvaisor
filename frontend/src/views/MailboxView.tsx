import { useCallback, useId, useState } from 'react'
import { Square } from 'lucide-react'
import { api, ApiError, type AlertEntry, type MailboxAccount, type MailboxCheckState, type MailboxMail } from '@/api'
import { AlertRunView } from '@/components/alert-run'
import { DismissButton } from '@/components/dismiss'
import { MailReport, MailboxPickList } from '@/components/mailbox-pick'
import { ProgressBlock } from '@/components/progress'
import { ErrorWithRetry, Loading } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { WhyDisabled } from '@/components/why'
import { MAILBOX_WORDS, plural } from '@/lib/alert'
import { runStore, useAlertRun } from '@/lib/alert-run'
import { dayLabel, daysBefore, whenLabel } from '@/lib/german'
import { mailboxReason, oversizedFailure } from '@/lib/mailbox'
import { useMailbox } from '@/lib/mailbox-check'
import { SETTINGS_HASH } from '@/lib/sections'
import { cn, without } from '@/lib/utils'

const MAILBOX_SECTION = `${SETTINGS_HASH}/postfach`
const PANEL = 'flex flex-col gap-3.5 rounded-xl border bg-card p-5 shadow-card'
const LINK = 'text-primary underline underline-offset-2'
const HINT_DEFAULT = 'Abbrechen hält nach der aktuellen Mail an. Die bisher gelesenen Mails bleiben in der Auswahlliste.'
const HINT_STOPPING = 'Wird nach der aktuellen Mail beendet. Die bisher gelesenen Mails bleiben in der Auswahlliste.'

/** How far back the first check reads, preset in „Mails ab“, in days. */
const FIRST_DAYS = 30

/** The alert run of the entries picked from a check, kept apart from the pasted mail's run. */
const runs = runStore('jobadvaisor.mailbox-run', 'jobadvaisor.mailbox-run-base')

/** „Alle Ordner“ or the chosen names, as the summary line says it. */
const folderSummary = (folders: MailboxAccount['folders']) => folders.names ? folders.names.join(', ') : 'Alle Ordner'

/** The source „Postfach“ of the intake view: the mailbox account in one line, „Mails ab“ before
 * the first check, „Postfach prüfen“, the progress of a running check with „Prüfen abbrechen“,
 * and the outcome: a failure with its reason, a report, and the pick list of the mails' entries
 * grouped by mail, whose chosen entries are added as one alert run (`AlertRunView`). The account
 * is read when the source is first shown (`active`); a check that runs elsewhere, or whose pick
 * list is not finished, is found through `GET /mailbox`, and its ID stays in browser storage
 * (`useMailbox`). Without a mailbox it points to the settings. `onText` and `onPdf` switch the
 * intake view to the other sources, for an entry the run could not read. */
export function MailboxView({ active, onText, onPdf }: { active: boolean; onText: () => void; onPdf: () => void }) {
  const box = useMailbox(active)
  const run = useAlertRun(runs)
  const { account, check } = box
  const [since, setSince] = useState(() => daysBefore(FIRST_DAYS))
  const [problem, setProblem] = useState('')
  const [finishing, setFinishing] = useState(false)
  const [finishFailed, setFinishFailed] = useState(false)
  /** The alert run that refused the finish, until it ends. */
  const [busyRun, setBusyRun] = useState<string | null>(null)
  /** What the last finish without entries said, until the next check starts. */
  const [flash, setFlash] = useState('')
  /** Oversized mails being read from this view, and why a reading failed, by mail key. */
  const [reading, setReading] = useState<Set<string>>(new Set())
  const [failures, setFailures] = useState<Record<string, string>>({})
  // A mail's key is its place in the check, so the next check reuses the keys: nothing local to
  // a mail outlives the check it came from.
  const [owner, setOwner] = useState(box.checkId)
  if (owner !== box.checkId) {
    setOwner(box.checkId)
    setReading(new Set())
    setFailures({})
  }
  const hintId = useId()
  const replaceId = useId()
  const whyId = useId()
  const sinceId = useId()
  const sinceHintId = useId()
  const emptyId = useId()
  const endBusy = useCallback(() => setBusyRun(null), [])

  if (run.gone || run.runId) {
    return <AlertRunView run={run} words={MAILBOX_WORDS} onText={onText} onPdf={onPdf}
                         onOver={() => { run.clear(); void box.load() }} />
  }
  if (account === null) {
    return box.accountFailed
      ? <ErrorWithRetry title="Das Postfach konnte nicht gelesen werden" onRetry={box.retryAccount} />
      : <Loading label="Postfach wird geladen" />
  }
  if (!account.configured) {
    return (
      <section aria-labelledby={emptyId} className={PANEL}>
        <h2 id={emptyId} className="text-lg font-bold">Noch kein Postfach eingerichtet</h2>
        <p className="text-muted-foreground">Richte ein Postfach ein, damit die App Job-Alert-Mails von dort lesen kann.</p>
        <a href={MAILBOX_SECTION} className={cn(LINK, 'self-start')}>Postfach einrichten</a>
      </section>
    )
  }

  /** Start a check; the first one needs the start date. */
  function startCheck() {
    if (account!.since === null && !since) {
      setProblem('Wähle das Startdatum, ab dem Mails gelesen werden.')
      return
    }
    setProblem('')
    setFlash('')
    setFinishFailed(false)
    setBusyRun(null)
    void box.start(account!.since === null ? since : null)
  }

  /** Finish the pick list with `entries`: they run as one alert run and the check is forgotten.
   * A busy alert run keeps the pick list and is shown; a check finished elsewhere, or a mail read
   * elsewhere, makes the check be read again. */
  async function finish(entries: AlertEntry[]) {
    if (finishing || !check) return
    setFinishing(true)
    setFinishFailed(false)
    try {
      const { run_id: id } = await api<{ run_id: string | null }>(`/mailbox/checks/${check.check_id}/finish`, {
        method: 'POST', json: { entries: entries.map((entry) => ({ url: entry.url, title: entry.title, force: false })) },
      })
      box.dismiss()
      if (id) run.attach(id, entries)
      else setFlash('Nichts hinzugefügt. Die Mails der Prüfung werden nicht noch einmal angeboten.')
    } catch (error) {
      if (error instanceof ApiError && error.status === 409 && typeof error.body.run_id === 'string') setBusyRun(error.body.run_id)
      else if (error instanceof ApiError && (error.status === 409 || error.status === 404)) void box.refresh()
      else setFinishFailed(true)
    } finally {
      setFinishing(false)
    }
  }

  /** Read the oversized `mail` on request and put its answer into the pick list. */
  async function readMail(mail: MailboxMail) {
    if (!check || reading.has(mail.key)) return
    setReading((now) => new Set(now).add(mail.key))
    setFailures((now) => without(now, mail.key))
    try {
      box.setMail(await api<MailboxMail>(`/mailbox/checks/${check.check_id}/mails/${mail.key}/read`, { method: 'POST' }))
    } catch (error) {
      if (error instanceof ApiError && error.status === 502) setFailures((now) => ({ ...now, [mail.key]: oversizedFailure(error.error) }))
      else if (error instanceof ApiError && (error.status === 409 || error.status === 404)) void box.refresh()
      else setFailures((now) => ({ ...now, [mail.key]: oversizedFailure(null) }))
    } finally {
      setReading((now) => {
        const next = new Set(now)
        next.delete(mail.key)
        return next
      })
    }
  }

  const { running, stopping } = box
  const failed = check?.status === 'failed' ? check : null
  const ended = check?.status === 'done' ? check : null
  const picking = ended !== null && ended.mails.length > 0
  return (
    <div className="flex flex-col gap-6">
      <section aria-label="Postfach" className={PANEL}>
        <div className="flex flex-col gap-0.5">
          <p className="font-bold">{account.user} auf {account.host}</p>
          <p className="text-[15px] text-muted-foreground">Ordner: {folderSummary(account.folders)}</p>
          <p className="text-[15px] text-muted-foreground">
            {account.last_check_at
              ? <>Letzte Prüfung: <time dateTime={account.last_check_at}>{whenLabel(account.last_check_at)}</time></>
              : 'Noch nie geprüft.'}
          </p>
          <a href={MAILBOX_SECTION} className={cn(LINK, 'self-start text-[15px]')}>Einstellungen</a>
        </div>
        {account.since === null && (
          <div className="flex flex-col gap-1">
            <label htmlFor={sinceId} className="text-sm font-bold">Mails ab</label>
            <Input id={sinceId} type="date" value={since} max={daysBefore(0)} aria-describedby={sinceHintId}
                   onChange={(event) => setSince(event.target.value)} className="w-48" />
            <span id={sinceHintId} className="text-[13px] text-muted-foreground">
              Ältere Mails werden nie gelesen. Jede Mail eines Absenders ohne feste Regel kostet einen Modellaufruf.
            </span>
          </div>
        )}
        {problem && <p role="alert" className="text-danger">{problem}</p>}
        <div className="flex flex-wrap items-center gap-1">
          <Button type="button" disabled={running} aria-describedby={running ? whyId : picking ? replaceId : undefined}
                  onClick={startCheck}>
            Postfach prüfen
          </Button>
          {running && <WhyDisabled id={whyId} label="Warum ist Prüfen nicht möglich?" reason="Es läuft schon eine Prüfung." />}
          {running && (
            <Button type="button" variant="outline" aria-describedby={hintId} aria-disabled={stopping || undefined}
                    onClick={() => { if (!stopping) void box.cancel() }}
                    className={cn(stopping && 'cursor-default text-muted-foreground hover:bg-card')}>
              <Square aria-hidden="true" />{stopping ? 'Wird beendet…' : 'Prüfen abbrechen'}
            </Button>
          )}
        </div>
        {picking && (
          <p id={replaceId} className="text-[13px] text-muted-foreground">Eine neue Prüfung ersetzt die offene Auswahlliste.</p>
        )}
        {running && !box.pollFailed && <Progress check={check} stopping={stopping} hintId={hintId} />}
      </section>

      <div role="status" className="flex flex-col gap-3">
        {running && <span className="sr-only">Die Prüfung läuft.</span>}
        {box.lost && (
          <p className="rounded-xl border bg-card px-4 py-3">
            Die Prüfung ist dem Server nicht mehr bekannt, er wurde wohl neu gestartet. Starte eine neue Prüfung.
          </p>
        )}
        {flash && <p className="rounded-xl border bg-card px-4 py-3">{flash}</p>}
      </div>
      {box.notice && <p role="alert" className="rounded-xl border border-danger bg-danger-soft px-4 py-3">{box.notice}</p>}
      {running && box.pollFailed && (
        <p role="alert" className="flex flex-col items-start gap-2 rounded-xl border border-danger bg-danger-soft px-4 py-3">
          Der Stand der Prüfung ist gerade nicht abrufbar. Die Prüfung läuft vielleicht weiter.
          <Button type="button" variant="outline" onClick={box.retryPoll}>Erneut versuchen</Button>
        </p>
      )}
      {failed && <Failure check={failed} onRetry={startCheck} />}
      {ended && (
        <>
          <MailReport check={ended} />
          {picking ? (
            <MailboxPickList key={ended.check_id} check={ended} reading={reading} failures={failures} finishing={finishing}
                             finishFailed={finishFailed} busyRun={busyRun} onBusyEnded={endBusy} onRead={readMail}
                             onAdd={finish} onNothing={() => finish([])} onText={onText} />
          ) : (
            <Nothing check={ended} since={account.since} onDismiss={box.dismiss} />
          )}
        </>
      )}
    </div>
  )
}

/** The progress of a running check: how many new mails it found and has read, a bar, and what a
 * cancel does (or that one was requested, `stopping`). `check` null (no state read yet) shows
 * the search. `hintId` is the cancel button's description. */
function Progress({ check, stopping, hintId }: { check: MailboxCheckState | null; stopping: boolean; hintId: string }) {
  const found = check && check.total > 0 ? check : null
  return (
    <ProgressBlock label="Stand der Prüfung"
                   head={found ? `${plural(found.total, 'neue Mail', 'neue Mails')} gefunden, ${found.read} gelesen` : 'Postfach wird durchsucht…'}
                   barLabel={found ? `Prüfung: ${found.read} von ${found.total} gelesen` : 'Prüfung wird vorbereitet'}
                   value={found?.read ?? 0} max={found?.total ?? 1} hintId={hintId}
                   headClass="min-h-6" hintClass={cn('min-h-10 text-muted-foreground', stopping && 'font-bold text-foreground')}
                   hint={stopping ? HINT_STOPPING : HINT_DEFAULT} />
  )
}

/** A `done` check with no mail to pick from: no new mails since `since` (nothing was read), or
 * mails read that held no posting (their report is above), with a dismiss button. A cancel before
 * the first mail says nothing more than its note above. */
function Nothing({ check, since, onDismiss }: { check: MailboxCheckState; since: string | null; onDismiss: () => void }) {
  const text = check.total === 0
    ? (check.cancelled ? null : since ? `Keine neuen Mails seit dem ${dayLabel(since)}.` : 'Keine neuen Mails.')
    : 'Die gelesenen Mails enthalten keine Anzeigen zum Auswählen.'
  return (
    <div className="flex items-start justify-between gap-2 rounded-xl border bg-card px-4 py-3">
      <p>{text ?? 'Es gibt nichts zum Auswählen.'}</p>
      <DismissButton label="Bericht ausblenden" onDismiss={onDismiss} />
    </div>
  )
}

/** A failed check: its reason in German (a crashed worker has none), „Erneut versuchen“ and the
 * way to the settings; a password the key cannot open links to entering it again. */
function Failure({ check, onRetry }: { check: MailboxCheckState; onRetry: () => void }) {
  return (
    <p role="alert" className="flex flex-col items-start gap-2 rounded-xl border border-danger bg-danger-soft px-4 py-3">
      <span>
        <strong>Die Prüfung ist fehlgeschlagen.</strong>{' '}
        {check.reason ? mailboxReason(check.reason) : 'Ein Fehler in der App hat die Prüfung beendet.'}
      </span>
      <span className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="outline" onClick={onRetry}>Erneut versuchen</Button>
        <a href={MAILBOX_SECTION} className={LINK}>
          {check.reason === 'password unreadable' ? 'Passwort neu eingeben' : 'Einstellungen öffnen'}
        </a>
      </span>
    </p>
  )
}
