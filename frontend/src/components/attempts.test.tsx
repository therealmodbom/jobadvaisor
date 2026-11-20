import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { AttemptList } from './attempts'

test('a gone answer on the submitted link reads „Stelle geschlossen“, one from an alternative source stays failed', () => {
  render(<AttemptList attempts={[
    { step: 'plain', url: 'https://a.example.org/1', outcome: 'HTTP 404' },
    { step: 'loop:fetch_plain', url: 'https://b.example.org/2', outcome: 'HTTP 404' },
    { step: 'loop:fetch_rendered', url: 'https://b.example.org/2', outcome: 'closed page (redirect)' },
  ]} />)
  const items = screen.getAllByRole('listitem')
  expect(items[0]).toHaveTextContent('Einfacher Abruf: Stelle geschlossen (HTTP 404)')
  expect(items[1]).toHaveTextContent('Weitere Seite, einfacher Abruf: fehlgeschlagen (HTTP 404)')
  expect(items[2]).toHaveTextContent('Weitere Seite, Abruf im Browser: fehlgeschlagen (closed page (redirect))')
})
