import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import type { PoolRow, ScoreAnswer } from '@/api'
import { useScore } from '@/lib/score'
import { axe } from '@/test-axe'
import { pending, stubApi } from '@/test-api'
import { row } from '@/test-fixtures'
import { ScoreButton, ScoreProblem } from './posting'

afterEach(() => vi.unstubAllGlobals())

const unscored = row('n1', 'Neue Stelle (m/w/d)', { state: 'unscored', score: null })
const ANSWER = { row: row('n1', 'Neue Stelle (m/w/d)', { score: 7 }) }

/** The score button and its problem line for `posting`, wired to `useScore` as the views do. */
function Harness({ posting, screening = true, onAnswer = vi.fn(), onRefused = vi.fn() }: {
  posting: PoolRow
  screening?: boolean
  onAnswer?: (answer: ScoreAnswer) => void
  onRefused?: () => void
}) {
  const score = useScore(onAnswer, onRefused)
  const call = score.call(posting.posting_id)
  return (
    <>
      <ScoreButton row={posting} screening={screening} call={call} onScore={() => void score.run(posting.posting_id)} />
      <ScoreProblem call={call} />
    </>
  )
}

test('the button says "Score berechnen" without a score and "Neu berechnen" with one', () => {
  const { rerender } = render(<Harness posting={unscored} />)
  expect(screen.getByRole('button', { name: 'Score berechnen' })).toBeEnabled()
  rerender(<Harness posting={row('p1', 'X')} />)
  expect(screen.getByRole('button', { name: 'Neu berechnen' })).toBeEnabled()
})

test('a click posts the score and hands the answer over', async () => {
  const onAnswer = vi.fn()
  const calls = stubApi({ 'POST /postings/n1/score': { body: ANSWER } })
  render(<Harness posting={unscored} onAnswer={onAnswer} />)
  await userEvent.click(screen.getByRole('button', { name: 'Score berechnen' }))
  expect(calls.filter((call) => call.method === 'POST').map((call) => call.path)).toEqual(['/postings/n1/score'])
  expect(onAnswer).toHaveBeenCalledWith(ANSWER)
  expect(screen.queryByRole('alert')).toBeNull()
})

test('while it computes the button says so, keeps focus and a second click sends nothing', async () => {
  const calls = stubApi({ 'POST /postings/n1/score': pending })
  render(<Harness posting={unscored} />)
  await userEvent.click(screen.getByRole('button', { name: 'Score berechnen' }))
  const busy = await screen.findByRole('button', { name: 'Wird berechnet …' })
  expect(busy).toHaveAttribute('aria-disabled', 'true')
  expect(busy).toHaveFocus()
  expect(screen.getByRole('status')).toHaveTextContent('Der Score wird berechnet.')
  await userEvent.click(busy)
  expect(calls.filter((call) => call.method === 'POST')).toHaveLength(1)
})

