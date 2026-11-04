import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test, vi } from 'vitest'
import { axe } from '@/test-axe'
import { EmptyState, ErrorWithRetry, Loading } from './states'

test('loading announces what it waits for', () => {
  render(<Loading label="Durchlauf wird geladen" />)
  expect(screen.getByRole('status')).toHaveTextContent('Durchlauf wird geladen')
})

test('an error says what failed and retries on request', async () => {
  const retry = vi.fn()
  render(<ErrorWithRetry title="Durchläufe konnten nicht geladen werden"
                         detail="Der Server antwortet nicht." onRetry={retry} />)
  expect(screen.getByRole('alert')).toHaveTextContent('Der Server antwortet nicht.')
  await userEvent.click(screen.getByRole('button', { name: 'Erneut versuchen' }))
  expect(retry).toHaveBeenCalledOnce()
})

test('an empty state says what to do next', () => {
  render(<EmptyState title="Noch kein Durchlauf" text="Starte einen, um Anzeigen zu bewerten.">
    <button type="button">Durchlauf starten</button>
  </EmptyState>)
  expect(screen.getByRole('heading', { name: 'Noch kein Durchlauf' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Durchlauf starten' })).toBeVisible()
})

test('the shared states have no accessibility violations', async () => {
  const { container } = render(<>
    <Loading label="Lädt" />
    <ErrorWithRetry title="Fehler" onRetry={() => {}} />
    <EmptyState title="Leer" text="Nichts da." />
  </>)
  expect(await axe(container)).toHaveNoViolations()
})
