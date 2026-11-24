import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronUp, LoaderCircle } from 'lucide-react'
import { api, type AlertEntry, type AlertRunState, type MailboxCheckState, type MailboxMail, type MailboxMailHead } from '@/api'
import { Note, PickRow } from '@/components/alert-pick'
import { Button } from '@/components/ui/button'
import { WhyDisabled } from '@/components/why'
import { PANEL, plural, preselected, ROW } from '@/lib/alert'
import { whenLabel } from '@/lib/german'
import { mailboxReason, oversizedFailure } from '@/lib/mailbox'
import { POLL_FAILURES, POLL_MS } from '@/lib/run'
import { cn } from '@/lib/utils'

/** An entry that cannot be picked: a stored duplicate, or a link several postings share. */
const locked = (entry: AlertEntry) => Boolean(entry.duplicate) || entry.ambiguous

/** A mail as the report names it: its sender and its subject in quotes. */
const named = (mail: MailboxMailHead) => `${mail.sender || 'Unbekannter Absender'}, „${mail.subject || 'ohne Betreff'}“`
const namedAll = (mails: MailboxMailHead[]) => mails.map(named).join('; ')

/** What a finished check reports besides its pick list, each as a short note: the mails left for
 * the next check, chosen folders that no longer exist, mails whose reading failed, mails held by
 * the content guard, mails not read while screening is off, and an interrupted connection. */
export function MailReport({ check }: { check: MailboxCheckState }) {
  return (
    <>
      {check.cancelled && <Note>Die Prüfung wurde nach {check.read} von {check.total} Mails abgebrochen.</Note>}
      {check.interrupted && (
        <Note>
          <strong>Verbindung unterbrochen:</strong> {mailboxReason(check.interrupted)} Die bis dahin gelesenen Mails sind
          verarbeitet, die übrigen liest die nächste Prüfung.
        </Note>
      )}
      {check.remaining > 0 && (
        <Note>{plural(check.remaining, 'Mail ist', 'Mails sind')} für die nächste Prüfung übrig.</Note>
      )}
      {check.missing_folders.length > 0 && (
        <Note>
          <strong>Ordner fehlen:</strong> Diese gewählten Ordner gibt es nicht mehr auf dem Server: {check.missing_folders.join(', ')}.
          Prüfe die Auswahl der Ordner in den Einstellungen.
        </Note>
      )}
      {check.failed.length > 0 && (
        <Note>
          <strong>Nicht gelesen:</strong> {namedAll(check.failed)}. Die Inhaltsprüfung oder das Modell hat nicht geantwortet.
          Die nächste Prüfung versucht es erneut.
        </Note>
      )}
      {check.held.length > 0 && (
        <Note>
          <strong>Von der Inhaltsprüfung zurückgehalten:</strong> {namedAll(check.held)}. Kein Modell hat sie gelesen, sie werden
          nicht noch einmal angeboten.
        </Note>
      )}
      {check.not_screened.length > 0 && (
        <Note>
          <strong>Nicht gelesen, solange die Inhaltsprüfung aus ist:</strong> {namedAll(check.not_screened)}. Für diese Absender
          gibt es keine feste Regel. Sobald die Inhaltsprüfung an ist, liest die nächste Prüfung sie.
        </Note>
      )}
    </>
  )
}

/** The progress of the alert run that blocked finishing the pick list (`id`), polled until it
 * ends or the server no longer knows it; then `onEnded` runs. */
