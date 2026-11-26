import { useId, type ReactNode } from 'react'
import { Info, Lock } from 'lucide-react'
import type { AlertEntry } from '@/api'
import { Badge, OriginalLink } from '@/components/posting'
import { Button } from '@/components/ui/button'
import { locked as isLocked, PANEL, ROW, ROW_BUTTON } from '@/lib/alert'
import { cn, isWebUrl } from '@/lib/utils'

/** A hint above the pick list, in the muted box of the intake view. */
export function Note({ children }: { children: ReactNode }) {
  return (
    <div role="note" className="flex items-start gap-2.5 rounded-[10px] bg-muted px-3.5 py-3 text-[15px]">
      <Info className="mt-0.5 size-[18px] flex-none" aria-hidden="true" />
      <span>{children}</span>
    </div>
  )
}

/** A panel with a heading and a sentence for a state without a list: nothing found, held, lost.
 * `danger` makes it an alert; `children` are its actions. */
export function Notice({ title, text, Icon, danger = false, children }: {
  title: string
  text: string
  Icon: typeof Info
  danger?: boolean
  children: ReactNode
}) {
  const headingId = useId()
  return (
    <section role={danger ? 'alert' : undefined} aria-labelledby={headingId}
             className={cn(PANEL, danger && 'border-danger bg-danger-soft')}>
      <div className="flex items-start gap-2.5">
        <Icon className={cn('mt-0.5 size-[22px] flex-none', danger && 'text-danger')} aria-hidden="true" />
        <div>
          <h2 id={headingId} className="text-lg font-bold">{title}</h2>
          <p className="mt-1">{text}</p>
        </div>
      </div>
      {children}
    </section>
  )
}

export function StartFailed() {
  return (
    <p role="alert" className="rounded-xl border border-danger bg-danger-soft px-4 py-3">
      Der Lauf konnte nicht gestartet werden. Ist der Server erreichbar? Die Auswahl bleibt, du kannst es noch einmal versuchen.
    </p>
  )
}

/** One entry of the pick list: a checkbox named by the title, the cleaned link, and what keeps
 * the entry from being picked or preselected (a copy of a link another mail offers names that
 * mail). `id` is the checkbox's ID, unique in the page; the
 * reason below it gets `<id>-why`. */
export function PickRow({ entry, id, checked, onToggle, onText }: {
  entry: AlertEntry
  id: string
  checked: boolean
  onToggle: () => void
  onText: () => void
}) {
  const locked = isLocked(entry)
  const why = `${id}-why`
  return (
    <li className={cn(ROW, locked && 'bg-background')}>
      <input type="checkbox" id={id} checked={checked && !locked} disabled={locked}
             aria-describedby={locked || entry.login_walled ? why : undefined} onChange={onToggle}
             className="mt-0.5 size-[22px] flex-none accent-primary disabled:cursor-not-allowed disabled:opacity-50" />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <label htmlFor={id} className="font-bold">{entry.title || entry.url}</label>
        {isWebUrl(entry.url)
          ? <OriginalLink url={entry.url} label={entry.url} name={entry.title} className="self-start font-mono text-sm" />
          : <span className="font-mono text-sm break-all text-muted-foreground">{entry.url}</span>}
        {entry.duplicate && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <Badge id={why} className="bg-muted text-foreground">Schon gespeichert</Badge>
            <a href={`#/anzeigen/${encodeURIComponent(entry.duplicate.posting_id)}`}
               className="text-[15px] text-primary underline">Gespeicherte Anzeige ansehen</a>
          </div>
        )}
        {entry.login_walled && !entry.duplicate && !entry.offered_in && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <Badge className="bg-muted text-foreground">
              <Lock className="size-4" aria-hidden="true" />Seite mit Login-Pflicht
            </Badge>
            <span id={why} className="text-sm text-muted-foreground">
              Nicht vorausgewählt: Die Seite selbst wird nicht abgerufen, die Anzeige wird über eine Websuche gesucht.
            </span>
          </div>
        )}
        {entry.offered_in && !entry.duplicate && !entry.ambiguous && (
          <span id={why} className="text-sm text-muted-foreground">
            Auch in der Mail von {entry.offered_in.sender || 'Unbekannter Absender'}, „{entry.offered_in.subject || 'ohne Betreff'}“.
            Dort auswählbar.
          </span>
        )}
        {entry.ambiguous && !entry.duplicate && (
          <>
            <Badge className="self-start bg-muted text-foreground">Link nicht eindeutig</Badge>
            <span id={why} className="text-sm text-muted-foreground">
              Mehrere Stellen der Mail führen über dieselbe Adresse. Über diesen Link lässt sich die Anzeige nicht
              hinzufügen. Füge ihren Text ein.
            </span>
            <Button type="button" size="sm" variant="outline" onClick={onText}
                    className={cn(ROW_BUTTON, 'sm:self-start')}>Text einfügen</Button>
          </>
        )}
      </div>
    </li>
  )
}
