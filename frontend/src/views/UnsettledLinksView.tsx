import { useEffect, useId, useRef, useState } from 'react'
import { CircleAlert, CirclePause, Clock, Trash2 } from 'lucide-react'
import { api, ApiError } from '@/api'
import { Notice } from '@/components/alert-pick'
import { AttemptDetails } from '@/components/alert-run'
import { OriginalLink } from '@/components/posting'
import { ErrorWithRetry, Loading } from '@/components/states'
import { Button } from '@/components/ui/button'
import { WhyDisabled } from '@/components/why'
import { PANEL, ROW, ROW_BUTTON } from '@/lib/alert'
import { whenLabel } from '@/lib/german'
import { notifyUnsettledLinks, type UnsettledLink, type UnsettledState } from '@/lib/unsettled-links'
import { cn } from '@/lib/utils'

/** The outcome word of a row, its tone and icon. Capitalised like every outcome word of the list;
 * the run view keeps its lower-case state words. Only the word carries a colour, the row stays neutral. */
const LABELS = {
  unread: { text: 'Nicht gelesen', tone: 'text-danger', Icon: CircleAlert },
  unclear: { text: 'Nicht beurteilbar', tone: 'text-danger', Icon: CircleAlert },
  not_reached: { text: 'Nicht gestartet', tone: 'text-muted-foreground', Icon: CirclePause },
  waiting: { text: 'Wartet', tone: 'text-muted-foreground', Icon: Clock },
}

/** The source tab „Offene Links“: the links alert runs could not settle, one neutral row each
 * with its outcome, title, link, meta line and attempts, and „Entfernen“ per row. `state` is the
 * list as `useUnsettledLinks` reads it (the intake view owns that read, so the tab and its badge
 * share one). A removal is announced, and the focus moves to the next row's „Entfernen“, else to
 * the heading. A row a computing run still has to fetch (`in_run`) cannot be removed. */
export function UnsettledLinksView({ state }: { state: UnsettledState }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  const removeButtons = useRef(new Map<string, HTMLButtonElement>())
  /** The row a removal went for and the row after it, until the list no longer holds the first. */
  const moveFocus = useRef<{ removed: string; next: string | null } | null>(null)
  const [announce, setAnnounce] = useState('')
  const [problem, setProblem] = useState('')

  useEffect(() => {
    const goal = moveFocus.current
    if (!goal || state.kind !== 'ready' || state.links.some((link) => link.url === goal.removed)) return
    moveFocus.current = null
    const next = goal.next ? removeButtons.current.get(goal.next) : undefined
    ;(next && !next.disabled ? next : headingRef.current)?.focus()
  }, [state])

  if (state.kind === 'loading') return <Loading label="Offene Links werden geladen" />
  if (state.kind === 'failed') {
    return <ErrorWithRetry title="Offene Links konnten nicht geladen werden" detail="Der Server ist nicht erreichbar."
                           onRetry={notifyUnsettledLinks} />
  }
  if (state.kind === 'unreadable') {
    return (
      <Notice danger Icon={CircleAlert} title="Offene Links nicht lesbar"
              text="Die Liste der offenen Links (unsettled-links.json im Datenrepository) ist nicht lesbar. Bis sie repariert ist, startet kein Lauf.">
        {null}
      </Notice>
    )
  }

  const { links } = state

  /** Removes `link` at once, without a confirm step: no posting or mail changes. A link that is
   * gone already counts as removed; the list is read again either way. */
  async function remove(link: UnsettledLink, index: number) {
    setProblem('')
    moveFocus.current = { removed: link.url, next: links[index + 1]?.url ?? null }
    try {
      await api('/unsettled-links', { method: 'DELETE', json: { url: link.url } })
      setAnnounce(`„${link.title || link.url}“ entfernt.`)
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setAnnounce(`„${link.title || link.url}“ ist nicht mehr in der Liste.`)
      } else {
        moveFocus.current = null
        setProblem(error instanceof ApiError && error.status === 409
          ? 'Dieser Link wird gerade von einem Lauf abgerufen. Danach kannst du ihn entfernen.'
          : 'Entfernen hat nicht geklappt. Versuch es noch einmal.')
      }
    }
    notifyUnsettledLinks()
  }

  return (
    <section aria-labelledby="unsettled-title" className={PANEL}>
      <div>
        <h2 id="unsettled-title" ref={headingRef} tabIndex={-1} className="text-lg font-bold">
          {links.length === 0 ? 'Keine offenen Links' : links.length === 1 ? '1 offener Link' : `${links.length} offene Links`}
        </h2>
        <p className="mt-0.5 text-[15px] text-muted-foreground">
          {links.length === 0
            ? 'Jeder Link der letzten Läufe wurde gespeichert, war schon da oder ist geschlossen.'
            : 'Diese Links konnte ein Lauf nicht klären. Ihre Mails gelten als gelesen, die Links warten hier. Entferne einen, wenn du ihn nicht mehr brauchst.'}
        </p>
      </div>
      <p role="status" className="sr-only">{announce}</p>
      {problem && <p role="alert" className="text-danger">{problem}</p>}
      {links.length > 0 && (
        <ul aria-label="Offene Links" className="flex flex-col gap-2.5">
          {links.map((link, index) => (
            <LinkRow key={link.url} link={link} removeRef={(button) => {
              if (button) removeButtons.current.set(link.url, button)
              else removeButtons.current.delete(link.url)
            }} onRemove={() => void remove(link, index)} />
          ))}
        </ul>
      )}
    </section>
  )
}

