// @vitest-environment node
/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { describe, expect, test } from 'vitest'

// jsdom applies no stylesheet, so axe cannot measure color contrast; this test checks the
// theme tokens themselves against WCAG 2.2 AA in both themes instead.
const css = readFileSync(new URL('./index.css', import.meta.url), 'utf8')
const [lightBlock, darkBlock] = css.split('@theme')[0].split('@media (prefers-color-scheme: dark)')

function tokens(block: string): Record<string, string> {
  return Object.fromEntries([...block.matchAll(/--([\w-]+):\s*(#[0-9A-Fa-f]{6});/g)]
    .map(([, name, value]) => [name, value]))
}

const light = tokens(lightBlock)
const themes = { light, dark: { ...light, ...tokens(darkBlock) } }

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

/** Text on surface: 4.5:1. */
const TEXT: [string, string][] = [
  ['foreground', 'background'], ['foreground', 'card'], ['foreground', 'muted'],
  ['foreground', 'positive-soft'], ['muted-foreground', 'background'],
  ['muted-foreground', 'card'], ['muted-foreground', 'muted'],
  ['primary-foreground', 'primary'], ['primary', 'card'], ['primary', 'background'],
  ['primary', 'positive-soft'], ['negative-foreground', 'negative'], ['negative', 'card'],
  ['negative', 'negative-soft'], ['explore', 'card'], ['explore', 'explore-soft'],
  ['danger', 'card'], ['danger', 'danger-soft'], ['success', 'card'], ['success', 'success-soft'],
  ['foreground', 'card-alt'], ['muted-foreground', 'card-alt'], ['primary', 'card-alt'],
  ['negative', 'card-alt'], ['explore', 'card-alt'],
]
/** Control boundaries and focus ring against their surface: 3:1 (WCAG 1.4.11). */
const CONTROLS: [string, string][] = [
  ['input', 'card'], ['input', 'background'], ['ring', 'card'], ['ring', 'background'],
  ['ring', 'card-alt'],
]

test('contrast matches the WCAG formula at its extremes', () => {
  expect(contrast('#000000', '#FFFFFF')).toBeCloseTo(21)
  expect(contrast('#777777', '#777777')).toBe(1)
})

describe.each(Object.entries(themes))('%s theme', (_, theme) => {
  test.each(TEXT)('text %s on %s reaches 4.5:1', (fg, bg) => {
    expect(contrast(theme[fg], theme[bg])).toBeGreaterThanOrEqual(4.5)
  })
  test.each(CONTROLS)('control %s on %s reaches 3:1', (fg, bg) => {
    expect(contrast(theme[fg], theme[bg])).toBeGreaterThanOrEqual(3)
  })
})
