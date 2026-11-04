import { configureAxe, type AxeMatchers } from 'vitest-axe'

// vitest-axe 0.1 augments the `Vi` namespace older Vitest versions had; Vitest 5 reads matcher
// types from the `vitest` module.
declare module 'vitest' {
  interface Matchers<R extends void | Promise<void> = void | Promise<void>, T = unknown> extends AxeMatchers {}
}

/** axe for component tests. jsdom applies no stylesheet, so color contrast is checked on the
 * theme tokens by `contrast.test.ts` instead of here. */
export const axe = configureAxe({ rules: { 'color-contrast': { enabled: false } } })
