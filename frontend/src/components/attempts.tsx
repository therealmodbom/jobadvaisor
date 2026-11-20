import type { Attempt } from '@/api'
import { cn } from '@/lib/utils'

const STEPS: Record<string, string> = {
  bundesagentur: 'Jobbörse der Bundesagentur',
  plain: 'Einfacher Abruf',
  rendered: 'Abruf im Browser',
  login_wall: 'Seite mit Login-Pflicht',
  'loop:fetch_plain': 'Weitere Seite, einfacher Abruf',
  'loop:fetch_rendered': 'Weitere Seite, Abruf im Browser',
  'loop:search_alternative_source': 'Websuche nach einer anderen Quelle',
}

/** The outcomes of an attempt that found the posting gone (the fetch ladder's own wording). */
const GONE = /^(HTTP 404|HTTP 410|closed page \((redirect|page text)\))$/

/** The steps tried for a link, one line each, with their outcome in German. `attempts` are the
 * fetch ladder's, as `POST /postings` and the alert run report them; an attempt that found the
 * posting gone reads „Stelle geschlossen“. */
export function AttemptList({ attempts, className }: { attempts: Attempt[]; className?: string }) {
  return (
    <ol className={cn('flex list-decimal flex-col gap-1 pl-5', className)}>
      {attempts.map((attempt, index) => (
        <li key={index}>
          {STEPS[attempt.step] ?? attempt.step}:{' '}
          {attempt.outcome === 'skipped' ? 'übersprungen'
            : attempt.outcome === 'ok' ? 'keine Anzeige gefunden'
              : <>{GONE.test(attempt.outcome) ? 'Stelle geschlossen' : 'fehlgeschlagen'} <span lang="en" className="text-sm text-muted-foreground">({attempt.outcome})</span></>}
        </li>
      ))}
    </ol>
  )
}
