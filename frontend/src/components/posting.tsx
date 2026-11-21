import { useId, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Check, ExternalLink, Info, LoaderCircle, Trash2 } from 'lucide-react'
import { AlertDialog } from 'radix-ui'
import { api, ApiError, deletePosting, type Availability, type AvailabilityChoice, type Label, type PoolRow, type Posting, type ReasonChip, type Status } from '@/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { WhyDisabled } from '@/components/why'
import { categoryNames, STATUSES, whenLabel } from '@/lib/german'
import { LEVELS } from '@/lib/rating'
import type { ScoreCall } from '@/lib/score'
import { cn } from '@/lib/utils'

/** A link to the original posting, for http(s) URLs only; `label` is its text (default
 * "Originalanzeige öffnen"). */
export function OriginalLink({ url, label = 'Originalanzeige öffnen' }: { url: string | null | undefined; label?: string }) {
  if (!url || !/^https?:\/\//i.test(url)) return null
  return (
    <a href={url} target="_blank" rel="noreferrer"
       className="inline-flex items-center gap-1 text-[15px] text-primary underline underline-offset-2 [overflow-wrap:anywhere]">
      {label}<ExternalLink className="size-3.5 flex-none" aria-hidden="true" />
    </a>
  )
}

/** The posting's full text, collapsed until opened. */
export function PostingText({ text }: { text: string | undefined }) {
  if (!text) return null
  return (
    <details className="rounded-lg border bg-background px-3 py-2">
      <summary className="cursor-pointer text-sm font-bold">Anzeigentext</summary>
      <p className="mt-2 max-w-[80ch] text-[15px] whitespace-pre-line">{text}</p>
    </details>
  )
}

/** The application status as a select, shared by pool rows and the posting page. `id` ids the
 * select and `title` names the posting for screen readers; `onStatus` sends a new status.
 * `saving` shows the save (the select stays enabled so keyboard focus is not dropped; a change
 * meanwhile is ignored), `failed` (the status that did not save) an error with a retry. */
export function StatusControl({ id, title, value, saving, failed, onStatus }: {
  id: string
  title: string
  value: Status
  saving: boolean
  failed: Status | undefined
  onStatus: (status: Status) => void
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-bold">Bewerbungsstatus</label>
      <select id={id} value={value} aria-busy={saving} aria-label={`Bewerbungsstatus: ${title}`}
              onChange={(event) => !saving && onStatus(event.target.value as Status)}
              className="min-h-11 rounded-lg border border-input bg-background px-2.5 text-[15px]">
        {STATUSES.map(([option, label]) => <option key={option} value={option}>{label}</option>)}
      </select>
      {saving && <span role="status" className="text-sm text-muted-foreground">wird gespeichert…</span>}
      {failed && (
        <span role="alert" className="flex flex-col items-start gap-1 text-sm text-danger">
          Der Bewerbungsstatus wurde nicht gespeichert.
          <Button type="button" variant="outline" size="sm" onClick={() => onStatus(failed)}>Erneut versuchen</Button>
        </span>
      )}
    </div>
  )
}

/** The availability on the posting page as a select with its note, next to `StatusControl`. The
 * user can set "verfügbar" or "geschlossen"; "nicht geprüft" (`value` null) and "unbekannt" (a
 * check could not tell) are shown but not choosable. The note says when the availability was set
 * and by whom ("laut Prüfung vom …", "von dir gesetzt am …, die nächste Prüfung prüft neu") or that
 * it was never checked. A posting no check can read (`checkable` false: pasted text, a PDF, or
 * only login-walled or non-public links) is never checked, so its note promises no check
 * ("kein prüfbarer Link, wird nicht geprüft", "von dir gesetzt am …"). A check covers open postings
 * only, so a hand setting promises the next check only while `open` (application status open).
 * `onChange` sends the choice. `saving` shows the save (the select stays enabled so keyboard focus is not dropped; a
 * change meanwhile is ignored), `failed` (the choice that did not save) an error with a retry. */
export function AvailabilityControl({ id, value, checkable, open, saving, failed, onChange }: {
  id: string
  value: Availability | null
  checkable: boolean
  open: boolean
  saving: boolean
  failed: AvailabilityChoice | undefined
  onChange: (choice: AvailabilityChoice) => void
}) {
  const shown = value?.state ?? 'never'
  const change = (choice: AvailabilityChoice) => { if (!saving) onChange(choice) }
  return (
    <div className="flex flex-col items-start gap-1">
      <label htmlFor={id} className="text-sm font-bold">Verfügbarkeit</label>
      <select id={id} value={shown} aria-busy={saving}
              onChange={(event) => change(event.target.value as AvailabilityChoice)}
              className="min-h-11 rounded-lg border border-input bg-background px-2.5 text-[15px]">
        <option value="available">verfügbar</option>
        <option value="closed">geschlossen</option>
        {shown === 'unknown' && <option value="unknown" disabled>unbekannt</option>}
        {shown === 'never' && <option value="never" disabled>nicht geprüft</option>}
      </select>
      <span className="text-[13px] text-muted-foreground">
        {!value ? (checkable ? 'noch nie geprüft' : 'kein prüfbarer Link, wird nicht geprüft')
          : value.set_by === 'check' ? `laut Prüfung vom ${whenLabel(value.set_at)}`
            : `von dir gesetzt am ${whenLabel(value.set_at)}${checkable && open ? ', die nächste Prüfung prüft neu' : ''}`}
      </span>
      {saving && <span role="status" className="text-sm text-muted-foreground">wird gespeichert…</span>}
      {failed && (
        <span role="alert" className="flex flex-col items-start gap-1 text-sm text-danger">
          Die Verfügbarkeit wurde nicht gespeichert.
          <Button type="button" variant="outline" size="sm" onClick={() => onChange(failed)}>Erneut versuchen</Button>
        </span>
      )}
    </div>
  )
}

/** What refuses a delete: a pass or a single score computes (`scoring`) or an availability check
 * runs (`check`). The pool view derives it from its pass and check state, the posting page gets
 * it as `delete_blocked`. */
export type DeleteBlock = 'scoring' | 'check'

const DELETE_REASONS: Record<DeleteBlock, string> = {
  scoring: 'Gerade läuft ein Score-Durchlauf. Löschen geht wieder, wenn er fertig ist.',
  check: 'Gerade läuft eine Verfügbarkeitsprüfung. Löschen geht wieder, wenn sie fertig ist.',
}
/** The API's 409 `error` for each `DeleteBlock`. */
const DELETE_REFUSALS: Record<string, DeleteBlock> = { 'scoring in progress': 'scoring', 'check in progress': 'check' }
const DELETE_FAILED = 'Löschen hat nicht geklappt. Versuch es noch einmal.'

/** The rating level `label` names in the delete dialog ("Ja, auf jeden Fall"; "Ja" or "Nein" for a
 * verdict without a strength), or null for no rating (no label, or an import that is no preference). */
function levelText(label: Label | null): string | null {
  if (!label?.verdict) return null
  const level = LEVELS.find(({ verdict, strength }) => verdict === label.verdict && strength === label.strength)
  return level?.label ?? (label.verdict === 'positive' ? 'Ja' : 'Nein')
}

/** The modal that confirms a delete of `row`, opened by `children`, the trigger button (focus
 * returns to it on close). It names title and company, and the rating level when there is one.
 * "Abbrechen" has the focus on open; Escape closes it without a request, but not while one runs. "Endgültig löschen" sends
 * one `DELETE` however often it is pressed. A 409 shows the matching reason in the dialog, which
 * stays open; any other failure says so and the button stays usable; a 404 (already gone) counts
 * as deleted. After a delete the dialog closes without handing focus back (the trigger is gone;
 * `onDeleted` places it) and `onDeleted` runs. */
export function DeleteDialog({ row, onDeleted, children }: {
  row: Pick<PoolRow, 'posting_id' | 'title' | 'company' | 'label'>
  onDeleted: () => void
  children: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const [sending, setSending] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  /** Blocks a second request in the same tick, before `sending` has rendered. */
  const guard = useRef(false)
  /** Set once the delete went through: the trigger is gone then, so the close must not move focus
   * (`onDeleted` places it). */
  const deleted = useRef(false)
  const level = levelText(row.label)

  async function remove() {
    if (guard.current) return
    guard.current = true
    setSending(true)
    setProblem(null)
    try {
      await deletePosting(row.posting_id)
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) {
        const block = error instanceof ApiError && error.status === 409 ? DELETE_REFUSALS[error.error] : undefined
        setProblem(block ? DELETE_REASONS[block] : DELETE_FAILED)
        guard.current = false
        setSending(false)
        return
      }
    }
    guard.current = false
    deleted.current = true
    setSending(false)
    setOpen(false)
    onDeleted()
  }

  return (
    // While the request runs the dialog cannot be closed (Escape, "Abbrechen", a click outside), so the
    // user sees how it ended.
    <AlertDialog.Root open={open} onOpenChange={(next) => {
      if (!next && guard.current) return
      setOpen(next)
      if (!next) setProblem(null)
    }}>
      <AlertDialog.Trigger asChild>{children}</AlertDialog.Trigger>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-50 bg-foreground/40" />
        <AlertDialog.Content onCloseAutoFocus={(event) => { if (deleted.current) event.preventDefault() }}
          className="fixed top-1/2 left-1/2 z-50 flex w-[min(440px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 rounded-xl border bg-card p-6 shadow-card">
          <AlertDialog.Title className="text-xl font-bold">Anzeige löschen?</AlertDialog.Title>
          <AlertDialog.Description asChild>
            <div className="flex flex-col gap-2">
              <p><strong>{row.title}</strong> ({row.company}) wird endgültig gelöscht, mit ihrem Score.</p>
              {level && (
                <p>
                  Du hast sie mit <strong>„{level}“</strong> bewertet. Die Bewertung geht mit verloren und zählt danach
                  nicht mehr als Beispiel fürs Scoren.
                </p>
              )}
            </div>
          </AlertDialog.Description>
          {problem && <p role="alert" className="text-danger">{problem}</p>}
          <div className="flex flex-wrap justify-end gap-2">
            <AlertDialog.Cancel asChild>
              <Button type="button" variant="outline" aria-disabled={sending || undefined}
                      className={cn(sending && 'cursor-not-allowed opacity-50')}>Abbrechen</Button>
            </AlertDialog.Cancel>
            <Button type="button" variant="destructive" aria-disabled={sending || undefined}
                    className={cn(sending && 'cursor-not-allowed opacity-50')} onClick={() => void remove()}>
              <Trash2 aria-hidden="true" />Endgültig löschen
            </Button>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}

/** The trash button of a pool row or the posting page: an icon button named "Anzeige löschen" that
 * opens `DeleteDialog` for `row`; `onDeleted` runs after the delete. While `blocked` the button is
 * `disabled` and a visible, focusable info icon beside it gives the reason (on hover and on focus,
 * and to screen readers through the button's description). `className` places the group, for
 * example `mt-6` to line it up with a select that has a label above. */
export function DeleteButton({ row, blocked, onDeleted, className }: {
  row: Pick<PoolRow, 'posting_id' | 'title' | 'company' | 'label'>
  blocked: DeleteBlock | null
  onDeleted: () => void
  className?: string
}) {
  const reasonId = useId()
  const button = (
    <Button type="button" variant="outline" aria-label="Anzeige löschen" disabled={blocked !== null}
            aria-describedby={blocked ? reasonId : undefined} className="size-11 flex-none px-0 text-danger">
      <Trash2 className="size-5" aria-hidden="true" />
    </Button>
  )
  return (
    <div className={cn('flex items-center gap-1', className)}>
      {blocked ? button : <DeleteDialog row={row} onDeleted={onDeleted}>{button}</DeleteDialog>}
      {blocked && <WhyDisabled id={reasonId} label="Warum ist Löschen nicht möglich?" reason={DELETE_REASONS[blocked]} />}
    </div>
  )
}

const FIELDS = [['title', 'Titel'], ['company', 'Firma'], ['location_raw', 'Ort']] as const
type Field = (typeof FIELDS)[number][0]

/** The form that corrects a posting's title, company and location through `PATCH /postings/{id}`.
 * `posting` holds the stored values the inputs start from; only changed fields are sent, an empty
 * one is refused. `onSaved` gets the stored posting after a save (also when nothing changed).
 * `children` sit beside the save button, for links or a cancel button. */
export function PostingFields({ postingId, posting, onSaved, children }: {
  postingId: string
  posting: Posting
  onSaved: (posting: Posting) => void
  children?: ReactNode
}) {
  const uid = useId()
  const [values, setValues] = useState<Record<Field, string>>(() => ({
    title: posting.title, company: posting.company, location_raw: posting.location_raw }))
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'empty' | 'error'>('idle')

  async function save(event: FormEvent) {
    event.preventDefault()
    if (FIELDS.some(([key]) => !values[key].trim())) return setSaveState('empty')
    const changed = Object.fromEntries(FIELDS.map(([key]) => [key, values[key].trim()])
      .filter(([key, value]) => value !== posting[key as Field]))
    if (Object.keys(changed).length === 0) {
      setSaveState('saved')
      return onSaved(posting)
    }
    setSaveState('saving')
    try {
      const updated = await api<{ posting: Posting }>(`/postings/${encodeURIComponent(postingId)}`,
                                                      { method: 'PATCH', json: changed })
      setSaveState('saved')
      onSaved(updated.posting)
    } catch {
      setSaveState('error')
    }
  }

  return (
    <form onSubmit={save} className="flex flex-col gap-4">
      <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3.5">
        {FIELDS.map(([key, label]) => (
          <div key={key} className={cn('flex flex-col gap-1.5', key === 'title' && 'col-span-full')}>
            <label htmlFor={`${uid}-${key}`} className="text-sm font-bold">{label}</label>
            <Input id={`${uid}-${key}`} value={values[key]}
                   onChange={(event) => {
                     setValues({ ...values, [key]: event.target.value })
                     setSaveState('idle')
                   }} />
          </div>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={saveState === 'saving'}>Korrekturen speichern</Button>
        {children}
        {saveState === 'saved' && (
          <span role="status" className="inline-flex items-center gap-1.5 font-bold text-success">
            <Check className="size-4" strokeWidth={3} aria-hidden="true" />Korrekturen gespeichert
          </span>
        )}
        {saveState === 'error' && (
          <span role="alert" className="text-danger">Speichern hat nicht geklappt. Versuch es noch einmal.</span>
        )}
        {saveState === 'empty' && (
          <span role="alert" className="text-danger">Titel, Firma und Ort dürfen nicht leer sein.</span>
        )}
      </div>
    </form>
  )
}

/** The score cell of a pool row or the posting page: held and excluded reasons, an unreadable
 * score, "noch kein Score", or the score out of 10. */
export function ScoreText({ row }: { row: PoolRow }) {
  if (row.state === 'held') return <>zurückgehalten: {categoryNames(row.categories)}</>
  if (row.state === 'excluded') return <>ausgeschlossen: {row.rules.join(', ')}</>
  if (row.score_problem) return <>Score unlesbar<span className="sr-only">: {row.score_problem}</span></>
  if (row.state === 'unscored' || row.score === null) return <>noch kein Score</>
  return <><span className="text-2xl font-bold tabular-nums">{row.score}</span>/10</>
}

/** Why a posting cannot be scored now, as the info text, or null when it can. A posting both held
 * and excluded shows the content guard (the pool's order). `screening` is whether a classifier is
 * configured: without one, a posting the guard never checked cannot be scored. */
function blockedReason(row: PoolRow, screening: boolean): string | null {
  if (row.state === 'held') {
    const names = categoryNames(row.categories)
    return `Der Inhaltsfilter hält diese Anzeige zurück${names ? ` (Verdacht: ${names})` : ''}. Erst nach einer Freigabe kann sie einen Score bekommen.`
  }
  if (row.state === 'excluded') {
    return `Eine Ausschlussregel greift: ${row.rules.join(', ')}. Ausgeschlossene Anzeigen bekommen keinen Score.`
  }
  if (row.unscreened && !screening) {
    return 'Der Inhaltsfilter hat diese Anzeige nie geprüft, und es ist kein Filter eingerichtet. Ohne Prüfung bekommt sie keinen Score.'
  }
  return null
}

/** The button that scores one posting now: "Score berechnen" (or "Neu berechnen" with a score),
 * "Wird berechnet …" while `call` computes (aria-disabled, so keyboard focus stays) and "Erneut
 * versuchen" after a problem worth a retry (`busy`, `failed`; a `broken` store keeps the normal
 * label). `onScore` sends the click. A posting that cannot be scored
 * (`blockedReason`) gets a disabled button and a visible, focusable info icon beside it that shows
 * the reason on hover and on focus, and gives it to screen readers. Pair it with `ScoreProblem`. */
export function ScoreButton({ row, screening, call, onScore, size = 'default' }: {
  row: PoolRow
  screening: boolean
  call: ScoreCall
  onScore: () => void
  size?: 'default' | 'sm'
}) {
  const reasonId = useId()
  const [open, setOpen] = useState(false)
  const reason = blockedReason(row, screening)
  const idle = row.state === 'scored' ? 'Neu berechnen' : 'Score berechnen'
  if (reason) {
    return (
      <div className="relative flex items-center gap-1">
        <Button type="button" variant="outline" size={size} disabled aria-describedby={reasonId}>{idle}</Button>
        <button type="button" aria-label="Warum nicht verfügbar?" aria-describedby={reasonId}
                onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
                onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
                onKeyDown={(event) => { if (event.key === 'Escape') setOpen(false) }}
                className="inline-flex size-11 items-center justify-center rounded-lg text-primary">
          <Info className="size-5" aria-hidden="true" />
        </button>
        <div id={reasonId} role="tooltip" hidden={!open}
             className="absolute top-full right-0 z-10 w-[300px] max-w-[80vw] rounded-lg border bg-card px-3.5 py-3 text-sm shadow-card">
          {reason}
        </div>
      </div>
    )
  }
  return (
    <>
      <Button type="button" variant="outline" size={size} aria-disabled={call.computing || undefined}
              aria-busy={call.computing || undefined}
              className={cn(call.computing && 'cursor-not-allowed opacity-50')}
              onClick={() => { if (!call.computing) onScore() }}>
        {call.computing
          ? <><LoaderCircle className="motion-safe:animate-spin" aria-hidden="true" />Wird berechnet …</>
          : call.problem === 'busy' || call.problem === 'failed' ? 'Erneut versuchen' : idle}
      </Button>
      <span role="status" className="sr-only">{call.computing ? 'Der Score wird berechnet.' : ''}</span>
    </>
  )
}

/** The message under a score button after a problem (`ScoreCall.problem`); nothing otherwise. */
export function ScoreProblem({ call }: { call: ScoreCall }) {
  if (!call.problem) return null
  return (
    <p role="alert" className="text-sm text-danger">
      {{
        busy: 'Es läuft gerade schon ein Scoring. Versuch es gleich noch einmal.',
        failed: 'Der Score konnte nicht berechnet werden. Versuch es noch einmal.',
        broken: 'Der Score konnte nicht gespeichert werden. Prüfe, ob das Datenrepository beschreibbar ist.',
      }[call.problem]}
    </p>
  )
}

/** A key hint beside a control; hidden from screen readers, a legend names the keys. */
export function Kbd({ children }: { children: ReactNode }) {
  return <span className="kbd" aria-hidden="true">{children}</span>
}

/** A small rounded label; `className` sets its colors, `id` lets a control point at it. */
export function Badge({ className, id, children }: { className: string; id?: string; children: ReactNode }) {
  return (
    <span id={id} className={cn('inline-flex items-center gap-1.5 rounded-full py-0.5 pr-2.5 pl-2 text-[13px] font-bold', className)}>
      {children}
    </span>
  )
}

/** Reason chips as read-only labels: `ids` are looked up in `chips` (an unknown ID shows
 * itself), tinted by polarity. Renders nothing for an empty list. */
export function ChipList({ ids, chips }: { ids: string[]; chips: ReasonChip[] }) {
  if (ids.length === 0) return null
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Gründe">
      {ids.map((id) => {
        const chip = chips.find((entry) => entry.id === id)
        const tone = chip?.polarity === 'positive' ? 'text-primary'
          : chip?.polarity === 'negative' ? 'text-negative' : 'text-muted-foreground'
        return <li key={id} className={cn('rounded-full border px-2 text-[13px]', tone)}>{chip?.label ?? id}</li>
      })}
    </ul>
  )
}
