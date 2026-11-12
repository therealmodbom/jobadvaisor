import type { Status } from '@/api'

/** German names of the content guard's categories; an unknown category shows its ID. */
export const CATEGORIES: Record<string, string> = {
  instructions_for_ai: 'Anweisungen an eine KI',
  jailbreaking: 'Versuch, eine KI zu manipulieren',
  dangerous: 'gefährliche Inhalte',
  criminal: 'kriminelle Inhalte',
}

/** The application statuses with their German names, in menu order. */
export const STATUSES: [Status, string][] = [['open', 'offen'], ['applied', 'beworben'], ['done', 'erledigt']]

/** The German names of `categories`, joined by commas. */
export function categoryNames(categories: string[]): string {
  return categories.map((category) => CATEGORIES[category] ?? category).join(', ')
}

const ADDED_FORMAT = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeStyle: 'short' })

/** „Hinzugefügt 12.11.2026, 14:05“ for the ISO timestamp `iso` (offset, optional microseconds),
 * to the minute and in the runtime's time zone, which in the app is the browser's. */
export function addedLabel(iso: string): string {
  return `Hinzugefügt ${ADDED_FORMAT.format(new Date(iso))}`
}
