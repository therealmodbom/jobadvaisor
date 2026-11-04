import { ThumbsDown, ThumbsUp } from 'lucide-react'
import type { PoolRow, ReasonChip, Strength, Verdict } from '@/api'
import { Kbd } from '@/components/posting'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { LEVELS, type Rating } from '@/lib/rating'
import { cn } from '@/lib/utils'

/** The four levels as a toggle group showing `row`'s level, with the saving and failure state of
 * its rating. A stored verdict without strength marks no button and shows as "Bewertet: Ja" or
 * "Bewertet: Nein". `onLevel` sends the choice; `keys` shows the shortcuts. */
export function VerdictButtons({ row, rating, onLevel, keys }: {
  row: PoolRow
  rating: Rating
  onLevel: (verdict: Verdict, strength: Strength) => void
  keys?: boolean
}) {
  const now = rating.view(row)
  return (
    <div className="flex flex-col items-start gap-1.5">
      <div className="flex flex-wrap gap-2">
        {LEVELS.map(({ key, label, verdict, strength, Icon }) => {
          const on = now.verdict === verdict && now.strength === strength
          const tone = verdict === 'positive'
            ? (on ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-card text-primary')
            : (on ? 'border-negative bg-negative text-negative-foreground' : 'border-border bg-card text-negative')
          return (
            <button key={key} type="button" aria-pressed={on} onClick={() => onLevel(verdict, strength)}
                    aria-label={`${label}: ${row.title}`}
                    className={cn('inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border pr-3 pl-3.5 font-bold', tone)}>
              <Icon className="size-[18px]" aria-hidden="true" />
              {label}
              {keys && <Kbd>{key}</Kbd>}
            </button>
          )
        })}
      </div>
      {now.verdict && !now.strength && (
        <span className="text-sm text-muted-foreground">Bewertet: {now.verdict === 'positive' ? 'Ja' : 'Nein'}</span>
      )}
      {now.saving && <span role="status" className="text-sm text-muted-foreground">wird gespeichert…</span>}
      {now.failed && (
        <span role="alert" className="flex flex-col items-start gap-1 text-sm text-danger">
          {now.failed === 'verdict'
            ? 'Dieser Grund legt kein Urteil fest. Wähle eine der vier Stufen von „Ja“ bis „Nein“, dann wird alles gespeichert.'
            : now.failed === 'chip'
              ? 'Ein Grund dieser Bewertung gibt es nicht mehr. Entferne ihn unter „Gründe“ (er steht dort mit seiner ID), dann wird gespeichert.'
              : 'Die Bewertung wurde nicht gespeichert. Deine Eingaben bleiben stehen.'}
          {now.failed !== 'verdict' && (
            <Button type="button" variant="outline" size="sm" onClick={() => rating.retry(row)}>Erneut versuchen</Button>
          )}
        </span>
      )}
    </div>
  )
}

/** Every reason chip as a toggle, whatever the verdict, then the note field. `keys` shows the
 * shortcuts; `highlight` marks the reasons after a verdict. The fieldset (`reasons-<id>`) takes
 * focus from the view; `Escape` in the note returns focus to the posting's row (`row-<id>`, pool
 * only). A stored chip the policy pack no longer has is listed too (by its ID), so it can be
 * removed. */
export function ReasonsAndNote({ row, chips, rating, keys, highlight }: {
  row: PoolRow
  chips: ReasonChip[]
  rating: Rating
  keys?: boolean
  highlight?: boolean
}) {
  const now = rating.view(row)
  const id = row.posting_id
  return (
    <div className="flex w-full basis-full flex-col gap-4">
      <fieldset id={`reasons-${id}`} tabIndex={-1}
                className={cn('min-w-0 rounded-lg', highlight && 'bg-positive-soft p-3 outline-2 outline-ring')}>
        <legend className={cn('text-sm font-bold', highlight ? 'float-left mb-2 w-full' : 'mb-2')}>
          Gründe <span className="font-normal text-muted-foreground">(optional, gespeichert wird sofort)</span>
        </legend>
        <div className="clear-both flex flex-wrap gap-2">
          {[...chips, ...now.chips.filter((stored) => !chips.some((chip) => chip.id === stored))
            .map((stored): ReasonChip => ({ id: stored, label: stored, polarity: null }))].map((chip, index) => {
            const on = now.chips.includes(chip.id)
            return (
              <button key={chip.id} type="button" aria-pressed={on} onClick={() => rating.chip(row, chip.id)}
                      className={cn('inline-flex min-h-10 items-center gap-1.5 rounded-full border px-3 text-sm',
                        on ? 'border-primary bg-positive-soft font-bold text-primary' : 'bg-card')}>
                {keys && index < Math.min(9, chips.length) && <Kbd>⇧{index + 1}</Kbd>}
                {chip.polarity === 'positive' && <ThumbsUp className="size-3.5" aria-hidden="true" />}
                {chip.polarity === 'negative' && <ThumbsDown className="size-3.5" aria-hidden="true" />}
                {chip.label}
              </button>
            )
          })}
        </div>
      </fieldset>
      <div className="flex flex-col gap-1.5">
        <label htmlFor={`note-${id}`} className="inline-flex items-center gap-2 text-sm font-bold">
          Notiz{keys && <Kbd>N</Kbd>}
        </label>
        <Textarea id={`note-${id}`} rows={3} value={now.note} placeholder="Was die Gründe nicht abdecken"
                  aria-describedby={!now.verdict && now.chips.length === 0 && now.note.trim() ? `note-hint-${id}` : undefined}
                  onChange={(event) => rating.setNote(row, event.target.value)}
                  onBlur={() => rating.saveNote(row)}
                  onKeyDown={(event) => {
                    if (event.key === 'Escape') document.getElementById(`row-${id}`)?.focus()
                  }} />
        {!now.verdict && now.chips.length === 0 && now.note.trim() && (
          <p id={`note-hint-${id}`} className="text-sm text-muted-foreground">
            Die Notiz wird gespeichert, sobald du ein Urteil oder einen Grund wählst.
          </p>
        )}
      </div>
    </div>
  )
}

const SHORTCUTS: [string[], string][] = [
  [['J', 'K'], 'Nächste oder vorige Anzeige'],
  ...LEVELS.map(({ key, label }): [string[], string] => [[key], label]),
  [['⇧', '1–9'], 'Grund mit dieser Nummer an oder aus'],
  [['N'], 'Notiz schreiben'],
  [['Esc'], 'Notiz verlassen'],
  [['Enter'], 'Weiter zur nächsten unbewerteten Anzeige'],
]

/** The always-visible shortcut legend of the pool. */
export function Legend() {
  return (
    <section aria-labelledby="legend-title" className="rounded-xl border bg-card px-5 py-4">
      <h2 id="legend-title" className="mb-2.5 font-bold">Tastatur</h2>
      <dl className="m-0 flex flex-wrap gap-x-6 gap-y-2 text-sm">
        {SHORTCUTS.map(([keys, meaning]) => (
          <div key={meaning} className="flex items-center gap-2">
            <dt className="flex gap-1">{keys.map((key) => <span key={key} className="kbd">{key}</span>)}</dt>
            <dd className="m-0">{meaning}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2.5 text-sm text-muted-foreground">
        Jede Bewertung wird sofort gespeichert. Nach einem Urteil bleibt die Anzeige offen, damit du Gründe
        wählen kannst; Enter geht weiter. Während du tippst, sind die Kürzel aus.
      </p>
    </section>
  )
}
