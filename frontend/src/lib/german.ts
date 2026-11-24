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

/** „12.11.2026, 14:05“ for the ISO timestamp `iso` (offset, optional microseconds), to the minute
 * and in the runtime's time zone, which in the app is the browser's. */
export function whenLabel(iso: string): string {
  return ADDED_FORMAT.format(new Date(iso))
}

/** „Hinzugefügt 12.11.2026, 14:05“ for the ISO timestamp `iso` (see `whenLabel`). */
export function addedLabel(iso: string): string {
  return `Hinzugefügt ${whenLabel(iso)}`
}

const DAY_FORMAT = new Intl.DateTimeFormat('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })

/** „23.11.2026“ for the calendar day `day` (`YYYY-MM-DD`), however the runtime's time zone lies. */
export function dayLabel(day: string): string {
  const [year, month, date] = day.split('-').map(Number)
  return DAY_FORMAT.format(new Date(year, month - 1, date))
}

/** The calendar day `days` before `now`, as `YYYY-MM-DD` in the runtime's time zone (the `value` of a date input). */
export function daysBefore(days: number, now = new Date()): string {
  const day = new Date(now.getFullYear(), now.getMonth(), now.getDate() - days)
  return [day.getFullYear(), day.getMonth() + 1, day.getDate()].map((part, i) => String(part).padStart(i ? 2 : 4, '0')).join('-')
}
