import { useId, useLayoutEffect, useRef } from 'react'
import { ListChecks, Square, X } from 'lucide-react'
import type { CheckState } from '@/api'
import { ProgressBlock } from '@/components/progress'
import { Button } from '@/components/ui/button'
import { WhyDisabled } from '@/components/why'
import { useSwapLock } from '@/lib/run'
import { cn } from '@/lib/utils'

const HINT_DEFAULT = 'Abbrechen hält nach der aktuellen Anzeige an. Was schon geprüft ist, bleibt gespeichert.'
const HINT_STOPPING = 'Wird nach der aktuellen Anzeige beendet. Was schon geprüft ist, bleibt gespeichert.'
const NOTHING_TO_CHECK = 'Nichts zu prüfen: Keine offene Anzeige hat einen Link, den die Prüfung abrufen kann.'
/** The ID of the progress hint, which the cancel button names as its description. */
const HINT_ID = 'check-why'

/** The availability check as a button that turns into its own cancel button.
 * Idle (`working` false): "Verfügbarkeit prüfen (N)" starts the check over `total` postings. With
 * `total` 0 it is `aria-disabled` (it keeps focus, a press does nothing) and a visible, focusable
 * info icon beside it says why. `working` (a check computes): the start button gives way to
 * "Prüfen abbrechen", which calls `onCancel`; both sit in one grid cell, the start button stays in
 * the layout, `invisible` and `inert`, and reserves the width, so nothing moves. `stopping` (a
 * cancel was requested): the button reads "Wird beendet…" and is `aria-disabled`. The progress
 * block's hint (`#check-why`) is the cancel button's description.
 * Swap delay and focus follow the pass button: for `SWAP_LOCK_MS` after each swap the button that
 * appeared ignores presses, and focus that was inside the button area moves with the swap. */
export function CheckButton({ total, working, stopping, onStart, onCancel }: {
  total: number
  working: boolean
  stopping: boolean
  onStart: () => void
  onCancel: () => void
}) {
  const { locked, handoff, seenWorking } = useSwapLock(working, '[data-check-area]')
  const startRef = useRef<HTMLButtonElement>(null)
  const cancelRef = useRef<HTMLButtonElement>(null)
  // Both buttons stay mounted, so the target exists at commit time; `transition-colors` keeps
  // the button that just appeared from staying `hidden` for a moment, which would refuse focus.
  useLayoutEffect(() => {
    if (handoff) (seenWorking ? cancelRef : startRef).current?.focus()
  }, [handoff, seenWorking])
  const reasonId = useId()
  const empty = total === 0
  const startDead = locked || empty
  const cancelDead = locked || stopping
  return (
    <div className="flex items-center gap-1">
      <div data-check-area className="grid">
        <Button ref={startRef} variant="outline" inert={working} aria-hidden={working || undefined}
                aria-disabled={startDead || undefined} aria-describedby={empty ? reasonId : undefined}
                onClick={() => { if (!startDead) onStart() }}
                className={cn('col-start-1 row-start-1 transition-colors', working && 'invisible',
                  empty && 'cursor-default opacity-50 hover:bg-card')}>
          <ListChecks aria-hidden="true" />Verfügbarkeit prüfen ({total})
        </Button>
        <Button ref={cancelRef} variant="outline" inert={!working} aria-hidden={!working || undefined}
                aria-disabled={cancelDead || undefined} aria-describedby={HINT_ID}
                onClick={() => { if (!cancelDead) onCancel() }}
                className={cn('col-start-1 row-start-1 transition-colors', !working && 'invisible',
                  stopping && 'cursor-default text-muted-foreground hover:bg-card')}>
          <Square aria-hidden="true" />{stopping ? 'Wird beendet…' : 'Prüfen abbrechen'}
        </Button>
      </div>
      {empty && !working && <WhyDisabled id={reasonId} label="Warum ist Prüfen nicht möglich?" reason={NOTHING_TO_CHECK} />}
    </div>
  )
}

/** The progress of a running check, below its button: "Verfügbarkeit: N von M geprüft", a bar and a
 * hint with the closed count so far and what a cancel does (or that one was requested,
 * `stopping`). `check` null (restored after a reload, no state read yet) shows no count. */
function CheckProgress({ check, stopping }: { check: CheckState | null; stopping: boolean }) {
  const total = Math.max(check?.total ?? 1, 1)
  return (
    <ProgressBlock label="Stand der Prüfung"
                   head={check ? `Verfügbarkeit: ${check.done} von ${check.total} geprüft` : 'Verfügbarkeit: Stand wird geladen…'}
                   barLabel={check ? `Prüfung: ${check.done} von ${check.total}` : 'Prüfung wird geladen'}
                   value={check?.done ?? 0} max={check ? total : 1} hintId={HINT_ID}
                   headClass="min-h-6 sm:max-lg:min-h-12"
                   hintClass={cn('min-h-10 text-muted-foreground', stopping && 'font-bold text-foreground')}
                   hint={stopping ? HINT_STOPPING : `${check ? `${check.counts.closed - check.still_closed} geschlossen bisher. ` : ''}${HINT_DEFAULT}`} />
  )
}

