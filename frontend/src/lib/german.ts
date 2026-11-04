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
