import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { whenLabel } from '@/lib/german'
import type { UnsettledLink } from '@/lib/unsettled-links'
import { axe } from '@/test-axe'
import { stubApi } from '@/test-api'
import { POOL } from '@/test-fixtures'
import App from '@/App'

const TRIED = '2026-11-27T08:05:00Z'
const ADDED = '2026-11-27T08:00:00Z'

const link = (n: number, over: Partial<UnsettledLink> = {}): UnsettledLink => ({
  url: `https://jobs.example.com/${n}`, title: `Stelle ${n}`, source: 'mailbox', state: 'unread', tries: 1,
  added_at: ADDED, last_tried_at: TRIED, attempts: [{ step: 'plain', outcome: 'HTTP 503' }], reason: null,
  in_run: false, ...over,
})

const nav = () => within(screen.getByRole('navigation', { name: 'Hauptnavigation' }))
const tabs = () => within(screen.getByRole('group', { name: 'Quelle der Anzeige' }))
/** The rows of the list: its direct children, since a row holds a list of attempts itself. */
const rows = () => Array.from(screen.getByRole('list', { name: 'Offene Links' }).children) as HTMLElement[]

/** Serves `GET /unsettled-links` from `list`, which a test may change, and `DELETE` from it too. */
function serve(list: UnsettledLink[], runId: string | null = null, extra: Parameters<typeof stubApi>[0] = {}) {
  return stubApi({
    'GET /pool': { body: POOL },
    'GET /policy-pack/login-wall-hosts': { body: { hosts: [] } },
    'GET /unsettled-links': () => ({ body: { links: list, run_id: runId } }),
    'DELETE /unsettled-links': (call) => {
      const url = (call.body as { url: string }).url
      list.splice(0, list.length, ...list.filter((row) => row.url !== url))
      return { body: { links: list } }
    },
    ...extra,
  })
}

beforeEach(() => {
  window.location.hash = '#/offene-links'
})

afterEach(() => {
  window.location.hash = ''
  vi.unstubAllGlobals()
})

test('after a run, the tab lists each link with outcome, title, source, runs and last try, in neutral rows', async () => {
  serve([link(1), link(2), link(3, { state: 'unclear' })])
  render(<App />)
  expect(await screen.findByRole('heading', { level: 2, name: '3 offene Links' })).toBeVisible()
  const [first, , third] = rows()
  expect(first).toHaveTextContent('Nicht gelesen')
  expect(first).toHaveTextContent('Stelle 1')
  expect(first).toHaveTextContent(`Postfach · in 1 Lauf abgerufen · offen seit ${whenLabel(ADDED)} · zuletzt ${whenLabel(TRIED)}`)
  expect(within(first).getByRole('link', { name: /Stelle 1/ })).toHaveAttribute('href', 'https://jobs.example.com/1')
  expect(within(first).getByRole('link', { name: /Stelle 1/ })).toHaveAttribute('target', '_blank')
  expect(third).toHaveTextContent('Nicht beurteilbar')
  for (const row of rows()) expect(row.className).not.toMatch(/danger/)
})

test('a pasted link is labelled "Alert-Mail", and several runs read "in 3 Läufen abgerufen"', async () => {
  serve([link(1, { source: 'paste', tries: 3 })])
  render(<App />)
  expect(await screen.findByRole('heading', { level: 2, name: '1 offener Link' })).toBeVisible()
  expect(rows()[0]).toHaveTextContent('Alert-Mail · in 3 Läufen abgerufen')
})

test('the attempts of the last try sit behind "Details: n Versuche", in German and without an address', async () => {
  serve([link(1, { attempts: [{ step: 'plain', outcome: 'HTTP 503' }, { step: 'rendered', outcome: 'browser failed' }] })])
  render(<App />)
  await screen.findByRole('list', { name: 'Offene Links' })
  const details = within(rows()[0]).getByText('Details: 2 Versuche')
  await userEvent.click(details)
  expect(within(rows()[0]).getByText(/Einfacher Abruf:/)).toBeVisible()
  expect(within(rows()[0]).getByText('(Abruf im Browser gescheitert)')).toBeVisible()
})

test('a link a run did not reach reads "Nicht gestartet" and says the run ended before it', async () => {
  serve([link(1, { state: 'not_reached', tries: 0, last_tried_at: null, attempts: [] })])
  render(<App />)
  await screen.findByRole('list', { name: 'Offene Links' })
  const [row] = rows()
  expect(row).toHaveTextContent('Nicht gestartet')
  expect(row).toHaveTextContent('noch in keinem Lauf abgerufen')
  expect(row).toHaveTextContent('Der Lauf wurde beendet, bevor er diesen Link erreicht hat.')
  expect(row).not.toHaveTextContent('zuletzt')
})

test('an unread link without attempts says it could not be read', async () => {
  serve([link(1, { attempts: [], reason: 'ValueError' })])
  render(<App />)
  await screen.findByRole('list', { name: 'Offene Links' })
  expect(rows()[0]).toHaveTextContent('Diese Anzeige konnte nicht gelesen werden.')
})

test('without open links the tab says that no link is open', async () => {
  serve([])
  render(<App />)
  expect(await screen.findByRole('heading', { level: 2, name: 'Keine offenen Links' })).toBeVisible()
  expect(screen.queryByRole('list', { name: 'Offene Links' })).toBeNull()
})