/** One unsettled link: its outcome, title, link, the meta line (source, runs, since when, last try),
 * what the outcome means where it needs a word, and the attempts of the last try. „Entfernen“ is
 * disabled with an info icon while a run still has to fetch the link; `removeRef` hands its button
 * to the list, for the focus move. */
function LinkRow({ link, removeRef, onRemove }: {
  link: UnsettledLink
  removeRef: (button: HTMLButtonElement | null) => void
  onRemove: () => void
}) {
  const whyId = useId()
  const { text, tone, Icon } = LABELS[link.state]
  const runs = link.tries === 0 ? 'noch in keinem Lauf abgerufen'
    : link.tries === 1 ? 'in 1 Lauf abgerufen' : `in ${link.tries} Läufen abgerufen`
  const meta = [
    link.source === 'mailbox' ? 'Postfach' : 'Alert-Mail',
    runs,
    `offen seit ${whenLabel(link.added_at)}`,
    link.last_tried_at && `zuletzt ${whenLabel(link.last_tried_at)}`,
  ].filter(Boolean).join(' · ')
  return (
    <li className={cn(ROW, 'max-sm:flex-col', link.state === 'waiting' && 'bg-background')}>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span className={cn('inline-flex items-center gap-1.5 font-bold', tone)}>
          <Icon className="size-4" aria-hidden="true" />{text}
        </span>
        <span className="font-bold">{link.title}</span>
        <OriginalLink url={link.url} label={link.url} name={link.title} className="self-start font-mono text-sm" />
        <span className="text-sm text-muted-foreground">{meta}</span>
        {link.state === 'unclear' && (
          <p className="text-[15px]">
            Der Link hat einmal geantwortet, die Stelle sei geschlossen, andere Abrufe wurden aber abgewiesen. Ob sie
            wirklich geschlossen ist, ist unklar.
          </p>
        )}
        {link.state === 'unread' && link.attempts.length === 0 && (
          <p className="text-[15px]">Diese Anzeige konnte nicht gelesen werden.</p>
        )}
        {link.state === 'not_reached' && link.tries === 0 && (
          <p className="text-[15px]">Der Lauf wurde beendet, bevor er diesen Link erreicht hat.</p>
        )}
        <AttemptDetails attempts={link.attempts} />
      </div>
      <div className="flex items-start gap-1 max-sm:w-full">
        <div className="flex flex-col gap-2 max-sm:flex-1 sm:w-[190px]">
          <Button type="button" size="sm" variant="outline" ref={removeRef} disabled={link.in_run}
                  aria-describedby={link.in_run ? whyId : undefined} onClick={onRemove}
                  className={cn(ROW_BUTTON, 'sm:w-full')}>
            <Trash2 className="size-4" aria-hidden="true" />Entfernen
          </Button>
        </div>
        {link.in_run && (
          <WhyDisabled id={whyId} label="Warum ist Entfernen nicht möglich?"
                       reason="Der laufende Lauf hat diesen Link noch vor sich. Danach kannst du ihn entfernen." />
        )}
      </div>
    </li>
  )
}