test.each([
  ['scoring in progress', 409, 'Es läuft gerade schon ein Scoring. Versuch es gleich noch einmal.'],
  ['scoring failed', 502, 'Der Score konnte nicht berechnet werden. Versuch es noch einmal.'],
])('%s answers an alert and the button offers a retry that clears it', async (error, status, message) => {
  let fail = true
  stubApi({ 'POST /postings/n1/score': () => (fail ? { status, body: { error, detail: 'x' } } : { body: ANSWER }) })
  const onRefused = vi.fn()
  render(<Harness posting={unscored} onRefused={onRefused} />)
  await userEvent.click(screen.getByRole('button', { name: 'Score berechnen' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(message)
  fail = false
  await userEvent.click(screen.getByRole('button', { name: 'Erneut versuchen' }))
  expect(await screen.findByRole('button', { name: 'Score berechnen' })).toBeEnabled()
  expect(screen.queryByRole('alert')).toBeNull()
  expect(onRefused).not.toHaveBeenCalled()
})

test('a gateway error without the API body (error "request failed") is a failed score with a retry', async () => {
  stubApi({ 'POST /postings/n1/score': { status: 504, body: {} } })
  render(<Harness posting={unscored} />)
  await userEvent.click(screen.getByRole('button', { name: 'Score berechnen' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Der Score konnte nicht berechnet werden. Versuch es noch einmal.')
  expect(screen.getByRole('button', { name: 'Erneut versuchen' })).toBeEnabled()
})

test('a 500 "internal error" is a broken store: its own message and no retry label', async () => {
  stubApi({ 'POST /postings/n1/score': { status: 500, body: { error: 'internal error', detail: 'x' } } })
  const onRefused = vi.fn()
  render(<Harness posting={unscored} onRefused={onRefused} />)
  await userEvent.click(screen.getByRole('button', { name: 'Score berechnen' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Der Score konnte nicht gespeichert werden. Prüfe, ob das Datenrepository beschreibbar ist.')
  expect(screen.queryByRole('button', { name: 'Erneut versuchen' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Score berechnen' })).toBeEnabled()
  expect(onRefused).not.toHaveBeenCalled()
})

test('an unreachable server is a failed score with a retry', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline') }))
  render(<Harness posting={unscored} />)
  await userEvent.click(screen.getByRole('button', { name: 'Score berechnen' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Der Score konnte nicht berechnet werden.')
  expect(screen.getByRole('button', { name: 'Erneut versuchen' })).toBeEnabled()
})

test.each(['excluded', 'held', 'unscreened'])('a %s refusal on the click reloads instead of offering a retry', async (error) => {
  stubApi({ 'POST /postings/n1/score': { status: 409, body: { error, detail: 'x' } } })
  const onRefused = vi.fn()
  render(<Harness posting={unscored} onRefused={onRefused} />)
  await userEvent.click(screen.getByRole('button', { name: 'Score berechnen' }))
  await vi.waitFor(() => expect(onRefused).toHaveBeenCalledOnce())
  expect(screen.queryByRole('alert')).toBeNull()
  expect(screen.getByRole('button', { name: 'Score berechnen' })).toBeEnabled()
})

test('a posting that vanished (404) reloads too', async () => {
  stubApi({ 'POST /postings/n1/score': { status: 404, body: { error: 'not found', detail: 'x' } } })
  const onRefused = vi.fn()
  render(<Harness posting={unscored} onRefused={onRefused} />)
  await userEvent.click(screen.getByRole('button', { name: 'Score berechnen' }))
  await vi.waitFor(() => expect(onRefused).toHaveBeenCalledOnce())
})

test.each([
  ['excluded', row('e', 'X', { state: 'excluded', score: null, rules: ['nur-vor-ort'] }), true,
    'Eine Ausschlussregel greift: nur-vor-ort. Ausgeschlossene Anzeigen bekommen keinen Score.'],
  ['held', row('h', 'X', { state: 'held', score: null, categories: ['instructions_for_ai'] }), true,
    'Der Inhaltsfilter hält diese Anzeige zurück (Verdacht: Anweisungen an eine KI). Erst nach einer Freigabe kann sie einen Score bekommen.'],
  ['held without categories', row('h', 'X', { state: 'held', score: null }), true,
    'Der Inhaltsfilter hält diese Anzeige zurück. Erst nach einer Freigabe kann sie einen Score bekommen.'],
  ['unscreened without a classifier', row('u', 'X', { state: 'unscored', score: null, unscreened: true }), false,
    'Der Inhaltsfilter hat diese Anzeige nie geprüft, und es ist kein Filter eingerichtet. Ohne Prüfung bekommt sie keinen Score.'],
])('%s: the button is disabled and the reason reaches it through aria-describedby', async (_name, posting, screening, reason) => {
  const calls = stubApi({})
  render(<Harness posting={posting} screening={screening} />)
  const button = screen.getByRole('button', { name: 'Score berechnen' })
  expect(button).toBeDisabled()
  expect(button).toHaveAccessibleDescription(reason)
  const info = screen.getByRole('button', { name: 'Warum nicht verfügbar?' })
  expect(info).toHaveAccessibleDescription(reason)
  await userEvent.click(button)
  expect(calls).toEqual([])
})

test('an unscreened posting can be scored when a classifier is configured', () => {
  render(<Harness posting={row('u', 'X', { state: 'unscored', score: null, unscreened: true })} screening />)
  expect(screen.getByRole('button', { name: 'Score berechnen' })).toBeEnabled()
  expect(screen.queryByRole('button', { name: 'Warum nicht verfügbar?' })).toBeNull()
})

test('the reason shows on hover and on focus of the info icon and Escape hides it', async () => {
  render(<Harness posting={row('e', 'X', { state: 'excluded', score: null, rules: ['nur-vor-ort'] })} />)
  const info = screen.getByRole('button', { name: 'Warum nicht verfügbar?' })
  const tip = screen.getByRole('tooltip', { hidden: true })
  expect(tip).not.toBeVisible()
  await userEvent.hover(info)
  expect(tip).toBeVisible()
  await userEvent.unhover(info)
  expect(tip).not.toBeVisible()
  await userEvent.tab() // focus reaches the info icon: the disabled button is skipped
  expect(info).toHaveFocus()
  expect(tip).toBeVisible()
  await userEvent.keyboard('{Escape}')
  expect(tip).not.toBeVisible()
  await userEvent.tab()
  expect(info).not.toHaveFocus()
})

test('the disabled button with its info icon has no accessibility violations', async () => {
  const { container } = render(<Harness posting={row('e', 'X', { state: 'excluded', score: null, rules: ['nur-vor-ort'] })} />)
  expect(await axe(container)).toHaveNoViolations()
})