test('an unreadable list says so and names the file, and no badge shows', async () => {
  stubApi({ 'GET /pool': { body: POOL }, 'GET /policy-pack/login-wall-hosts': { body: { hosts: [] } },
            'GET /unsettled-links': { status: 503, body: { error: 'unsettled links unreadable', detail: 'unsettled-links.json: invalid' } } })
  render(<App />)
  const notice = await screen.findByRole('alert')
  expect(notice).toHaveTextContent('Die Liste der offenen Links (unsettled-links.json im Datenrepository) ist nicht lesbar.')
  expect(nav().getByRole('link', { name: 'Anzeige hinzufügen' })).toBeVisible()
  expect(tabs().getByRole('button', { name: 'Offene Links' })).toBeVisible()
})

test('a list that cannot be loaded offers a retry', async () => {
  let fail = true
  serve([link(1)], null, { 'GET /unsettled-links': () => fail ? { status: 500, body: { error: 'boom' } } : { body: { links: [link(1)], run_id: null } } })
  render(<App />)
  expect(await screen.findByRole('heading', { name: 'Offene Links konnten nicht geladen werden' })).toBeVisible()
  fail = false
  await userEvent.click(screen.getByRole('button', { name: 'Erneut versuchen' }))
  expect(await screen.findByRole('heading', { level: 2, name: '1 offener Link' })).toBeVisible()
})

test('removing a link takes its row away at once, announces it, lowers both badges and focuses the next row', async () => {
  const list = [link(1), link(2), link(3)]
  const calls = serve(list)
  render(<App />)
  expect(await nav().findByRole('link', { name: 'Anzeige hinzufügen, 3 offene Links' })).toBeVisible()
  await userEvent.click(within(rows()[0]).getByRole('button', { name: 'Entfernen' }))
  expect(calls.find((call) => call.method === 'DELETE')!.body).toEqual({ url: 'https://jobs.example.com/1' })
  expect(await screen.findByRole('heading', { level: 2, name: '2 offene Links' })).toBeVisible()
  expect(rows()).toHaveLength(2)
  expect(screen.getByText('„Stelle 1“ entfernt.')).toHaveAttribute('role', 'status')
  expect(await nav().findByRole('link', { name: 'Anzeige hinzufügen, 2 offene Links' })).toBeVisible()
  expect(tabs().getByRole('button', { name: 'Offene Links, 2 offene Links' })).toBeVisible()
  expect(within(rows()[0]).getByRole('button', { name: 'Entfernen' })).toHaveFocus()
})

test('removing the last row moves the focus to the heading', async () => {
  serve([link(1)])
  render(<App />)
  await screen.findByRole('list', { name: 'Offene Links' })
  await userEvent.click(within(rows()[0]).getByRole('button', { name: 'Entfernen' }))
  const heading = await screen.findByRole('heading', { level: 2, name: 'Keine offenen Links' })
  expect(heading).toHaveFocus()
})

test('a link that is gone already counts as removed, and one a run holds shows why it stays', async () => {
  serve([link(1), link(2)], null, {
    'DELETE /unsettled-links': (call) => (call.body as { url: string }).url.endsWith('/1')
      ? { status: 404, body: { error: 'not found' } } : { status: 409, body: { error: 'link in run' } },
  })
  render(<App />)
  await screen.findByRole('list', { name: 'Offene Links' })
  await userEvent.click(within(rows()[0]).getByRole('button', { name: 'Entfernen' }))
  expect(await screen.findByText('„Stelle 1“ ist nicht mehr in der Liste.')).toBeInTheDocument()
  await userEvent.click(within(rows()[1]).getByRole('button', { name: 'Entfernen' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Dieser Link wird gerade von einem Lauf abgerufen.')
})

test('while a run computes, the rows it still has to fetch cannot be removed and their info icon says why', async () => {
  serve([link(1), link(2, { state: 'waiting', in_run: true, tries: 0, last_tried_at: null, attempts: [] })], 'r1')
  render(<App />)
  await screen.findByRole('list', { name: 'Offene Links' })
  const [settled, waiting] = rows()
  expect(within(settled).getByRole('button', { name: 'Entfernen' })).toBeEnabled()
  expect(within(waiting).getByText('Wartet')).toBeVisible()
  expect(within(waiting).getByRole('button', { name: 'Entfernen' })).toBeDisabled()
  const why = within(waiting).getByRole('button', { name: 'Warum ist Entfernen nicht möglich?' })
  await userEvent.click(why)
  expect(within(waiting).getByRole('tooltip')).toHaveTextContent('Der laufende Lauf hat diesen Link noch vor sich.')
  expect(await nav().findByRole('link', { name: 'Anzeige hinzufügen, 1 offener Link' })).toBeVisible()
})

test('the tab has no accessibility violations', async () => {
  serve([link(1), link(2, { state: 'unclear' }), link(3, { state: 'not_reached', tries: 0, last_tried_at: null, attempts: [] })])
  const { container } = render(<App />)
  await screen.findByRole('list', { name: 'Offene Links' })
  expect(await axe(container)).toHaveNoViolations()
})
