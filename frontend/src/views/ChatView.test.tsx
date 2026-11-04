import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import { axe } from '@/test-axe'
import { pending, stubApi } from '@/test-api'
import { ChatView } from './ChatView'

const QUESTION = 'Warum wurde demo-061 ausgeschlossen?'
const ANSWER = { reply: 'Sie trifft deine Regel no-on-call.',
                 tool_calls: [{ name: 'check_exclusions', args: { posting_id: 'demo-061' } },
                              { name: 'check_exclusions', args: { posting_id: 'demo-061' } }] }

async function ask(text = QUESTION) {
  await userEvent.type(screen.getByLabelText('Deine Frage'), text)
  await userEvent.click(screen.getByRole('button', { name: 'Senden' }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

test('an answer shows below the question with the steps the agent took', async () => {
  const calls = stubApi({ 'POST /agent/messages': { body: ANSWER } })
  render(<ChatView />)
  await ask()
  const conversation = screen.getByRole('region', { name: 'Unterhaltung' })
  expect(await within(conversation).findByText('Sie trifft deine Regel no-on-call.')).toBeVisible()
  expect(within(conversation).getByText(QUESTION)).toBeVisible()
  const steps = within(conversation).getByRole('list', { name: 'Schritte des Agenten' })
  expect(within(steps).getAllByRole('listitem').map((item) => item.textContent))
    .toEqual(['Ausschlussregeln geprüft'])
  expect(calls.find((call) => call.method === 'POST')!.body).toEqual({
    messages: [{ role: 'user', content: QUESTION }] })
  expect(screen.getByLabelText('Deine Frage')).toHaveValue('')
})

test('an answer renders its Markdown: lists, tables and links, but no raw HTML', async () => {
  const reply = ['- **Android Developer** (demo-027)', '',
    '| Anzeige | Urteil |', '|---|---|', '| demo-046 | positiv |', '',
    '[Anzeige](https://example.org/1) <img src=x onerror="alert(1)">'].join('\n')
  stubApi({ 'POST /agent/messages': { body: { reply, tool_calls: [] } } })
  const { container } = render(<ChatView />)
  await ask()
  const conversation = screen.getByRole('region', { name: 'Unterhaltung' })
  expect(await within(conversation).findByRole('table')).toHaveTextContent('demo-046positiv')
  expect(within(conversation).getByText('Android Developer').tagName).toBe('STRONG')
  const external = within(conversation).getByRole('link', { name: /^Anzeige\s*\(öffnet in neuem Tab\)$/ })
  expect(external).toHaveAttribute('target', '_blank')
  expect(external).toHaveClass('underline', 'text-primary')
  expect(external.querySelector('svg')).not.toBeNull()
  expect(conversation.querySelector('img')).toBeNull()
  expect(await axe(container)).toHaveNoViolations()
})

test('a link to a posting page opens it in the same tab', async () => {
  stubApi({ 'POST /agent/messages': { body: {
    reply: '[Backend Engineer, Acme (demo-002)](#/anzeigen/demo-002)',
    tool_calls: [{ name: 'best_open_postings', args: {} }] } } })
  render(<ChatView />)
  await ask()
  const link = await screen.findByRole('link', { name: 'Backend Engineer, Acme (demo-002)' })
  expect(link).toHaveAttribute('href', '#/anzeigen/demo-002')
  expect(link).not.toHaveAttribute('target')
  expect(link).toHaveClass('underline', 'text-primary')
  expect(link.querySelector('svg')).toBeNull()
  expect(screen.getByRole('list', { name: 'Schritte des Agenten' }))
    .toHaveTextContent('Beste offene Anzeigen gesucht')
})

test('the whole conversation goes with the next question', async () => {
  const calls = stubApi({ 'POST /agent/messages': { body: ANSWER } })
  render(<ChatView />)
  await ask()
  await screen.findByText(ANSWER.reply)
  await ask('Und demo-100?')
  const posts = calls.filter((call) => call.method === 'POST')
  expect((posts[1].body as { messages: unknown[] }).messages).toEqual([
    { role: 'user', content: QUESTION }, { role: 'assistant', content: ANSWER.reply },
    { role: 'user', content: 'Und demo-100?' }])
})

test('while the agent answers, progress shows and no second question is sent', async () => {
  const calls = stubApi({ 'POST /agent/messages': pending })
  render(<ChatView />)
  await ask()
  expect(screen.getByRole('status')).toHaveTextContent('Sieht deine Anzeigen durch')
  expect(screen.getByRole('button', { name: 'Senden' })).toBeDisabled()
  await userEvent.type(screen.getByLabelText('Deine Frage'), 'Noch was{Enter}')
  expect(calls.filter((call) => call.method === 'POST')).toHaveLength(1)
})

test('a failed request keeps the question and retries it', async () => {
  let fail = true
  const calls = stubApi({ 'POST /agent/messages': () => (fail
    ? { status: 500, body: { error: 'internal error', detail: 'TimeoutError' } } : { body: ANSWER }) })
  render(<ChatView />)
  await ask()
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('Keine Antwort')
  expect(screen.getByText(QUESTION)).toBeVisible()
  fail = false
  await userEvent.click(within(alert).getByRole('button', { name: 'Erneut versuchen' }))
  expect(await screen.findByText(ANSWER.reply)).toBeVisible()
  const posts = calls.filter((call) => call.method === 'POST')
  expect(posts[1].body).toEqual(posts[0].body)
})

test('bold and code in an answer render as such, without their markers', async () => {
  stubApi({ 'POST /agent/messages': { body: {
    reply: 'Ausgeschlossen durch **no-unpaid**, siehe `demo-061`.', tool_calls: [] } } })
  render(<ChatView />)
  await ask()
  const rule = await screen.findByText('no-unpaid')
  expect(rule.tagName).toBe('STRONG')
  expect(screen.getByText('demo-061').tagName).toBe('CODE')
  expect(screen.queryByText(/\*\*/)).toBeNull()
})

test('suggestions ask what the agent answers over the pool', () => {
  stubApi({})
  render(<ChatView />)
  expect(screen.getByRole('button', { name: 'Auf welche Stelle soll ich mich bewerben?' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Was habe ich als zu junior markiert?' })).toBeVisible()
})

test('a suggestion is sent at once and leaves a draft in the field alone', async () => {
  const calls = stubApi({ 'POST /agent/messages': { body: ANSWER } })
  render(<ChatView />)
  await userEvent.type(screen.getByLabelText('Deine Frage'), 'Entwurf')
  await userEvent.click(screen.getByRole('button', { name: 'Auf welche Stelle soll ich mich bewerben?' }))
  expect(await screen.findByText(ANSWER.reply)).toBeVisible()
  expect(calls.find((call) => call.method === 'POST')!.body).toEqual({
    messages: [{ role: 'user', content: 'Auf welche Stelle soll ich mich bewerben?' }] })
  expect(screen.getByLabelText('Deine Frage')).toHaveValue('Entwurf')
})

test('the chat view has no accessibility violations', async () => {
  stubApi({ 'POST /agent/messages': { body: ANSWER } })
  const { container } = render(<ChatView />)
  await ask()
  await screen.findByText(ANSWER.reply)
  expect(await axe(container)).toHaveNoViolations()
})
