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

/** The steps tried for a link, one line each, with their outcome in German. `attempts` are the
 * fetch ladder's, as `POST /postings` and the alert run report them. */
export function AttemptList({ attempts, className }: { attempts: Attempt[]; className?: string }) {
  return (
    <ol className={cn('flex list-decimal flex-col gap-1 pl-5', className)}>
      {attempts.map((attempt, index) => (
        <li key={index}>
          {STEPS[attempt.step] ?? attempt.step}:{' '}
          {attempt.outcome === 'skipped' ? 'übersprungen'
            : attempt.outcome === 'ok' ? 'keine Anzeige gefunden'
              : <>fehlgeschlagen <span lang="en" className="text-sm text-muted-foreground">({attempt.outcome})</span></>}
        </li>
      ))}
    </ol>
  )
}
