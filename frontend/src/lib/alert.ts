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

/** What the run view says about leaving a run and about the links it did not settle, which
 * depends on where the entries came from: `over` is the button that leaves a finished run, `lost`
 * the text and `lostAction` the button for a run the server forgot, `crash` the closing sentence
 * of a crashed run's notice. `cancelled` says how to add the entries of a cancelled run that were
 * not reached (null: `again` covers it; when set, it is the closing sentence of a cancelled run
 * instead of `again`), and `again` is the sentence of a finished or cancelled run with failed or
 * unreached entries (null: none). `listLink` adds a link „Offene Links ansehen“ after the closing
 * sentence (`again`, `cancelled` or `crash`) and in the notice of a run the server forgot: every
 * source whose run keeps its links in the list of open links sets it, except the run that is
 * shown in that tab itself. */
export type RunWords = {
  over: string; lost: string; lostAction: string; crash: string
  cancelled: string | null; again: string | null
  listLink: boolean
}

/** The words of a run of a pasted alert mail: the links not added are kept under „Offene Links“,
 * and the mail can also be pasted again, which marks what is stored. */
export const PASTE_WORDS: RunWords = {
  over: 'Andere Mail einfügen',
  lost: 'Die App wurde neu gestartet, der Stand dieses Laufs ist weg. Schon gespeicherte Anzeigen bleiben gespeichert, die übrigen Links stehen unter „Offene Links“. Du kannst die Mail auch noch einmal einfügen: Gespeicherte Stellen sind dann markiert.',
  lostAction: 'Mail noch einmal einfügen',
  crash: 'Die Links, die er nicht erreicht hat, stehen unter „Offene Links“. Du kannst die Mail auch noch einmal einfügen: Gespeicherte Stellen sind dann markiert.',
  cancelled: 'Die Links, die nicht erreicht wurden, stehen unter „Offene Links“. Du kannst die Mail auch erneut einfügen, um die übrigen hinzuzufügen: Was schon gespeichert ist, erscheint dann als gespeichert.',
  again: 'Die Links, die nicht gelesen wurden oder nicht erreicht sind, stehen unter „Offene Links“.',
  listLink: true,
}

/** The words of a run started from „Offene Links“ (the retry of one link or of all). Its run
 * shows in that tab, so no sentence points there (`listLink` off); `again` does not say „again“,
 * since a run of another source that this tab attached to may hold links the list did not have. */
export const RETRY_WORDS: RunWords = {
  over: 'Zurück zu den offenen Links',
  lost: 'Der Server kennt den Lauf nicht mehr. Schon gespeicherte Anzeigen bleiben gespeichert, die übrigen Links stehen weiter in der Liste.',
  lostAction: 'Zurück zu den offenen Links',
  crash: 'Die übrigen Links stehen weiter in der Liste.',
  cancelled: null,
  again: 'Die Links, die nicht hinzugefügt wurden, stehen in der Liste der offenen Links.',
  listLink: false,
}

/** The words of a run of entries picked from a mailbox check: every mail of the pick list counts
 * as handled once the run starts, so the links that were not stored are kept under „Offene Links“
 * and their mails do not come back. */
export const MAILBOX_WORDS: RunWords = {
  over: 'Zurück zum Postfach',
  lost: 'Der Server kennt den Lauf nicht mehr. Schon gespeicherte Anzeigen bleiben gespeichert, die übrigen Links stehen unter „Offene Links“.',
  lostAction: 'Zurück zum Postfach',
  crash: 'Die Links, die er nicht erreicht hat, stehen unter „Offene Links“.',
  cancelled: null,
  again: 'Die Links, die nicht gelesen wurden oder nicht erreicht sind, stehen unter „Offene Links“. Ihre Mails gelten als gelesen.',
  listLink: true,
}
