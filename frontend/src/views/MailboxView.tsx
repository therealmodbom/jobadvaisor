import { useId, useState } from 'react'
import { Square } from 'lucide-react'
import type { MailboxAccount, MailboxCheckState } from '@/api'
import { Note } from '@/components/alert-pick'
import { DismissButton } from '@/components/dismiss'
import { ProgressBlock } from '@/components/progress'
import { ErrorWithRetry, Loading } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { WhyDisabled } from '@/components/why'
import { plural } from '@/lib/alert'
import { dayLabel, daysBefore, whenLabel } from '@/lib/german'
import { mailboxReason } from '@/lib/mailbox'
import { useMailbox } from '@/lib/mailbox-check'
import { SETTINGS_HASH } from '@/lib/sections'
import { cn } from '@/lib/utils'

const MAILBOX_SECTION = `${SETTINGS_HASH}/postfach`
const PANEL = 'flex flex-col gap-3.5 rounded-xl border bg-card p-5 shadow-card'
const LINK = 'text-primary underline underline-offset-2'
const HINT_DEFAULT = 'Abbrechen hält nach der aktuellen Mail an. Die bisher gelesenen Mails bleiben in der Auswahlliste.'
const HINT_STOPPING = 'Wird nach der aktuellen Mail beendet. Die bisher gelesenen Mails bleiben in der Auswahlliste.'

/** How far back the first check reads, preset in „Mails ab“, in days. */
const FIRST_DAYS = 30

/** „Alle Ordner“ or the chosen names, as the summary line says it. */
const folderSummary = (folders: MailboxAccount['folders']) => folders.names ? folders.names.join(', ') : 'Alle Ordner'

/** The source „Postfach“ of the intake view: the mailbox account in one line, „Mails ab“ before
 * the first check, „Postfach prüfen“, the progress of a running check with „Prüfen abbrechen“,
 * and the outcome (no new mails, a cancel, a failure with its reason). The account is read when
 * the source is first shown (`active`); a check that runs elsewhere, or whose pick list is not
 * finished, is found through `GET /mailbox`, and its ID stays in browser storage (`useMailbox`).
 * Without a mailbox it points to the settings. */
export function MailboxView({ active }: { active: boolean; onText: () => void; onPdf: () => void }) {
  const box = useMailbox(active)
  const { account, check } = box
  const [since, setSince] = useState(() => daysBefore(FIRST_DAYS))
  const [problem, setProblem] = useState('')
  const hintId = useId()
  const whyId = useId()
  const sinceId = useId()
  const sinceHintId = useId()
  const emptyId = useId()

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
    void box.start(account!.since === null ? since : null)
  }

  const { running, stopping } = box
  const failed = check?.status === 'failed' ? check : null
  const ended = check?.status === 'done' ? check : null
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
          <Button type="button" disabled={running} aria-describedby={running ? whyId : undefined} onClick={startCheck}>
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
        {running && !box.pollFailed && <Progress check={check} stopping={stopping} hintId={hintId} />}
      </section>

      <div role="status" className="flex flex-col gap-3">
        {running && <span className="sr-only">Die Prüfung läuft.</span>}
        {box.lost && (
          <p className="rounded-xl border bg-card px-4 py-3">
            Die Prüfung ist dem Server nicht mehr bekannt, er wurde wohl neu gestartet. Starte eine neue Prüfung.
          </p>
        )}
        {ended && <Outcome check={ended} since={account.since} onDismiss={box.dismiss} />}
      </div>
      {box.notice && <p role="alert" className="rounded-xl border border-danger bg-danger-soft px-4 py-3">{box.notice}</p>}
      {running && box.pollFailed && (
        <p role="alert" className="flex flex-col items-start gap-2 rounded-xl border border-danger bg-danger-soft px-4 py-3">
          Der Stand der Prüfung ist gerade nicht abrufbar. Die Prüfung läuft vielleicht weiter.
          <Button type="button" variant="outline" onClick={box.retryPoll}>Erneut versuchen</Button>
        </p>
      )}
      {failed && <Failure check={failed} onRetry={startCheck} />}
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

/** What a `done` check left: for a cancel the note after how many mails it stopped, and without
 * any mail to pick from the plain statement that nothing is new since `since`, with a dismiss
 * button for the report. */
function Outcome({ check, since, onDismiss }: { check: MailboxCheckState; since: string | null; onDismiss: () => void }) {
  const nothing = check.mails.length === 0
  return (
    <>
      {check.cancelled && <Note>Die Prüfung wurde nach {check.read} von {check.total} Mails abgebrochen.</Note>}
      {nothing && !check.cancelled && check.total === 0 && (
        <div className="flex items-start justify-between gap-2 rounded-xl border bg-card px-4 py-3">
          <p>{since ? `Keine neuen Mails seit dem ${dayLabel(since)}.` : 'Keine neuen Mails.'}</p>
          <DismissButton label="Bericht ausblenden" onDismiss={onDismiss} />
        </div>
      )}
    </>
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
