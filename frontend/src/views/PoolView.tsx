import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { Check, ChevronDown, ChevronUp, CircleSlash, Compass, ShieldAlert, Square } from 'lucide-react'
import { DropdownMenu } from 'radix-ui'
import { api, ApiError, type Counter, type NextPass, type PassProgress, type PassState, type PassVariant, type Pool, type PoolRow, type RatingAnswer, type ScoreAnswer, type Status, type Strength, type Verdict } from '@/api'
import { CheckButton, CheckStatus } from '@/components/check'
import { Badge, ChipList, ScoreButton, ScoreProblem, ScoreText, StatusControl } from '@/components/posting'
import { ProgressBlock } from '@/components/progress'
import { Legend, ReasonsAndNote, VerdictButtons } from '@/components/rating'
import { EmptyState, ErrorWithRetry, Loading } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { WhyDisabled } from '@/components/why'
import { useCheck } from '@/lib/check'
import { addedLabel, STATUSES } from '@/lib/german'
import { FULL_RANGE, inRange, NO_SCORE, SORTS, sortRows, TOP_SCORE, type ScoreRange, type Sort } from '@/lib/pool-order'
import { LEVELS, strayPaste, useRating, type Rating } from '@/lib/rating'
import { POLL_FAILURES, POLL_MS, SWAP_LOCK_MS, useSwapLock } from '@/lib/run'
import { useScore, type ScoreCall } from '@/lib/score'
import { cn, without } from '@/lib/utils'

export { POLL_FAILURES, POLL_MS, SWAP_LOCK_MS }
const PASS_KEY = 'jobadvaisor.pool-pass'

/** The pass ID kept across a reload; storage may be blocked, so every access is guarded. */
const storedPass = {
  get: () => {
    try {
      return sessionStorage.getItem(PASS_KEY)
    } catch {
      return null
    }
  },
  set: (id: string | null) => {
    try {
      if (id) sessionStorage.setItem(PASS_KEY, id)
      else sessionStorage.removeItem(PASS_KEY)
    } catch { /* storage blocked: a reload simply does not resume */ }
  },
}

const verdictOf = (row: PoolRow) => row.label?.verdict ?? null
/** The posting's availability is closed (a check or the user set it; unknown is not closed). */
const isClosed = (row: PoolRow) => row.availability?.state === 'closed'

/** The filters; each keeps the rows it shows, in the server's order. "Offen", "Noch nicht
 * bewertet" and "Bewertet" leave closed postings out, "Stelle geschlossen" lists the closed ones
 * with application status open, and "Herkunft" keeps every imported row whatever its status. */
const FILTERS: { id: string; label: string; keep: (row: PoolRow) => boolean }[] = [
  { id: 'open', label: 'Offen', keep: (row) => row.status === 'open' && !isClosed(row) },
  { id: 'unrated', label: 'Noch nicht bewertet', keep: (row) => row.status === 'open' && !isClosed(row) && verdictOf(row) === null },
  { id: 'rated', label: 'Bewertet', keep: (row) => row.status === 'open' && !isClosed(row) && verdictOf(row) !== null },
  { id: 'applied', label: 'Beworben', keep: (row) => row.status === 'applied' },
  { id: 'done', label: 'Erledigt', keep: (row) => row.status === 'done' },
  { id: 'closed', label: 'Stelle geschlossen', keep: (row) => row.status === 'open' && isClosed(row) },
  { id: 'imported', label: 'Herkunft', keep: (row) => row.origin !== null },
]

/** The scoring pass: starts it, polls it while it runs, remembers its ID across a reload.
 * `onDone` runs when a pass ends with scores to show: done or cancelled. `busy` is true while one
 * runs or waits for an answer. `cancelling` is true from the accepted cancel request on, so a
 * poll that started before it cannot enable the button again. `cancelledScored` is the number a
 * cancelled pass stored (null: none was cancelled, or a later pass started). */