/** A closed posting of the report, linked to its page. */
const ClosedLink = ({ entry }: { entry: CheckState['closed'][number] }) => (
  <li>
    <a href={`#/anzeigen/${encodeURIComponent(entry.posting_id)}`} className="text-primary underline underline-offset-2">
      {entry.title}, {entry.company}
    </a>
  </li>
)

/** The report of an ended check (`done` or `cancelled`): how many postings it newly closed (the
 * ones in `check.closed`), the first three linked and the rest behind a toggle, how many were
 * available, how many stayed unknown and how many stay closed from before. `onDismiss` hides it. */
function CheckReport({ check, onDismiss }: { check: CheckState; onDismiss: () => void }) {
  const id = useId()
  const { available, unknown } = check.counts
  const closed = check.counts.closed - check.still_closed
  const [first, rest] = [check.closed.slice(0, 3), check.closed.slice(3)]
  return (
    <section aria-labelledby={id} className="flex flex-col gap-1.5 rounded-xl border bg-card px-4 py-3">
      <div className="flex items-start justify-between gap-2">
        <h2 id={id} className="text-[17px] font-bold">
          {check.status === 'cancelled' ? 'Prüfung abgebrochen' : 'Prüfung fertig'}: {closed === 1 ? '1 Stelle' : `${closed} Stellen`} neu geschlossen
        </h2>
        {/* The negative margins move the icon into the corner, level with the heading's line,
            and keep the 36 px hit area. */}
        <button type="button" aria-label="Bericht ausblenden" onClick={onDismiss}
                className="-mr-2.5 -my-1.5 inline-flex size-9 flex-none items-center justify-center rounded-lg hover:bg-muted">
          <X className="size-4" aria-hidden="true" />
        </button>
      </div>
      {first.length > 0 && (
        <ul aria-label="Geschlossene Stellen" className="list-disc pl-5 text-[15px]">
          {first.map((entry) => <ClosedLink key={entry.posting_id} entry={entry} />)}
        </ul>
      )}
      {rest.length > 0 && (
        <details className="text-[15px]">
          <summary className="cursor-pointer text-primary">{rest.length} weitere anzeigen</summary>
          <ul aria-label="Weitere geschlossene Stellen" className="list-disc pl-5">
            {rest.map((entry) => <ClosedLink key={entry.posting_id} entry={entry} />)}
          </ul>
        </details>
      )}
      <p className="text-sm text-muted-foreground">
        {available} verfügbar.
        {unknown > 0 && ` ${unknown === 1 ? '1 blieb' : `${unknown} blieben`} unbekannt, die nächste Prüfung versucht sie erneut.`}
        {check.still_closed > 0 && ` ${check.still_closed} weiterhin geschlossen.`}
      </p>
    </section>
  )
}

/** Everything below the check button, in its column: the progress while the check runs, then its
 * report, and the notices (the server forgot the check, the start or cancel failed, polling
 * failed, the check crashed). `check`, `running`, `stopping`, `lost`, `notice` and `pollFailed`
 * are `useCheck`'s; `onStart` starts a new check after a crash, `onRetryPoll` resumes polling and
 * `onDismiss` hides the report. The live region holds only text that does not change per poll,
 * so it is read once; the visible counts sit outside it. */
export function CheckStatus({ check, running, stopping, lost, notice, pollFailed, onStart, onRetryPoll, onDismiss }: {
  check: CheckState | null
  running: boolean
  stopping: boolean
  lost: boolean
  notice: string
  pollFailed: boolean
  onStart: () => void
  onRetryPoll: () => void
  onDismiss: () => void
}) {
  const reported = check && (check.status === 'done' || check.status === 'cancelled') ? check : null
  return (
    <>
      {running && !pollFailed && <CheckProgress check={check} stopping={stopping} />}
      <div role="status" className="flex flex-col gap-3">
        {running && <span className="sr-only">Die Prüfung läuft.</span>}
        {running && stopping && <span className="sr-only">Die Prüfung wird nach der aktuellen Anzeige beendet.</span>}
        {lost && (
          <p className="rounded-xl border bg-card px-4 py-3">
            Die Prüfung ist dem Server nicht mehr bekannt, er wurde wohl neu gestartet. Starte eine neue Prüfung.
          </p>
        )}
        {reported && <CheckReport check={reported} onDismiss={onDismiss} />}
      </div>
      {notice && <p role="alert" className="rounded-xl border border-danger bg-danger-soft px-4 py-3">{notice}</p>}
      {running && pollFailed && (
        <p role="alert" className="flex flex-col items-start gap-2 rounded-xl border border-danger bg-danger-soft px-4 py-3">
          Der Stand der Prüfung ist gerade nicht abrufbar. Die Prüfung läuft vielleicht weiter.
          <Button type="button" variant="outline" onClick={onRetryPoll}>Erneut versuchen</Button>
        </p>
      )}
      {check?.status === 'failed' && (
        <p role="alert" className="flex flex-col items-start gap-2 rounded-xl border border-danger bg-danger-soft px-4 py-3">
          Die Prüfung ist fehlgeschlagen. Was schon geprüft ist, bleibt gespeichert.
          <Button type="button" variant="outline" onClick={onStart}>Erneut versuchen</Button>
        </p>
      )}
    </>
  )
}
