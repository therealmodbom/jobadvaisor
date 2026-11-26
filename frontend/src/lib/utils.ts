import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** `record` without `key`. */
export const without = <T,>(record: Record<string, T>, key: string) =>
  Object.fromEntries(Object.entries(record).filter(([entry]) => entry !== key))

/** Whether `url` is an http(s) address, the only kind `OriginalLink` makes a link of. */
export function isWebUrl(url: string | null | undefined): url is string {
  return !!url && /^https?:\/\//i.test(url)
}

/** Joins class names, letting a later Tailwind class override a conflicting earlier one. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