function usePass(onDone: () => void) {
  const [passId, setPassId] = useState<string | null>(storedPass.get)
  const [pass, setPass] = useState<PassState | null>(null)
  const [notice, setNotice] = useState('')
  const [pollFailed, setPollFailed] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [cancelledScored, setCancelledScored] = useState<number | null>(null)
  const sending = useRef(false)
  const running = passId !== null && (pass === null || pass.status === 'running')
  const busy = running || pass?.status === 'awaiting_answer'

  useEffect(() => {
    if (!passId || !running || pollFailed) return
    let failures = 0
    const timer = setInterval(() => {
      api<PassState>(`/pool/passes/${passId}`).then((next) => {
        failures = 0
        if (next.status === 'done' || next.status === 'cancelled') {
          storedPass.set(null)
          setPassId(null)
          setPass(null)
          if (next.status === 'cancelled') setCancelledScored(next.scored)
          onDone()
        } else {
          if (next.status === 'aborted' || next.status === 'failed') storedPass.set(null)
          setPass(next)
        }
      }, (error) => {
        if (error instanceof ApiError && error.status === 404) {
          storedPass.set(null)
          setPassId(null)
        } else if (++failures >= POLL_FAILURES) {
          clearInterval(timer)
          setPollFailed(true)
        }
      })
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [passId, running, pollFailed, onDone])

  /** Run one pass request; `sending` makes a double click send one. */
  async function send(request: () => Promise<void>, conflict: string, failure: string) {
    if (sending.current) return
    sending.current = true
    setNotice('')
    try {
      await request()
    } catch (error) {
      setNotice(error instanceof ApiError && error.status === 409 ? conflict : failure)
    } finally {
      sending.current = false
    }
  }
  /** Start the pass of `variant`; the server decides what it scores from the name alone. */
  const start = (variant: PassVariant) => send(async () => {
    const answer = await api<{ pass_id: string }>('/pool/passes', { method: 'POST', json: { variant } })
    storedPass.set(answer.pass_id)
    setPass(null)
    setPollFailed(false)
    setCancelling(false)
    setCancelledScored(null)
    setPassId(answer.pass_id)
  }, 'Es wird schon gescort. Warte, bis das fertig ist.',
  'Das Scoren konnte nicht gestartet werden. Ist der Server erreichbar?')
  const answer = (proceed: boolean) => send(async () => {
    await api(`/pool/passes/${passId}/unscreened`, { method: 'POST', json: { continue: proceed } })
    setPass((current) => current && { ...current, status: 'running' })
  }, 'Gerade wird schon gescort. Antworte, wenn das fertig ist.',
  'Die Antwort wurde nicht gespeichert. Versuch es noch einmal.')
  // A 409 means the pass ended or paused in between; the next poll shows that, so it says nothing.
  const cancel = () => send(async () => {
    await api(`/pool/passes/${passId}/cancel`, { method: 'POST' })
    setCancelling(true)
  }, '', 'Das Scoren konnte nicht abgebrochen werden. Versuch es noch einmal.')
  return { pass, busy, notice, start, answer, cancel, cancelling, cancelledScored, pollFailed,
           retryPoll: () => setPollFailed(false) }
}

const HINT_DEFAULT = 'Abbrechen hält nach der aktuellen Anzeige an. Was schon gescort ist, bleibt gespeichert.'
/** The default hint is shorter on a phone (design: A-Phone), so it keeps its two lines there. */
const HINT_DEFAULT_PHONE = 'Abbrechen hält nach der aktuellen Anzeige an. Gescortes bleibt gespeichert.'
const HINT_STOPPING = 'Wird nach der aktuellen Anzeige beendet.'
const HINT_STORING = 'Das Speichern lässt sich nicht mehr abbrechen.'

/** The progress of a running pass, below the pass button in the pass column: a head line with the
 * loader, a bar and a hint line, each of fixed height (the hint always has two lines' room), so the
 * block keeps one size in every phase. `progress` null (no report yet) reads like checking: no
 * count, empty bar. The bar fills with `done`/`total` while scoring and is full while storing. The
 * hint (`#cancel-why`, the cancel button's description) says what a cancel does, that one was
 * requested (`stopping`), or why storing cannot be cancelled. Only texts and the bar change. */
function PassProgressBlock({ progress, stopping }: { progress: PassProgress | null; stopping: boolean }) {
  const phase = progress?.phase ?? 'checking'
  const score = progress?.score ?? null
  const storing = phase === 'storing'
  const counted = phase === 'checking' ? null : score
  const total = Math.max(score?.total ?? 1, 1)
  const [value, max] = storing ? [total, total] : counted ? [counted.done, total] : [0, 1]
  const head = storing ? 'Scores werden gespeichert'
    : counted ? `Scoren läuft: ${counted.done} von ${counted.total}` : 'Scoren läuft: Anzeigen prüfen…'
  // The bar is full while storing, but its name says how many were scored (a cancel stores fewer).
  const barLabel = counted ? `Scoren: ${counted.done} von ${counted.total}` : storing ? 'Scores speichern' : 'Anzeigen prüfen'
  return (
    <ProgressBlock label="Stand des Scorens" head={head} barLabel={barLabel} value={value} max={max} hintId="cancel-why"
                   hintClass={cn('h-10 text-muted-foreground', stopping && !storing && 'font-bold text-foreground')}
                   hint={storing ? HINT_STORING : stopping ? HINT_STOPPING : (
                     <>
                       <span className="sm:hidden">{HINT_DEFAULT_PHONE}</span>
                       <span className="max-sm:hidden">{HINT_DEFAULT}</span>
                     </>
                   )} />
  )
}

/** The status-region sentence for a cancelled pass that stored `scored` scores. */
const cancelledText = (scored: number) => `Das Scoren wurde abgebrochen. ${
  scored === 0 ? 'Keine Anzeige hat' : scored === 1 ? '1 Anzeige hat' : `${scored} Anzeigen haben`} einen neuen Score.`

const VARIANT_TITLE: Record<PassVariant, string> = { unscored: 'Nur Anzeigen ohne Score', all: 'Alle Anzeigen neu scoren' }
const VARIANT_VERBS: Record<PassVariant, string> = { unscored: 'Anzeigen ohne Score scoren', all: 'Alle Anzeigen neu scoren' }
/** Why a pass of the shown variant has nothing to score; the "unscored" reason points at the menu
 * only while "all" has postings. */
const NOTHING_TO_SCORE: Record<PassVariant, (next: NextPass) => string> = {
  unscored: (next) => `Es gibt keine Anzeigen ohne Score.${next.all > 0 ? ' Über den Pfeil wählst du „Alle Anzeigen neu scoren“.' : ''}`,
  all: () => 'Es gibt nichts zu scoren: Alle Anzeigen sind ausgeschlossen oder zurückgehalten.',
}

/** What a pass of `variant` over `n` postings costs: one model call per posting. */
function costLine(variant: PassVariant, n: number) {
  const postings = n === 1 ? '1 Anzeige' : `${n} Anzeigen`
  return variant === 'unscored' ? `${postings} ohne Score, je ein Modellaufruf.`
    : `${postings}, je ein Modellaufruf. Vorhandene Scores werden ersetzt.`
}

/** The scoring pass as a split button that turns into its own cancel button.
 * Idle (`working` false): the main part starts the pass of the `shown` variant, the trigger opens a
 * menu whose entries `onPick` a variant, with its count and cost, without starting anything. When
 * the main part is disabled (no postings for the variant, or a pass is `busy`) a focusable info
 * icon beside the button gives the reason, which is also the main part's description. Only `busy`
 * disables the trigger.
 * `working` (a pass computes): the split button gives way to one outline button that calls
 * `onCancel`. Both sit in one grid cell, the split button stays in the layout, `invisible` and
 * `inert`, and reserves the width, so nothing beside it moves when a pass starts or ends; the info
 * icon is not shown. `stopping` (a cancel was requested): the button reads "Wird beendet…".
 * `storing`: it keeps its label but cannot cancel any more. In both it is `aria-disabled`, not
 * `disabled`, so it keeps focus and a further Enter does nothing; `#cancel-why` (the progress
 * block's hint) gives the reason.
 * Swap delay: for `SWAP_LOCK_MS` after each swap the button that appeared is `aria-disabled` and
 * ignores presses, so a double click cannot cancel the pass it just started, nor a late cancel
 * click start a new one.
 * Focus: the main part is never natively `disabled` (no postings for the variant, a pass `busy`,
 * the swap delay): it is `aria-disabled` with a click guard, so it keeps focus when a reload or a
 * pass sets its count to 0 and a further Enter lands on a button, not on the pool's row shortcuts.
 * When focus was inside the button area before a swap, it moves with the swap: to the cancel button
 * when a pass starts, back to the main part when it ends, or to the unscreened question's heading
 * when the pass stopped at that question (never to a button that starts paid work). Focus inside
 * that question counts as inside the area, so answering it carries focus on the same way. */
function PassButton({ nextPass, shown, busy, working, stopping, storing, onPick, onStart, onCancel }: {
  nextPass: NextPass
  shown: PassVariant
  busy: boolean
  working: boolean
  stopping: boolean
  storing: boolean
  onPick: (variant: PassVariant) => void
  onStart: (variant: PassVariant) => void
  onCancel: () => void
}) {
  const [open, setOpen] = useState(false)
  // A pass that starts while the menu is open closes it (render-time sync, no effect).
  if (busy && open) setOpen(false)
  // A swap locks the new button for SWAP_LOCK_MS and hands focus on (lib/run.ts).
  const { locked, handoff, seenWorking } = useSwapLock(working, '[data-pass-area]')
  const reasonId = useId()
  const mainRef = useRef<HTMLButtonElement>(null)
  const cancelRef = useRef<HTMLButtonElement>(null)
  // Both buttons stay mounted, so the target exists at commit time. Nothing here starts paid work:
  // the pass button, even when the swap goes back to it, is `aria-disabled` for the swap delay.
  // Both buttons use `transition-colors`, not the base `transition-all`: a transition on
  // `visibility` keeps the button that just appeared `hidden` for a moment, and Chromium refuses
  // `focus()` on it.
  useLayoutEffect(() => {
    if (!handoff) return
    const question = document.getElementById('unscreened-title')
    const target = seenWorking ? cancelRef.current : question ?? mainRef.current
    target?.focus()
  }, [handoff, seenWorking])
  const count = nextPass[shown]
  // Why the main part cannot start now; null while it can (the cost is in the menu).
  const why = busy ? 'Das Scoren läuft.' : count === 0 ? NOTHING_TO_SCORE[shown](nextPass) : null
  const Chevron = open ? ChevronUp : ChevronDown
  const cancelDead = locked || stopping || storing
  const mainDead = locked || busy || count === 0
  return (
    <div className="flex items-center gap-1">
      <div data-pass-area className="grid max-sm:flex-1">
        <div role="group" aria-label="Scoren" inert={working} aria-hidden={working || undefined}
             className={cn('col-start-1 row-start-1 flex', working && 'invisible')}>
          <Button ref={mainRef} onClick={() => { if (!mainDead) onStart(shown) }}
                  aria-disabled={mainDead || undefined} aria-describedby={why ? reasonId : undefined}
                  className={cn('min-w-0 flex-1 rounded-r-none transition-colors', (busy || count === 0) && 'cursor-default opacity-50 hover:bg-primary')}>
            {/* Both labels share one grid cell, so the button keeps the wider one's size when the
                variant changes; the hidden one only reserves space. */}
            <span className="grid justify-items-center">
              {(['unscored', 'all'] as const).map((variant) => (
                <span key={variant} aria-hidden={variant !== shown || undefined}
                      className={cn('col-start-1 row-start-1', variant !== shown && 'invisible')}>
                  {VARIANT_VERBS[variant]} ({nextPass[variant]})
                </span>
              ))}
            </span>
          </Button>
          <DropdownMenu.Root open={open} onOpenChange={setOpen}>
            <DropdownMenu.Trigger asChild>
              <Button className="w-11 rounded-l-none border-l border-primary-foreground/45 px-0"
                      aria-label="Andere Variante wählen" disabled={busy}>
                <Chevron aria-hidden="true" />
              </Button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content align="start" sideOffset={6} collisionPadding={16} aria-label="Variante"
                                    className="z-50 flex w-[min(380px,calc(100vw-2rem))] flex-col gap-0.5 rounded-xl border bg-card p-1.5 shadow-card">
                <DropdownMenu.RadioGroup value={shown} onValueChange={(value) => onPick(value as PassVariant)}>
                  {(['unscored', 'all'] as const).map((variant) => (
                    <DropdownMenu.RadioItem key={variant} value={variant}
                                            className="flex min-h-11 cursor-pointer items-start gap-2.5 rounded-md px-2.5 py-2 outline-none data-[highlighted]:bg-muted">
                      <span className="mt-1 size-4 flex-none text-primary">
                        <DropdownMenu.ItemIndicator><Check className="size-4" aria-hidden="true" /></DropdownMenu.ItemIndicator>
                      </span>
                      <span className="flex flex-col">
                        <span className="font-bold">{VARIANT_TITLE[variant]} ({nextPass[variant]})</span>
                        <span className="text-sm text-muted-foreground">{costLine(variant, nextPass[variant])}</span>
                      </span>
                    </DropdownMenu.RadioItem>
                  ))}
                </DropdownMenu.RadioGroup>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        </div>
        <Button ref={cancelRef} variant="outline" inert={!working} aria-hidden={!working || undefined}
                aria-disabled={cancelDead ? true : undefined} aria-describedby="cancel-why"
                onClick={() => { if (!cancelDead) onCancel() }}
                className={cn('col-start-1 row-start-1 transition-colors', !working && 'invisible',
                  (stopping || storing) && 'cursor-default text-muted-foreground hover:bg-card')}>
          <Square aria-hidden="true" />{stopping && !storing ? 'Wird beendet…' : 'Scoren abbrechen'}
        </Button>
      </div>
      {why && !working && <WhyDisabled id={reasonId} label="Warum ist Scoren nicht möglich?" reason={why} />}
    </div>
  )
}

/** The question over postings the content guard never checked: names them, then go on or abort.
 * It is part of the pass button's focus area (`data-pass-area`): an answer unmounts the pressed
 * button, and `PassButton` then moves focus to the cancel button (the pass goes on) or, once the
 * aborted pass has ended, to its main part. */
function UnscreenedQuestion({ pass, onAnswer }: { pass: PassState; onAnswer: (proceed: boolean) => void }) {
  const count = pass.unscreened.length
  return (
    <section aria-labelledby="unscreened-title" data-pass-area
             className="flex max-w-[760px] flex-col gap-4 rounded-xl border bg-card p-6 shadow-card">
      <div className="flex items-start gap-3">
        <ShieldAlert className="mt-0.5 size-6 flex-none text-negative" aria-hidden="true" />
        <div>
          <h2 id="unscreened-title" tabIndex={-1} className="text-xl font-bold">Das Scoren wartet auf deine Antwort</h2>
          <p className="mt-1.5">
            {count === 1 ? 'Eine Anzeige wurde' : `${count} Anzeigen wurden`} hinzugefügt, während die
            Inhaltsprüfung aus war. Niemand hat sie auf Text geprüft, der sich an die KI richtet, etwa die
            Anweisung, einen Score zu erhöhen.
          </p>
        </div>
      </div>
      <ul className="ml-9 flex flex-col gap-1.5">
        {pass.unscreened.map((entry) => (
          <li key={entry.posting_id}><strong>{entry.title}</strong>, {entry.company}</li>
        ))}
      </ul>
      <p className="ml-9 text-muted-foreground">
        Score sie trotzdem, dann laufen sie mit den anderen durch. Oder brich ab: Dann wird nichts
        gescort, und du kannst die Inhaltsprüfung einschalten und neu starten.
      </p>
      <div className="ml-9 flex flex-wrap gap-2">
        <Button onClick={() => onAnswer(true)}>Trotzdem scoren</Button>
        <Button variant="outline" onClick={() => onAnswer(false)}>Abbrechen</Button>
      </div>
    </section>
  )
}

/** The one line below the pass button: the correction counter, the pool's hint ("Ranking passt gut"
 * or "neu scoren sinnvoll") and the share of corrections, or how many ratings it still needs
 * (`counter.rate` is null below ten). The menu of the pass button says what a pass costs. */
function CounterLine({ counter }: { counter: Counter }) {
  const rescore = counter.hint === 'rescore'
  return (
    <p className="text-sm text-muted-foreground">
      <strong className="text-foreground">{counter.corrections === 1 ? '1 Korrektur' : `${counter.corrections} Korrekturen`}</strong>
      {' · '}
      <span className={cn('font-bold', rescore ? 'text-negative' : 'text-primary')}>{rescore ? 'neu scoren sinnvoll' : 'Ranking passt gut'}</span>
      {' · '}
      <span>{counter.rate === null ? `Anteil ab 10 Bewertungen (bisher ${counter.rated})` : `Anteil ${Math.round(counter.rate * 100)} %`}</span>
    </p>
  )
}

/** One pool row: the "Hinzugefügt" line (when it entered the app), title link, company and location, score with its button, the "Stichprobe", "Stelle geschlossen" and
 * import marks, the rating (verdict buttons; the selected row also shows every reason chip and the
 * note field, the others their chosen reasons) and the status control. `onSelect` makes it the row
 * the shortcuts act on, `onLevel` sends a rating level. `onStatus` sends a new status; `saving`
 * and `failed` show its state, `failed` with a retry. `scoreCall` is the state of the row's score
 * button (`screening`: a content-guard classifier is configured), `onScore` sends its click. Focus
 * selects the row, except focus from a mouse press: that waits for the click, since selecting on
 * mousedown reflows the rows and the click would miss its target. */
function Row({ row, chips, rating, selected, onSelect, onLevel, saving, failed, onStatus, screening, scoreCall, onScore }: {
  row: PoolRow
  chips: Pool['reason_chips']
  rating: Rating
  selected: boolean
  onSelect: () => void
  onLevel: (verdict: Verdict, strength: Strength) => void
  saving: boolean
  failed: Status | undefined
  onStatus: (status: Status) => void
  screening: boolean
  scoreCall: ScoreCall
  onScore: () => void
}) {
  const now = rating.view(row)
  const pressed = useRef(false)
  // The press's own focus event fires in the same task, so a zero timeout clears a press that never focused.
  const press = () => { pressed.current = true; setTimeout(() => { pressed.current = false }) }
  return (
    <li id={`row-${row.posting_id}`} tabIndex={-1} onPointerDown={press}
        onFocusCapture={() => { if (!pressed.current) onSelect() }} onClick={onSelect}
        className={cn('flex flex-wrap items-start gap-x-6 gap-y-3 rounded-xl border bg-card px-5 py-4 shadow-card',
          selected && 'outline-2 outline-offset-2 outline-ring')}>
      <div className="min-w-0 flex-[3_1_280px]">
        <p className="text-[11px] leading-4 text-subtle-foreground">
          <time dateTime={new Date(row.added_at).toISOString()}>{addedLabel(row.added_at)}</time>
        </p>
        <h3 className="text-lg leading-snug font-bold">
          <a id={`title-${row.posting_id}`} href={`#/anzeigen/${encodeURIComponent(row.posting_id)}`} className="text-foreground">{row.title}</a>
        </h3>
        <p className="text-[15px] text-muted-foreground">{row.company}, {row.location_raw}</p>
        {(row.exploration || row.origin || isClosed(row)) && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {isClosed(row) && (
              <Badge className="bg-muted text-muted-foreground"><CircleSlash className="size-3.5" aria-hidden="true" />Stelle geschlossen</Badge>
            )}
            {row.exploration && (
              <Badge className="bg-explore-soft text-explore"><Compass className="size-4" aria-hidden="true" />Stichprobe</Badge>
            )}
            {row.origin && <Badge className="bg-muted text-foreground">Importiert aus {row.origin.table}</Badge>}
          </div>
        )}
      </div>
      <div className="flex min-w-0 flex-[2_1_200px] flex-col items-start gap-1.5">
        <p className="text-[15px]">
          <ScoreText row={row} />
        </p>
        <ScoreButton row={row} screening={screening} call={scoreCall} onScore={onScore} size="sm" />
        <ScoreProblem call={scoreCall} />
        {!selected && <ChipList ids={now.chips} chips={chips} />}
      </div>
      <StatusControl id={`status-${row.posting_id}`} title={row.title} value={row.status} saving={saving}
                     failed={failed} onStatus={onStatus} />
      <div className="w-full basis-full">
        <VerdictButtons row={row} rating={rating} onLevel={onLevel} keys={selected} />
      </div>
      {selected && <ReasonsAndNote row={row} chips={chips} rating={rating} keys highlight={now.verdict !== null} />}
    </li>
  )
}

/** The look of the pool's selects: the status control's, on the card background like the text field. */
const SELECT = 'min-h-11 rounded-lg border border-input bg-card px-2.5 text-[15px]'

/** The steps of the score range as `option`s: "ohne Score" (-1), then 0 to 10. */
function StepOptions() {
  return Array.from({ length: TOP_SCORE - NO_SCORE + 1 }, (_, index) => index + NO_SCORE).map((step) => (
    <option key={step} value={step}>{step === NO_SCORE ? 'ohne Score' : step}</option>
  ))
}

const END = 'Keine weitere unbewertete Anzeige.'

/** The ID of the next row after `from` (the first when `from` is unknown) that `unrated` accepts,
 * wrapping around and never `from` itself; `null` if there is none. */
const nextUnrated = (rows: PoolRow[], from: string | undefined, unrated: (row: PoolRow) => boolean) => {
  const start = rows.findIndex((row) => row.posting_id === from) + 1
  return [...rows.slice(start), ...rows.slice(0, Math.max(start - 1, 0))].find(unrated)?.posting_id ?? null
}

/** The pool view (`#/pool`): ranked postings from `GET /pool` with state and text filters, the
 * application status per row, the scoring pass with its progress and the correction counter with
 * its hint. Reloads whenever it becomes `active` or `reloadKey` changes (the header saved the settings). */
export function PoolView({ active = true, reloadKey = 0 }: { active?: boolean; reloadKey?: number }) {
  const [pool, setPool] = useState<Pool | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)
  const [filter, setFilter] = useState('open')
  const [text, setText] = useState('')
  const [range, setRange] = useState<ScoreRange>(FULL_RANGE)
  const [sort, setSort] = useState<Sort>('rank')
  const [saving, setSaving] = useState<Record<string, boolean>>({})
  const [failed, setFailed] = useState<Record<string, Status>>({})
  /** The posting the shortcut keys act on; `null` until one is chosen (then the first unrated). */
  const [selected, setSelected] = useState<string | null>(null)
  /** Postings rated or scored here: they stay in the "Noch nicht bewertet" list and outside the
   * score range until the state filter or the range changes. */
  const [touched, setTouched] = useState<ReadonlySet<string>>(new Set())
  /** The shown order: posting IDs, sorted when the pool loaded or the sort, the state filter or the
   * range changed (`orderKey`), so a posting rated or scored here keeps its place. */
  const [order, setOrder] = useState<string[]>([])
  const [orderKey, setOrderKey] = useState('')
  /** Counts the loads that arrived; part of `orderKey`. */
  const [loads, setLoads] = useState(0)
  /** The pass variant chosen in the menu; the shown one is `picked ?? next_pass.default`. Every
   * pool load drops it, and so does a change of `next_pass.default` (render-time sync below). */
  const [picked, setPicked] = useState<PassVariant | null>(null)
  const [focusRequest, setFocusRequest] = useState<{ id: string; target: 'row' | 'reasons' | 'note' } | null>(null)
  /** Polite message when Enter finds no further unrated posting; it alternates a trailing space
   * so the same text is announced again. */
  const [end, setEnd] = useState('')
  /** Polite announcement of a status change, whose row may leave the shown list. */
  const [announce, setAnnounce] = useState('')
  /** Counts the changes of the state filter or the range (`pick`, `pickRange`). */
  const epoch = useRef(0)
  /** Per posting, the epoch in which its last rating request and its last score request were sent,
   * kept apart because both can be in flight at once. An answer joins `touched` only if the epoch
   * has not moved on since: `pick` and `pickRange` clear `touched`, and a late answer must not
   * bring a row back into a list it no longer fits. */
  const sentRating = useRef(new Map<string, number>())
  const sentScore = useRef(new Map<string, number>())
  /** Add `id` to `touched` unless a filter or the range changed since its request in `sent` left. */
  const touch = (sent: Map<string, number>, id: string) => {
    const since = sent.get(id) ?? epoch.current
    sent.delete(id)
    if (since === epoch.current) setTouched((current) => new Set(current).add(id))
  }
  const rating = useRating((answer: RatingAnswer) => {
    const id = answer.row.posting_id
    setPool((current) => current && { ...current, counter: answer.counter, next_pass: answer.next_pass,
      rows: current.rows.map((row) => (row.posting_id === id ? answer.row : row)) })
    touch(sentRating.current, id)
  })
  /** Record the epoch of `id`'s rating request when `result` shows one was sent (a promise); an
   * action that sends nothing leaves the epoch of a request still in flight alone. */
  const sent = <T,>(id: string, result: T) => {
    if (result instanceof Promise) sentRating.current.set(id, epoch.current)
    return result
  }
  /** `rating` for the rows: every action that sends a rating records its epoch. */
  const tracked: Rating = {
    ...rating,
    level: (row, verdict, strength) => sent(row.posting_id, rating.level(row, verdict, strength)),
    chip: (row, chip) => sent(row.posting_id, rating.chip(row, chip)),
    saveNote: (row) => sent(row.posting_id, rating.saveNote(row)),
    retry: (row) => sent(row.posting_id, rating.retry(row)),
  }
  useEffect(() => {
    if (focusRequest) document.getElementById(`${focusRequest.target}-${focusRequest.id}`)?.focus()
  }, [focusRequest])

  /** Number of the newest load; an older answer arriving later is dropped. */
  const latest = useRef(0)
  const load = useCallback(() => {
    const mine = ++latest.current
    api<Pool>('/pool').then((next) => {
      if (mine !== latest.current) return
      setPool(next)
      setPicked(null)
      setLoads((count) => count + 1)
      setLoadFailed(false)
    }, () => {
      if (mine === latest.current) setLoadFailed(true)
    })
  }, [])
  useEffect(() => {
    if (active) load() // `reloadKey` changing (the header saved the settings) reloads the hint
  }, [active, load, reloadKey])
  /** A score from a row button replaces the row (the answer has no "Stichprobe" mark, so the row
   * keeps its own) and brings the counter and the next-pass figures along. */
  const score = useScore((scored: ScoreAnswer) => {
    const id = scored.row.posting_id
    setPool((current) => current && { ...current, counter: scored.counter, next_pass: scored.next_pass,
      rows: current.rows.map((row) => (row.posting_id === id ? { ...scored.row, exploration: row.exploration } : row)) })
    touch(sentScore.current, id)
  }, load)
  const { clearBusy } = score
  /** A finished pass reloads the pool and drops the rows' "scoring in progress" messages: they
   * were about that pass. */
  const passDone = useCallback(() => {
    load()
    clearBusy()
  }, [load, clearBusy])
  const { pass, busy, notice, start, answer, cancel, cancelling, cancelledScored, pollFailed, retryPoll } = usePass(passDone)
  const check = useCheck(load)

  async function setStatus(postingId: string, status: Status) {
    setSaving((current) => ({ ...current, [postingId]: true }))
    setFailed((current) => without(current, postingId))
    try {
      await api(`/postings/${encodeURIComponent(postingId)}`, { method: 'PATCH', json: { status } })
      setPool((current) => current && { ...current,
        rows: current.rows.map((row) => (row.posting_id === postingId ? { ...row, status } : row)) })
      const changed = pool?.rows.find((row) => row.posting_id === postingId)
      if (changed) {
        const leaves = !FILTERS.find((entry) => entry.id === filter)!.keep({ ...changed, status })
        setAnnounce(`${changed.title}: Bewerbungsstatus ${STATUSES.find(([id]) => id === status)![1]}.${leaves ? ' Die Anzeige ist nicht mehr in dieser Ansicht.' : ''}`)
      }
    } catch {
      setFailed((current) => ({ ...current, [postingId]: status }))
    } finally {
      setSaving((current) => without(current, postingId))
    }
  }

  const keep = FILTERS.find((entry) => entry.id === filter)!.keep
  const needle = text.trim().toLowerCase()
  // Take the order afresh when the pool loaded or the sort, the state filter or the range changed
  // (render-time sync, no effect); a rating or score in between changes a row but not its place.
  const key = `${loads}|${sort}|${filter}|${range.from}|${range.to}`
  if (pool && key !== orderKey) {
    setOrderKey(key)
    setOrder(sortRows(pool.rows, sort).map((row) => row.posting_id))
  }
  const byId = new Map(pool?.rows.map((row) => [row.posting_id, row]))
  const shown = order.flatMap((id) => byId.get(id) ?? []).filter((row) => {
    const mine = touched.has(row.posting_id)
    return (keep(row) || (mine && filter === 'unrated' && row.status === 'open'))
      && (mine || inRange(row, range)) && (!needle || `${row.title} ${row.company}`.toLowerCase().includes(needle))
  })
  const unrated = (row: PoolRow) => row.status === 'open' && rating.view(row).verdict === null
  const current = shown.some((row) => row.posting_id === selected) ? selected : nextUnrated(shown, undefined, unrated) ?? shown[0]?.posting_id

  /** Give the filter its rows afresh: nothing rated or scored here stays in it. */
  function pick(id: string) {
    epoch.current++
    setFilter(id)
    setTouched(new Set())
  }
  /** Set the range, ends kept in order; nothing rated or scored here stays outside it. */
  function pickRange(next: ScoreRange) {
    epoch.current++
    setRange(next)
    setTouched(new Set())
  }
  /** Send a level; the posting stays open and its reasons take focus, so reasons can follow. */
  function rate(row: PoolRow, verdict: Verdict, strength: Strength) {
    void tracked.level(row, verdict, strength)
    setSelected(row.posting_id)
    setFocusRequest({ id: row.posting_id, target: 'reasons' })
  }

  useEffect(() => {
    /** A paste that no text field takes goes to the note of the selected posting, which gets
     * focus, because focus sits on the reasons after a rating. */
    function onPaste(event: ClipboardEvent) {
      const row = shown.find((entry) => entry.posting_id === current)
      const text = strayPaste(event)
      if (!active || !row || !text) return
      event.preventDefault()
      const note = rating.view(row).note
      rating.setNote(row, note ? `${note}\n${text}` : text)
      setSelected(row.posting_id)
      setFocusRequest({ id: row.posting_id, target: 'note' })
    }
    window.addEventListener('paste', onPaste)
    return () => window.removeEventListener('paste', onPaste)
  })

  useEffect(() => {
    /** The pool's shortcuts (`design.md` "Rating without a run"): off while a text field, select,
     * editable element, menu (the pass variant menu), dialog (the header settings) or the check
     * column has focus, while a modifier other than Shift is held and while the view is hidden. A held key repeats only j and k, so it never rates or
     * toggles twice. */
    function onKey(event: KeyboardEvent) {
      const row = shown.find((entry) => entry.posting_id === current)
      if (!active || !pool || !row || event.altKey || event.ctrlKey || event.metaKey) return
      if (event.repeat && event.key !== 'j' && event.key !== 'k') return
      if ((event.target as HTMLElement).closest?.('input, textarea, select, [role="menu"], [role="dialog"], [data-no-shortcuts], [contenteditable]:not([contenteditable="false"])')) return
      const digit = /^Digit([1-9])$/.exec(event.code)?.[1]
      const level = LEVELS.find(({ key }) => key === event.key)
      const step = { j: 1, k: -1 }[event.key]
      const go = (id: string | undefined | null) => {
        if (!id) return
        setSelected(id)
        setFocusRequest({ id, target: 'row' })
      }
      if (event.shiftKey && digit) {
        const chip = pool.reason_chips[Number(digit) - 1]
        if (!chip) return
        void tracked.chip(row, chip.id)
        // Keep acting on this posting even after its derived verdict moves the default on.
        setSelected(row.posting_id)
      } else if (event.shiftKey) {
        return
      } else if (level) {
        rate(row, level.verdict, level.strength)
      } else if (event.key === 'Enter') {
        // On a button, link or summary Enter keeps its own meaning (toggle, open); J/K and
        // Enter put focus on the row itself, where Enter chains.
        if ((event.target as HTMLElement).closest?.('button, a, summary')) return
        const next = nextUnrated(shown, row.posting_id, unrated)
        if (next) go(next)
        else setEnd((text) => (text === END ? `${END} ` : END))
      } else if (step) {
        go(shown[shown.indexOf(row) + step]?.posting_id)
      } else if (event.key === 'n') {
        document.getElementById(`note-${row.posting_id}`)?.focus()
      } else {
        return
      }
      event.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })
  const counter = pool?.counter
  const working = busy && !pollFailed && pass?.status !== 'awaiting_answer'
  const stopping = cancelling || (pass?.cancel_requested ?? false)
  const storing = pass?.progress?.phase === 'storing'
  const defaultVariant = pool?.next_pass.default
  const [seenDefault, setSeenDefault] = useState(defaultVariant)
  if (seenDefault !== defaultVariant) {
    setSeenDefault(defaultVariant)
    setPicked(null)
  }
  const shownVariant = picked ?? defaultVariant ?? 'unscored'

  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-3xl leading-tight font-bold tracking-tight">Deine Anzeigen</h1>

      {pool && (
        // Two columns, each action with its status below it, so neither button moves when the
        // other action's status changes height; stacked on a phone.
        <div className="grid grid-cols-1 items-start gap-x-8 gap-y-4 sm:grid-cols-2">
          <div data-column="pass" className="flex min-w-0 flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <PassButton nextPass={pool.next_pass} shown={shownVariant} busy={busy} working={working} stopping={stopping}
                          storing={storing} onPick={setPicked} onStart={start} onCancel={cancel} />
              {counter && <CounterLine counter={counter} />}
            </div>
            {working && <PassProgressBlock progress={pass?.progress ?? null} stopping={stopping} />}
            {/* The live region holds only text that does not change per poll, so it is read once; the
                visible counts sit outside it. */}
            <div role="status" className="flex flex-col gap-3">
              {working && <span className="sr-only">Das Scoren läuft.</span>}
              {working && stopping && <span className="sr-only">Das Scoren wird nach der aktuellen Anzeige beendet.</span>}
              {pass?.status === 'aborted' && <p className="rounded-xl border bg-card px-4 py-3">Das Scoren wurde abgebrochen.</p>}
              {cancelledScored !== null && <p className="rounded-xl border bg-card px-4 py-3">{cancelledText(cancelledScored)}</p>}
            </div>
          </div>
          {/* The pool's key shortcuts stay off inside this column (`data-no-shortcuts`). */}
          <div data-column="check" data-no-shortcuts className="flex min-w-0 flex-col gap-3">
            <CheckButton total={pool.next_check.total} working={check.running && !check.pollFailed}
                         stopping={check.stopping} onStart={check.start} onCancel={check.cancel} />
            <CheckStatus check={check.check} running={check.running} stopping={check.stopping} lost={check.lost}
                         notice={check.notice} pollFailed={check.pollFailed} onStart={check.start}
                         onRetryPoll={check.retryPoll} onDismiss={check.dismiss} />
          </div>
        </div>
      )}

      <p role="status" className="sr-only">{announce}</p>
      <p role="status" className="sr-only">{end}</p>
      {notice && <p role="alert" className="rounded-xl border border-danger bg-danger-soft px-4 py-3">{notice}</p>}
      {busy && pollFailed && (
        <ErrorWithRetry title="Der Stand des Scorens ist gerade nicht abrufbar"
                        detail="Der Server antwortet nicht. Das Scoren läuft vielleicht weiter." onRetry={retryPoll} />
      )}
      {loadFailed && pool && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-danger bg-danger-soft px-4 py-3">
          Die Anzeigen konnten nicht neu geladen werden. Die Liste kann veraltet sein.
          <Button variant="outline" onClick={load}>Erneut versuchen</Button>
        </div>
      )}
      {pass?.status === 'failed' && (
        <ErrorWithRetry title="Das Scoren ist fehlgeschlagen"
                        detail={`${pass.error ?? 'Der Server hat keinen Grund genannt.'} Vielleicht enthält das Datenrepository eine kaputte Datei. Behebe sie und starte das Scoren noch einmal.`}
                        onRetry={() => start(shownVariant)} />
      )}
      {pass?.status === 'awaiting_answer' && <UnscreenedQuestion pass={pass} onAnswer={answer} />}

      {loadFailed && !pool ? (
        <ErrorWithRetry title="Anzeigen konnten nicht geladen werden"
                        detail="Der Server ist nicht erreichbar oder hat einen Fehler gemeldet." onRetry={load} />
      ) : !pool ? (
        <Loading label="Anzeigen werden geladen" />
      ) : pool.rows.length === 0 ? (
        <EmptyState title="Noch keine Anzeigen gespeichert" text="Füge zuerst ein paar Anzeigen hinzu.">
          <Button asChild><a href="#/hinzufuegen">Anzeige hinzufügen</a></Button>
        </EmptyState>
      ) : (
        <>
          <h2 className="sr-only">Anzeigen</h2>
          <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
            <div className="flex flex-col gap-1">
              <label htmlFor="pool-text" className="text-sm font-bold">Titel oder Firma</label>
              <Input id="pool-text" type="search" value={text} onChange={(event) => setText(event.target.value)} className="w-64 bg-card" />
            </div>
            <fieldset className="min-w-0">
              <legend className="mb-1 p-0 text-sm font-bold">Score</legend>
              <div className="flex items-end gap-2">
                <div className="flex flex-col gap-1">
                  <label htmlFor="pool-from" className="text-sm text-muted-foreground">von</label>
                  <select id="pool-from" value={range.from} className={SELECT}
                          onChange={(event) => { const from = Number(event.target.value); pickRange({ from, to: Math.max(from, range.to) }) }}>
                    <StepOptions />
                  </select>
                </div>
                <div className="flex flex-col gap-1">
                  <label htmlFor="pool-to" className="text-sm text-muted-foreground">bis</label>
                  <select id="pool-to" value={range.to} className={SELECT}
                          onChange={(event) => { const to = Number(event.target.value); pickRange({ from: Math.min(to, range.from), to }) }}>
                    <StepOptions />
                  </select>
                </div>
              </div>
            </fieldset>
            <div className="flex min-w-0 flex-col gap-1">
              <label htmlFor="pool-sort" className="text-sm font-bold">Sortierung</label>
              <select id="pool-sort" value={sort} onChange={(event) => setSort(event.target.value as Sort)} className={cn(SELECT, 'max-w-full')}>
                {SORTS.map(({ id, label }) => <option key={id} value={id}>{label}</option>)}
              </select>
            </div>
          </div>
          <div role="group" aria-label="Filter" className="flex flex-wrap gap-1.5">
            {FILTERS.map((entry) => (
              <button key={entry.id} type="button" aria-pressed={filter === entry.id} onClick={() => pick(entry.id)}
                      className={cn('min-h-11 rounded-lg border px-3.5 font-bold',
                        filter === entry.id ? 'border-primary bg-primary text-primary-foreground' : 'bg-card')}>
                {entry.label}
              </button>
            ))}
          </div>
          {shown.length === 0 ? (
            <div className="flex flex-wrap items-center gap-4 rounded-xl border bg-card p-5">
              <p>Keine Anzeige passt zu diesem Filter</p>
              <Button variant="outline" onClick={() => {
                pick('open')
                setText('')
                pickRange(FULL_RANGE)
              }}>Filter zurücksetzen</Button>
            </div>
          ) : (
            <>
              <Legend />
              <ul className="flex flex-col gap-3" aria-label="Anzeigen">
                {shown.map((row) => (
                  <Row key={row.posting_id} row={row} chips={pool.reason_chips} rating={tracked}
                       selected={row.posting_id === current} onSelect={() => setSelected(row.posting_id)}
                       onLevel={(verdict, strength) => rate(row, verdict, strength)} saving={!!saving[row.posting_id]}
                       failed={failed[row.posting_id]} onStatus={(status) => setStatus(row.posting_id, status)}
                       screening={pool.screening} scoreCall={score.call(row.posting_id)}
                       onScore={() => { sentScore.current.set(row.posting_id, epoch.current); void score.run(row.posting_id) }} />
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </div>
  )
}
