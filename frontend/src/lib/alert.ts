import type { AlertEntry } from '@/api'

/** `n` with its noun: "1 Stelle", "3 Stellen". */
export const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

/** An entry the pick list selects at first: a new posting on a host the app fetches. */
export const preselected = (entry: AlertEntry) => !entry.duplicate && !entry.login_walled && !entry.ambiguous

/** An entry that cannot be picked: a stored duplicate, a link several postings share, or a copy of
 * a link an earlier mail of the pick list offers. */
export const locked = (entry: AlertEntry) => Boolean(entry.duplicate) || entry.ambiguous || Boolean(entry.offered_in)

/** The panel of the intake views and the row of a pick or run list. */
export const PANEL = 'flex flex-col gap-3.5 rounded-xl border bg-card p-5 shadow-card'
export const ROW = 'flex items-start gap-3 rounded-[10px] border px-4 py-3'
/** For a small button inside a row: its label wraps instead of overflowing the row, and on a
 * phone it is as wide as the row and 44px high. */
export const ROW_BUTTON = 'h-auto min-h-8 whitespace-normal text-center max-sm:min-h-11 max-sm:w-full'

/** What the run view says about leaving a run, which depends on where the entries came from:
 * `over` is the button that leaves a finished run, `lost` the text and `lostAction` the button
 * for a run the server forgot, `crash` the closing sentence of a crashed run's notice. `cancelled`
 * says how to add the entries of a cancelled run that were not reached (null: `again` covers
 * it), and `again` is the sentence of a finished or cancelled run with failed or unreached
 * entries, for a run whose mails the next check offers again (null: not the case). */
export type RunWords = {
  over: string; lost: string; lostAction: string; crash: string
  cancelled: string | null; again: string | null
}

/** The words of a run of a pasted alert mail. */
export const PASTE_WORDS: RunWords = {
  over: 'Andere Mail einfügen',
  lost: 'Die App wurde neu gestartet, der Stand dieses Laufs ist weg. Schon gespeicherte Anzeigen bleiben gespeichert. Füge die Mail noch einmal ein: Gespeicherte Stellen sind dann markiert, die übrigen kannst du erneut hinzufügen.',
  lostAction: 'Mail noch einmal einfügen',
  crash: 'Füge die Mail noch einmal ein: Gespeicherte Stellen sind dann markiert.',
  cancelled: 'Füge die Mail erneut ein, um die übrigen hinzuzufügen. Was schon gespeichert ist, erscheint dann als gespeichert.',
  again: null,
}

/** The words of a run of entries picked from a mailbox check: the mails count as handled, so a lost
 * or crashed run is made up for by adding the missing postings one by one. */
export const MAILBOX_WORDS: RunWords = {
  over: 'Zurück zum Postfach',
  lost: 'Die App wurde neu gestartet, der Stand dieses Laufs ist weg. Schon gespeicherte Anzeigen bleiben gespeichert. Die Mails der Prüfung gelten als gelesen: Füge fehlende Anzeigen einzeln als Link oder Text ein.',
  lostAction: 'Zurück zum Postfach',
  crash: 'Die Mails der Prüfung gelten als gelesen: Füge fehlende Anzeigen einzeln als Link oder Text ein.',
  cancelled: null,
  again: 'Die nächste Prüfung bietet die Mails dieser Anzeigen wieder an.',
}
