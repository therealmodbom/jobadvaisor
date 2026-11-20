import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import { axe } from '@/test-axe'
import { stubApi } from '@/test-api'
import { POOL } from '@/test-fixtures'
import { SettingsControl } from './settings'

afterEach(() => vi.unstubAllGlobals())

const THRESHOLD = 'Korrekturen bis zum Hinweis'
const PERCENT = 'Anteil bis zum Hinweis (in %)'

/** Render the control and open its panel once the stored settings have arrived. */
async function open(routes: Parameters<typeof stubApi>[0] = {}, onSaved = () => {}) {
  const calls = stubApi({ 'GET /pool': { body: POOL }, ...routes })
  render(<SettingsControl onSaved={onSaved} />)
  await userEvent.click(screen.getByRole('button', { name: 'Einstellungen' }))
  await screen.findByLabelText(THRESHOLD)
  return calls
}

test('the button is closed at first and opens a panel with the stored threshold and rate', async () => {
  stubApi({ 'GET /pool': { body: POOL } })
  render(<SettingsControl onSaved={() => {}} />)
  const button = screen.getByRole('button', { name: 'Einstellungen' })
  expect(button).toHaveAttribute('aria-expanded', 'false')
  expect(screen.queryByRole('dialog')).toBeNull()
  await userEvent.click(button)
  expect(button).toHaveAttribute('aria-expanded', 'true')
  expect(screen.getByRole('dialog', { name: 'Einstellungen' })).toBeVisible()
  expect(await screen.findByLabelText(THRESHOLD)).toHaveValue(10)
  expect(screen.getByLabelText(PERCENT)).toHaveValue(30)
})

test('settings save the share as 0 to 1 and tell the view to reload the pool', async () => {
  const onSaved = vi.fn()
  const calls = await open({ 'PUT /pool/settings': { body: { settings: POOL.settings } } }, onSaved)
  await userEvent.clear(screen.getByLabelText(THRESHOLD))
  await userEvent.type(screen.getByLabelText(THRESHOLD), '5')
  await userEvent.clear(screen.getByLabelText(PERCENT))
  await userEvent.type(screen.getByLabelText(PERCENT), '25')
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1))
  expect(calls.find((call) => call.method === 'PUT')!.body).toEqual({ correction_threshold: 5, correction_rate: 0.25 })
})

test.each([['0', '30', /ganze Zahl ab 1/], ['2.5', '30', /ganze Zahl ab 1/], ['5', '101', /von 0 bis 100/], ['5', '', /von 0 bis 100/]])(
  'settings reject %s / %s inline and send nothing', async (threshold, percent, message) => {
    const calls = await open()
    await userEvent.clear(screen.getByLabelText(THRESHOLD))
    await userEvent.type(screen.getByLabelText(THRESHOLD), threshold)
    await userEvent.clear(screen.getByLabelText(PERCENT))
    if (percent) await userEvent.type(screen.getByLabelText(PERCENT), percent)
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(calls.some((call) => call.method === 'PUT')).toBe(false)
  })

test('a failed save keeps the input and offers a retry', async () => {
  let fail = true
  const calls = await open({ 'PUT /pool/settings': () => (fail ? { status: 500 } : { body: { settings: POOL.settings } }) })
  await userEvent.clear(screen.getByLabelText(THRESHOLD))
  await userEvent.type(screen.getByLabelText(THRESHOLD), '7')
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  expect(await screen.findByText('Die Einstellungen wurden nicht gespeichert.')).toBeVisible()
  expect(screen.getByLabelText(THRESHOLD)).toHaveValue(7)
  fail = false
  await userEvent.click(screen.getByRole('button', { name: 'Erneut versuchen' }))
  await waitFor(() => expect(calls.filter((call) => call.method === 'PUT')).toHaveLength(2))
})

test('Escape closes the panel and focus returns to the button', async () => {
  await open()
  await userEvent.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(screen.getByRole('button', { name: 'Einstellungen' })).toHaveFocus()
  expect(screen.getByRole('button', { name: 'Einstellungen' })).toHaveAttribute('aria-expanded', 'false')
})

test('a click outside closes the panel', async () => {
  await open()
  await userEvent.click(document.body)
  expect(screen.queryByRole('dialog')).toBeNull()
})

test('a second press on the button closes the panel', async () => {
  await open()
  await userEvent.click(screen.getByRole('button', { name: 'Einstellungen' }))
  expect(screen.queryByRole('dialog')).toBeNull()
})

test('a failed load of the stored settings offers a retry', async () => {
  let failing = true
  stubApi({ 'GET /pool': () => (failing ? { status: 500 } : { body: POOL }) })
  render(<SettingsControl onSaved={() => {}} />)
  await userEvent.click(screen.getByRole('button', { name: 'Einstellungen' }))
  failing = false
  await userEvent.click(await screen.findByRole('button', { name: 'Erneut versuchen' }))
  expect(await screen.findByLabelText(THRESHOLD)).toHaveValue(10)
})

test('the open panel has no accessibility violations', async () => {
  await open()
  expect(await axe(document.body, { rules: { region: { enabled: false } } })).toHaveNoViolations()
})