function BusyRun({ id, onEnded }: { id: string; onEnded: () => void }) {
  const [state, setState] = useState<AlertRunState | null>(null)
  useEffect(() => {
    let failures = 0
    let stale = false
    const poll = () => api<AlertRunState>(`/alert-mails/runs/${id}`).then((next) => {
      if (stale) return
      failures = 0
      setState(next)
      if (next.status !== 'running') onEnded()
    }, () => {
      if (!stale && ++failures >= POLL_FAILURES) onEnded()
    })
    const timer = setInterval(poll, POLL_MS)
    poll()
    return () => {
      stale = true
      clearInterval(timer)
    }
  }, [id, onEnded])
  return (
    <section aria-label="Ein anderer Lauf rechnet" className="flex flex-col gap-1.5 rounded-[10px] bg-muted px-4 py-3">
      <p>
        <strong>Ein anderer Lauf rechnet noch</strong>
        {state && <>: {state.done} von {state.total} erledigt</>}.
        {' '}Deine Auswahl bleibt, du kannst sie danach hinzufügen.
      </p>
      <progress aria-label="Fortschritt des anderen Laufs" className="h-2 w-full accent-primary"
                value={state?.done ?? 0} max={Math.max(state?.total ?? 1, 1)} />
    </section>
  )
}

/** What a mail read on request without entries says, as the report says it of the mails read
 * during the check: held by the content guard, waiting for the screening, or no postings. */
function noEntriesNote(preview: NonNullable<MailboxMail['preview']>) {
  if (preview.held) {
    return <><strong>Von der Inhaltsprüfung zurückgehalten:</strong> Kein Modell hat die Mail gelesen, sie wird nicht noch einmal angeboten.</>
  }
  if (preview.model_skipped === 'screening off') {
    return <><strong>Nicht gelesen, solange die Inhaltsprüfung aus ist:</strong> Für diesen Absender gibt es keine feste Regel. Sobald die Inhaltsprüfung an ist, liest die nächste Prüfung die Mail.</>
  }
  return 'Die Mail enthält keine Anzeigen.'
}

/** One mail of the pick list: its head (a tri-state checkbox that selects or clears the mail's
 * selectable entries, sender, the line of subject, date and folder, „n von m ausgewählt“, the
 * collapse button), its notes and its entries. An oversized mail not read yet has an unticked
 * checkbox instead, whose ticking reads it (`onRead`); `reading` is true while that runs, and
 * `failure` is the reason of a failed reading. `on(i)` tells whether entry `i` is selected,
 * `setMany` and `toggle` change the selection, `collapsed` and `onCollapse` the fold. */
