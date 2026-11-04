import { useId, useState, type FormEvent, type ReactNode } from 'react'
import { Check, ExternalLink } from 'lucide-react'
import { api, type PoolRow, type Posting, type ReasonChip, type Status } from '@/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { categoryNames, STATUSES } from '@/lib/german'
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
      <label htmlFor={id} className="text-sm font-bold">Status</label>
      <select id={id} value={value} aria-busy={saving} aria-label={`Status: ${title}`}
              onChange={(event) => !saving && onStatus(event.target.value as Status)}
              className="min-h-11 rounded-lg border border-input bg-background px-2.5 text-[15px]">
        {STATUSES.map(([option, label]) => <option key={option} value={option}>{label}</option>)}
      </select>
      {saving && <span role="status" className="text-sm text-muted-foreground">wird gespeichert…</span>}
      {failed && (
        <span role="alert" className="flex flex-col items-start gap-1 text-sm text-danger">
          Der Status wurde nicht gespeichert.
          <Button type="button" variant="outline" size="sm" onClick={() => onStatus(failed)}>Erneut versuchen</Button>
        </span>
      )}
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
