import { Check, CircleAlert, CloudUpload, Info, LoaderCircle } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { whenText, type BackupFailure, type BackupState, type BackupStatus, type BackupStep } from '@/lib/backup'
import { cn } from '@/lib/utils'

/** The last successful backup as a phrase: "zuletzt heute, 09:12" or "noch keine Sicherung". */
const lastBackup = (status: BackupStatus) =>
  status.last_success ? `zuletzt ${whenText(status.last_success)}` : 'noch keine Sicherung'

/** A result this recent still counts as "just now". */
const JUST_NOW_MS = 60_000

/** The German sentence for why the backup is unavailable, from the backend's reason. */
function unavailableText(reason: string): string {
  if (/not a git repository|not the top level/.test(reason)) {
    return 'Das Datenverzeichnis ist kein eigenes Git-Repository. Sichern braucht ein Git-Repository '
      + 'mit dem Datenverzeichnis als oberster Ebene.'
  }
  if (/not installed/.test(reason)) return 'Git ist auf diesem Rechner nicht installiert.'
  return `Sichern ist hier nicht möglich: ${reason}`
}

/** The German sentence for a refused press, from the backend's detail. */
function refusalText(detail: string): string {
  const branch = /^on branch (.+)$/.exec(detail)
  if (branch) return `Sichern geht nur auf main; das Repository steht auf „${branch[1]}“.`
  if (detail === 'on a detached HEAD') {
    return 'Sichern geht nur auf main; das Repository steht auf keinem Branch.'
  }
  const operation = /^a (.+) is in progress$/.exec(detail)
  if (operation) return `Sichern geht nicht: ein ${operation[1]} ist noch nicht abgeschlossen.`
  return `Sichern geht nicht: ${detail}`
}

/** The failure toggle and its panel: a small red button that says what did not work, and the
 * explanation with git's message and the times. The panel closes with a second press, Escape or a
 * click outside. */