function MailItem({ mail, reading, failure, on, toggle, setMany, collapsed, onCollapse, onRead, onText }: {
  mail: MailboxMail
  reading: boolean
  failure: string | null
  on: (index: number) => boolean
  toggle: (index: number) => void
  setMany: (indexes: number[], value: boolean) => void
  collapsed: boolean
  onCollapse: () => void
  onRead: () => void
  onText: () => void
}) {
  const listId = useId()
  const box = useRef<HTMLInputElement>(null)
  const preview = mail.preview
  const entries = preview?.entries ?? []
  const selectable = entries.flatMap((entry, index) => locked(entry) ? [] : [index])
  const chosen = selectable.filter(on).length
  const all = selectable.length > 0 && chosen === selectable.length
  const some = chosen > 0 && !all
  const subject = mail.subject || 'ohne Betreff'
  const unread = preview === null
  const noChoice = !unread && selectable.length === 0
  const whyId = useId()
  useLayoutEffect(() => {
    if (box.current) box.current.indeterminate = some
  })
  return (
    <li aria-label={`Mail „${subject}“`} className="flex flex-col rounded-[10px] border">
      <div className="flex items-start gap-3 px-4 py-3 max-sm:flex-wrap">
        <input ref={box} type="checkbox" aria-label={unread ? `Mail „${subject}“ lesen` : `Alle Anzeigen der Mail „${subject}“`}
               checked={unread ? reading : all} disabled={unread ? reading : selectable.length === 0}
               aria-describedby={noChoice ? whyId : undefined}
               onChange={() => unread ? onRead() : setMany(selectable, !all)}
               className="mt-0.5 size-[22px] flex-none accent-primary disabled:cursor-not-allowed disabled:opacity-50" />
        {noChoice && (
          <div className="-mx-2 -my-2.5 flex-none">
            <WhyDisabled id={whyId} label="Warum ist die Mail nicht auswählbar?" reason="Diese Mail hat keine Anzeige, die du auswählen kannst." />
          </div>
        )}
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <p className="font-bold break-words">{mail.sender || 'Unbekannter Absender'}</p>
          <p className="flex flex-wrap gap-x-3 text-[15px] text-muted-foreground max-sm:flex-col">
            <span className="break-words">{subject}</span>
            <time dateTime={mail.date}>{whenLabel(mail.date)}</time>
            <span className="break-words">{mail.folder}</span>
          </p>
          {unread && !reading && <span className="text-[15px] font-bold">Zu groß, nicht gelesen</span>}
          {unread && !reading && !failure && (
            <span className="text-sm text-muted-foreground">Hake die Mail an, um sie zu lesen. Sie wird dann wie eine eingefügte Mail ausgewertet.</span>
          )}
          {reading && (
            <span role="status" className="flex items-center gap-2 text-[15px] font-bold">
              <LoaderCircle className="size-4 motion-safe:animate-spin" aria-hidden="true" />Wird gelesen …
            </span>
          )}
          {failure && !reading && <span role="alert" className="text-[15px] text-danger">{failure}</span>}
        </div>
        {!unread && (
          <div className="flex flex-none items-center gap-1 max-sm:w-full max-sm:justify-between max-sm:pl-[34px]">
            <span className="text-[15px] text-muted-foreground">{chosen} von {selectable.length} ausgewählt</span>
            <button type="button" aria-label={`Anzeigen der Mail „${subject}“`} aria-expanded={!collapsed} aria-controls={listId}
                    onClick={onCollapse}
                    className="inline-flex size-11 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground">
              {collapsed ? <ChevronDown className="size-5" aria-hidden="true" /> : <ChevronUp className="size-5" aria-hidden="true" />}
            </button>
          </div>
        )}
      </div>
      {preview && preview.entries.length === 0 && (
        <div className="px-4 pb-3"><Note>{noEntriesNote(preview)}</Note></div>
      )}
      {preview && preview.unread_hosts.length > 0 && (
        <div className="px-4 pb-3">
          <Note>
            <strong>Nicht gelesen:</strong>{' '}
            {preview.unread_hosts.map((item) => `${item.host} (${plural(item.links, 'Link', 'Links')})`).join(', ')}.
            {' '}Diese Links passen zu keiner festen Regel.
          </Note>
        </div>
      )}
      {preview?.truncated && (
        <div className="px-4 pb-3"><Note>Die Mail enthält mehr als 100 Stellen. Nur die ersten 100 sind aufgeführt.</Note></div>
      )}
      <ul id={listId} aria-label={`Anzeigen der Mail „${subject}“`} hidden={collapsed || unread}
          className="flex flex-col gap-2.5 px-4 pb-4">
        {entries.map((entry, index) => (
          <PickRow key={index} entry={entry} id={`${listId}-entry-${index}`} checked={on(index)} onText={onText}
                   onToggle={() => toggle(index)} />
        ))}
      </ul>
    </li>
  )
}

/** The pick list of a finished check, grouped by mail, with „N Anzeigen hinzufügen“ and „Nichts
 * hinzufügen“. The selection and the folds are kept here, so mount it with the check's ID as its
 * `key`. New entries (`preselected`) start selected, also those of an oversized mail once read.
 * `onAdd` and `onNothing` finish the check; `onRead` reads an oversized mail, which `reading`
 * (keys read here) and `failures` (key to reason) describe, beside the check's own `reading`
 * flags (read in another tab). While a mail is read, or `busyRun` (an alert run that refused the
 * finish) computes, adding waits and a visible info icon says why; `finishing` waits for the
 * answer and `finishFailed` says it did not come. `onBusyEnded` runs when that run is over. */
