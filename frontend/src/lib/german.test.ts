import { expect, test } from 'vitest'
import { addedLabel, dayLabel, daysBefore } from './german'

test.each([['2026-11-23', '23.11.2026'], ['2026-01-05', '05.01.2026']])('dayLabel(%s) is %s', (day, label) => {
  expect(dayLabel(day)).toBe(label)
})

// Late in the evening the local day is not the UTC day: the date must come from local parts.
test.each([
  [new Date(2026, 10, 24, 0, 30), 30, '2026-10-25'],
  [new Date(2026, 10, 24, 23, 30), 30, '2026-10-25'],
  [new Date(2026, 2, 5, 12), 10, '2026-02-23'],
])('daysBefore(%s, %i) is %s', (now, days, day) => {
  expect(daysBefore(days, now)).toBe(day)
})

// The vitest time zone is pinned to Europe/Berlin (vite.config.ts), so these read the same everywhere.
test.each([
  ['2026-11-12T13:05:00+00:00', 'Hinzugefügt 12.11.2026, 14:05'],
  ['2026-01-05T08:03:00+00:00', 'Hinzugefügt 05.01.2026, 09:03'],
  ['2026-11-11T23:30:00+00:00', 'Hinzugefügt 12.11.2026, 00:30'],
  ['2026-11-12T13:05:00.123456+00:00', 'Hinzugefügt 12.11.2026, 14:05'],
])('addedLabel(%s) is %s', (iso, label) => {
  expect(addedLabel(iso)).toBe(label)
})
