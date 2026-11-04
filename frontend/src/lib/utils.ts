import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** `record` without `key`. */
export const without = <T,>(record: Record<string, T>, key: string) =>
  Object.fromEntries(Object.entries(record).filter(([entry]) => entry !== key))

/** Joins class names, letting a later Tailwind class override a conflicting earlier one. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
