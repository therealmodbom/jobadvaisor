import type { Attempt } from '@/api'
import { cn } from '@/lib/utils'

/** What the list shows of an attempt: the step and its outcome. The unsettled-links list keeps no
 * address, so its attempts have no `url`. */
export type ShownAttempt = Pick<Attempt, 'step' | 'outcome'> & Partial<Pick<Attempt, 'url'>>

const STEPS: Record<string, string> = {
  bundesagentur: 'Jobbörse der Bundesagentur',
  plain: 'Einfacher Abruf',
  rendered: 'Abruf im Browser',
  login_wall: 'Seite mit Login-Pflicht',
  'loop:fetch_plain': 'Weitere Seite, einfacher Abruf',
  'loop:fetch_rendered': 'Weitere Seite, Abruf im Browser',
  'loop:search_alternative_source': 'Websuche nach einer anderen Quelle',
}

/** The reasons the backend raises (`fetch.py`, `bundesagentur.py`, `loop.py`), in German. */
const REASONS: Record<string, string> = {
  'no posting text': 'kein Anzeigentext gefunden',
  'no job-board detail URL': 'kein Link zur Anzeige in der Jobbörse',
  'unparseable answer': 'Antwort nicht lesbar',
  'too many redirects': 'zu viele Weiterleitungen',
  'invalid URL': 'ungültiger Link',
  'redirect with personal parameters': 'Weiterleitung mit persönlichen Daten, nicht gefolgt',
  'redirect to a non-public address': 'Weiterleitung an eine nicht öffentliche Adresse, nicht gefolgt',
  'closed page (redirect)': 'Weiterleitung auf eine geschlossene Stelle',
  'closed page (page text)': 'Seite meldet die Stelle als geschlossen',
  'login-walled host, not fetched': 'Seite mit Login-Pflicht, nicht abgerufen',
  'screening failed': 'Inhaltsprüfung gescheitert',
  'withheld by the content guard': 'vom Inhaltsfilter zurückgehalten',
  'search failed': 'Websuche gescheitert',
}

/** Reasons with a variable tail after the prefix (an exception name, a browser message); the tail is dropped. */
const REASON_PREFIXES: [string, string][] = [
  ['connection failed', 'keine Verbindung'],
  ['browser failed', 'Abruf im Browser gescheitert'],
  ['fetch failed', 'Abruf gescheitert'],
]

/** The reason of a failed attempt in parentheses: German from the tables, `HTTP <n>` as it is,
 * and a reason the tables do not know as it came, marked `lang="en"`. */
function Reason({ outcome }: { outcome: string }) {
  const known = REASONS[outcome] ?? REASON_PREFIXES.find(([prefix]) => outcome.startsWith(prefix))?.[1]
  const english = !known && !/^HTTP \d+$/.test(outcome)
  return <span lang={english ? 'en' : undefined} className="text-sm text-muted-foreground">({known ?? outcome})</span>
}

/** The outcomes of an attempt that found the posting gone (the fetch ladder's own wording). */
const GONE = /^(HTTP 404|HTTP 410|closed page \((redirect|page text)\))$/

/** Whether the attempt found the submitted link gone: a `loop:*` step fetches another page of
 * the search for the posting, so a gone answer there is just a failed step. */
function isGone(attempt: ShownAttempt) {
  return !attempt.step.startsWith('loop:') && GONE.test(attempt.outcome)
}

/** The steps tried for a link, one line each, with their outcome in German. `attempts` are the
 * fetch ladder's, as `POST /postings` and the alert run report them; an attempt on the submitted
 * link that found the posting gone reads „Stelle geschlossen“, one on an alternative source
 * (`loop:*`) stays „fehlgeschlagen“. */
export function AttemptList({ attempts, className }: { attempts: ShownAttempt[]; className?: string }) {
  return (
    <ol className={cn('flex list-decimal flex-col gap-1 pl-5', className)}>
      {attempts.map((attempt, index) => (
        <li key={index}>
          {STEPS[attempt.step] ?? attempt.step}:{' '}
          {attempt.outcome === 'skipped' ? 'übersprungen'
            : attempt.outcome === 'ok' ? 'keine Anzeige gefunden'
              : <>{isGone(attempt) ? 'Stelle geschlossen' : 'fehlgeschlagen'} <Reason outcome={attempt.outcome} /></>}
        </li>
      ))}
    </ol>
  )
}