function FailureToggle({ failure, status }: { failure: BackupFailure; status: BackupStatus }) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const panelId = useId()
  const push = failure.step === 'push'
  useEffect(() => {
    if (!open) return
    const close = (event: Event) => {
      if (event instanceof KeyboardEvent ? event.key === 'Escape'
          : !root.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('keydown', close)
    document.addEventListener('mousedown', close)
    return () => {
      document.removeEventListener('keydown', close)
      document.removeEventListener('mousedown', close)
    }
  }, [open])
  return (
    <div ref={root} className="relative">
      <button type="button" aria-expanded={open} aria-controls={open ? panelId : undefined}
              onClick={() => setOpen(!open)}
              className="inline-flex items-center gap-1.5 rounded-md bg-danger-soft px-2 py-1.5 text-sm font-bold text-danger">
        <CircleAlert className="size-3.5" aria-hidden="true" />
        {push ? 'Nicht gepusht' : 'Nicht gesichert'}
      </button>
      {open && (
        <div id={panelId} role="dialog" aria-label={push ? 'Push fehlgeschlagen' : 'Sichern fehlgeschlagen'}
             className="absolute top-full right-0 z-20 mt-2 flex w-[min(360px,calc(100vw-32px))] flex-col gap-2.5 rounded-xl border bg-card p-4 shadow-card">
          <p className="font-bold">{push ? 'Push hat nicht geklappt' : 'Sichern hat nicht geklappt'}</p>
          <p className="text-sm text-muted-foreground">
            {push
              ? 'Deine Änderungen sind lokal committet und gehen nicht verloren. Der Push zum Remote hat nicht geklappt – versuch es noch einmal.'
              : 'Deine Änderungen liegen noch im Datenverzeichnis und gehen nicht verloren. Git hat das Committen abgelehnt – versuch es noch einmal.'}
          </p>
          <code className="block rounded-lg bg-background px-3 py-2 font-mono text-[13px] leading-[18px] whitespace-pre-wrap break-words">
            {failure.reason}
          </code>
          <span className="text-sm text-muted-foreground">
            Letzter Versuch: {whenText(failure.at)} · zuletzt gesichert:{' '}
            {status.last_success ? whenText(status.last_success) : 'noch nie'}
          </span>
        </div>
      )}
    </div>
  )
}

/** The info icon beside a disabled button: a focusable button that shows `reason` on focus, on
 * hover and when pressed, so the reason never depends on a mouse. */
function WhyUnavailable({ reason }: { reason: string }) {
  const [pinned, setPinned] = useState(false)
  const [near, setNear] = useState(false)
  const id = useId()
  return (
    <span className="relative inline-flex" onMouseEnter={() => setNear(true)} onMouseLeave={() => setNear(false)}>
      <button type="button" aria-label="Warum ist Sichern nicht möglich?" aria-describedby={id}
              onClick={() => setPinned(!pinned)} onFocus={() => setNear(true)}
              onBlur={() => { setNear(false); setPinned(false) }}
              className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground">
        <Info className="size-4" aria-hidden="true" />
      </button>
      {(near || pinned) && (
        <span id={id} role="tooltip"
              className="absolute top-full right-0 z-20 mt-2 w-[min(320px,calc(100vw-32px))] rounded-lg border bg-card px-3 py-2 text-sm shadow-card">
          {unavailableText(reason)}
        </span>
      )}
    </span>
  )
}

/** The status line left of the button, in words, for a status without a failure. */
function statusLine(status: BackupStatus, refusal: string | null): { text: string; tone?: 'success' | 'danger' } {
  if (refusal) return { text: refusalText(refusal), tone: 'danger' }
  if (status.running) return { text: 'wird gesichert…' }
  const count = status.uncommitted + status.unpushed
  if (status.pending) {
    return { text: `${count} ${count === 1 ? 'Änderung' : 'Änderungen'} nicht gesichert · ${lastBackup(status)}` }
  }
  const result = status.last_result
  const fresh = result !== null && Date.now() - new Date(result.at).getTime() < JUST_NOW_MS
  if (fresh && result.result === 'pushed') return { text: 'Gepusht, gerade eben', tone: 'success' }
  if (fresh && result.result === 'up_to_date') return { text: 'Schon alles gesichert, gerade eben', tone: 'success' }
  if (status.remote === null) {
    return { text: `Nur lokal committet – kein Remote eingerichtet · ${lastBackup(status)}` }
  }
  return { text: lastBackup(status) }
}

/** The backup control of the app header: the status line, the button and, after a failure, the
 * toggle with its panel. The button is filled while something is not backed up and quiet
 * otherwise, and stays enabled for a retry after a failure; it is disabled while a backup runs
 * and, with an info icon that gives the reason, while the backup is unavailable. Renders nothing
 * before the first status has arrived. */
export function BackupControl({ state }: { state: BackupState }) {
  const { status, unavailable, refusal, press } = state
  if (unavailable !== null) {
    return (
      <div className="flex items-center gap-2">
        <Button variant="outline" disabled><CloudUpload aria-hidden="true" />Sichern</Button>
        <WhyUnavailable reason={unavailable} />
      </div>
    )
  }
  if (status === null) return null
  const failure = status.last_failure
  const count = status.uncommitted + status.unpushed
  const line = failure && !refusal && !status.running ? null : statusLine(status, refusal)
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      {line && (
        <span className={cn('inline-flex items-center gap-1.5 text-sm',
          line.tone === 'success' ? 'text-success' : line.tone === 'danger' ? 'text-danger' : 'text-muted-foreground')}>
          {line.tone === 'success' && <Check className="size-3.5" aria-hidden="true" />}
          {line.text}
        </span>
      )}
      {failure && !status.running && <FailureToggle failure={failure} status={status} />}
      {status.running ? (
        <Button disabled><LoaderCircle className="animate-spin" aria-hidden="true" />Sichern ({count})</Button>
      ) : status.pending ? (
        <Button onClick={press}>
          <CloudUpload aria-hidden="true" />
          {failure ? 'Erneut sichern' : 'Sichern'} ({count})
        </Button>
      ) : (
        <Button variant="outline" onClick={press} aria-label="Gesichert – jetzt erneut sichern">
          <Check className="text-success" aria-hidden="true" />Gesichert
        </Button>
      )}
    </div>
  )
}

const STEPS: Record<BackupStep, string> = {
  staging: 'Vorbereiten', committing: 'Committen', pushing: 'Pushen zum Remote',
}
const ORDER: BackupStep[] = ['staging', 'committing', 'pushing']

/** The thin strip under the header while a backup runs: the step ("Schritt 3 von 3: Pushen zum
 * Remote", of two without a remote), the number of files and, while pushing, the share git
 * reports as done, with a bar once there is one. Renders nothing otherwise. */
export function BackupStrip({ status }: { status: BackupStatus | null }) {
  if (!status?.running || !status.progress) return null
  const { step, files, percent } = status.progress
  const total = status.remote === null ? 2 : 3
  const detail = [files > 0 ? `${files} ${files === 1 ? 'Datei' : 'Dateien'}` : null,
                  percent !== null ? `${percent} %` : null].filter(Boolean).join(' · ')
  return (
    <div role="status" aria-label="Fortschritt der Sicherung" className="border-b bg-positive-soft">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-1.5 px-6 py-3">
        <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 text-sm">
          <span className="font-bold">Schritt {ORDER.indexOf(step) + 1} von {total}: {STEPS[step]}</span>
          <span className="text-muted-foreground">{detail}</span>
        </div>
        {percent !== null && (
          <div aria-hidden="true" className="h-1.5 rounded-full bg-card">
            <div className="h-1.5 rounded-full bg-primary" style={{ width: `${percent}%` }} />
          </div>
        )}
      </div>
    </div>
  )
}