export function MailboxPickList({ check, reading, failures, finishing, finishFailed, busyRun, onBusyEnded, onRead, onAdd, onNothing, onText }: {
  check: MailboxCheckState
  reading: Set<string>
  failures: Record<string, string>
  finishing: boolean
  finishFailed: boolean
  busyRun: string | null
  onBusyEnded: () => void
  onRead: (mail: MailboxMail) => void
  onAdd: (entries: AlertEntry[]) => void
  onNothing: () => void
  onText: () => void
}) {
  /** Choices the user made, by `<mail key>:<entry index>`; the rest follows `preselected`. */
  const [picked, setPicked] = useState<Map<string, boolean>>(new Map())
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const addWhy = useId()
  const nothingWhy = useId()
  const on = (mail: MailboxMail, index: number) => {
    const entry = mail.preview?.entries[index]
    return !!entry && !locked(entry) && (picked.get(`${mail.key}:${index}`) ?? preselected(entry))
  }
  const chosen = check.mails.flatMap((mail) => (mail.preview?.entries ?? []).filter((_, index) => on(mail, index)))
  const reads = check.mails.some((mail) => mail.reading) || reading.size > 0
  const addReason = reads ? 'Eine zu große Mail wird gerade gelesen.'
    : busyRun ? 'Ein anderer Lauf rechnet noch. Danach kannst du die Auswahl hinzufügen.'
      : chosen.length === 0 ? 'Wähle mindestens eine Anzeige aus.' : null
  const nothingBlocked = reads || finishing
  const setMany = (mail: MailboxMail, indexes: number[], value: boolean) => setPicked((now) => {
    const next = new Map(now)
    indexes.forEach((index) => next.set(`${mail.key}:${index}`, value))
    return next
  })
  const fold = (key: string) => setCollapsed((now) => {
    const next = new Set(now)
    if (!next.delete(key)) next.add(key)
    return next
  })
  return (
    <section aria-label="Auswahlliste" className={cn(PANEL, 'min-w-0')}>
      {finishFailed && (
        <p role="alert" className={cn(ROW, 'border-danger bg-danger-soft')}>
          Die Anzeigen konnten nicht hinzugefügt werden. Ist der Server erreichbar? Die Auswahl bleibt, du kannst es noch einmal versuchen.
        </p>
      )}
      {busyRun && <BusyRun id={busyRun} onEnded={onBusyEnded} />}
      <ul aria-label="Mails der Prüfung" className="flex flex-col gap-3">
        {check.mails.map((mail) => (
          <MailItem key={mail.key} mail={mail} reading={reading.has(mail.key) || mail.reading}
                    failure={mail.preview !== null ? null
                      : mail.read_failed ? oversizedFailure(mail.read_failed) : failures[mail.key] ?? null}
                    on={(index) => on(mail, index)}
                    toggle={(index) => setMany(mail, [index], !on(mail, index))}
                    setMany={(indexes, value) => setMany(mail, indexes, value)}
                    collapsed={collapsed.has(mail.key)} onCollapse={() => fold(mail.key)}
                    onRead={() => onRead(mail)} onText={onText} />
        ))}
      </ul>
      <div className="flex flex-col gap-2 border-t pt-3.5 sm:flex-row sm:flex-wrap sm:items-center">
        <div className="flex items-center gap-1">
          <Button type="button" disabled={addReason !== null || finishing} aria-describedby={addReason ? addWhy : undefined}
                  onClick={() => onAdd(chosen)}>
            {plural(chosen.length, 'Anzeige', 'Anzeigen')} hinzufügen
          </Button>
          {addReason && <WhyDisabled id={addWhy} label="Warum ist Hinzufügen nicht möglich?" reason={addReason} />}
        </div>
        <div className="flex items-center gap-1">
          <Button type="button" variant="outline" disabled={nothingBlocked}
                  aria-describedby={reads ? nothingWhy : undefined} onClick={onNothing}>
            Nichts hinzufügen
          </Button>
          {reads && <WhyDisabled id={nothingWhy} label="Warum ist Nichts hinzufügen nicht möglich?" reason="Eine zu große Mail wird gerade gelesen." />}
        </div>
      </div>
      <p className="text-sm text-muted-foreground">
        Die Anzeigen werden nacheinander abgerufen. Danach gelten die Mails dieser Prüfung als gelesen und werden nicht noch
        einmal angeboten, auch die, aus denen du nichts hinzufügst.
      </p>
    </section>
  )
}
