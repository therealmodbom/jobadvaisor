import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { AttemptList } from './attempts'

/** One attempt on the plain step with `outcome`, rendered; returns its list item. */
function line(outcome: string) {
  render(<AttemptList attempts={[{ step: 'plain', url: 'https://a.example.org/1', outcome }]} />)
  return screen.getByRole('listitem')
}

test('a gone answer on the submitted link reads „Stelle geschlossen“, one from an alternative source stays failed', () => {
  render(<AttemptList attempts={[
    { step: 'plain', url: 'https://a.example.org/1', outcome: 'HTTP 404' },
    { step: 'loop:fetch_plain', url: 'https://b.example.org/2', outcome: 'HTTP 404' },
    { step: 'loop:fetch_rendered', url: 'https://b.example.org/2', outcome: 'closed page (redirect)' },
  ]} />)
  const items = screen.getAllByRole('listitem')
  expect(items[0]).toHaveTextContent('Einfacher Abruf: Stelle geschlossen (HTTP 404)')
  expect(items[1]).toHaveTextContent('Weitere Seite, einfacher Abruf: fehlgeschlagen (HTTP 404)')
  expect(items[2]).toHaveTextContent('Weitere Seite, Abruf im Browser: fehlgeschlagen (Weiterleitung auf eine geschlossene Stelle)')
})

// The reasons the backend raises today (design.md, „German reasons by table“); a prefix reason
// comes with a sample tail that must not show.
const REASONS: [string, string][] = [
  ['no posting text', 'kein Anzeigentext gefunden'],
  ['no job-board detail URL', 'kein Link zur Anzeige in der Jobbörse'],
  ['unparseable answer', 'Antwort nicht lesbar'],
  ['connection failed: ConnectError', 'keine Verbindung'],
  ['browser failed: TimeoutError', 'Abruf im Browser gescheitert'],
  ['fetch failed: ReadTimeout', 'Abruf gescheitert'],
  ['too many redirects', 'zu viele Weiterleitungen'],
  ['invalid URL', 'ungültiger Link'],
  ['redirect with personal parameters', 'Weiterleitung mit persönlichen Daten, nicht gefolgt'],
  ['redirect to a non-public address', 'Weiterleitung an eine nicht öffentliche Adresse, nicht gefolgt'],
  ['closed page (redirect)', 'Weiterleitung auf eine geschlossene Stelle'],
  ['closed page (page text)', 'Seite meldet die Stelle als geschlossen'],
  ['login-walled host, not fetched', 'Seite mit Login-Pflicht, nicht abgerufen'],
  ['screening failed', 'Inhaltsprüfung gescheitert'],
  ['withheld by the content guard', 'vom Inhaltsfilter zurückgehalten'],
  ['search failed', 'Websuche gescheitert'],
]

test.each(REASONS)('the reason „%s“ shows German and never its English text', (reason, german) => {
  const item = line(reason)
  expect(item).toHaveTextContent(`(${german})`)
  expect(item).not.toHaveTextContent(reason.split(':')[0])
  expect(item).not.toHaveTextContent('ConnectError')
  expect(item).not.toHaveTextContent('TimeoutError')
  expect(item).not.toHaveTextContent('ReadTimeout')
  expect(item.querySelector('[lang="en"]')).toBeNull()
})

test('no posting text reads „fehlgeschlagen (kein Anzeigentext gefunden)“', () => {
  expect(line('no posting text')).toHaveTextContent('Einfacher Abruf: fehlgeschlagen (kein Anzeigentext gefunden)')
})

test('an HTTP status keeps its code and is not marked as English', () => {
  const item = line('HTTP 429')
  expect(item).toHaveTextContent('Einfacher Abruf: fehlgeschlagen (HTTP 429)')
  expect(item.querySelector('[lang="en"]')).toBeNull()
})

test('a reason the view does not know shows as it came and is marked as English', () => {
  const item = line('some new reason')
  expect(item).toHaveTextContent('Einfacher Abruf: fehlgeschlagen (some new reason)')
  expect(item.querySelector('[lang="en"]')).toHaveTextContent('(some new reason)')
})
