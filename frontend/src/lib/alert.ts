import type { AlertEntry } from '@/api'

/** `n` with its noun: "1 Stelle", "3 Stellen". */
export const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

/** An entry the pick list selects at first: a new posting on a host the app fetches. */
export const preselected = (entry: AlertEntry) => !entry.duplicate && !entry.login_walled && !entry.ambiguous

/** The panel of the intake views and the row of a pick or run list. */
export const PANEL = 'flex flex-col gap-3.5 rounded-xl border bg-card p-5 shadow-card'
export const ROW = 'flex items-start gap-3 rounded-[10px] border px-4 py-3'
/** For a small button inside a row: its label wraps instead of overflowing the row, and on a
 * phone it is as wide as the row and 44px high. */
export const ROW_BUTTON = 'h-auto min-h-8 whitespace-normal text-center max-sm:min-h-11 max-sm:w-full'

/** What the run view says about leaving a run, which depends on where the entries came from:
 * `over` is the button that leaves a finished run, `lost` the text and `lostAction` the button
 * for a run the server forgot, `crash` the closing sentence of a crashed run's notice. */
export type RunWords = { over: string; lost: string; lostAction: string; crash: string }

/** The words of a run of a pasted alert mail. */
export const PASTE_WORDS: RunWords = {
  over: 'Andere Mail einfügen',
  lost: 'Die App wurde neu gestartet, der Stand dieses Laufs ist weg. Schon gespeicherte Anzeigen bleiben gespeichert. Füge die Mail noch einmal ein: Gespeicherte Stellen sind dann markiert, die übrigen kannst du erneut hinzufügen.',
  lostAction: 'Mail noch einmal einfügen',
  crash: 'Füge die Mail noch einmal ein: Gespeicherte Stellen sind dann markiert.',
}
