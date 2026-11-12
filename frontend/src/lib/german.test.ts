import { expect, test } from 'vitest'
import { addedLabel } from './german'

// The vitest time zone is pinned to Europe/Berlin (vite.config.ts), so these read the same everywhere.
test.each([
  ['2026-11-12T13:05:00+00:00', 'Hinzugefügt 12.11.2026, 14:05'],
  ['2026-01-05T08:03:00+00:00', 'Hinzugefügt 05.01.2026, 09:03'],
  ['2026-11-11T23:30:00+00:00', 'Hinzugefügt 12.11.2026, 00:30'],
  ['2026-11-12T13:05:00.123456+00:00', 'Hinzugefügt 12.11.2026, 14:05'],
])('addedLabel(%s) is %s', (iso, label) => {
  expect(addedLabel(iso)).toBe(label)
})
