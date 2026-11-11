import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Compass, LoaderCircle, ShieldAlert } from 'lucide-react'
import { api, ApiError, type PassState, type Pool, type PoolRow, type PoolSettings, type RatingAnswer, type ScoreAnswer, type Status, type Strength, type Verdict } from '@/api'
import { Badge, ChipList, ScoreButton, ScoreProblem, ScoreText, StatusControl } from '@/components/posting'
import { Legend, ReasonsAndNote, VerdictButtons } from '@/components/rating'
import { EmptyState, ErrorWithRetry, Loading } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { STATUSES } from '@/lib/german'
import { LEVELS, strayPaste, useRating, type Rating } from '@/lib/rating'
import { useScore, type ScoreCall } from '@/lib/score'
import { cn, without } from '@/lib/utils'

/** How often a computing scoring pass is polled, in milliseconds. */
export const POLL_MS = 1000
/** Failed polls in a row after which polling stops and a retry is offered. */
export const POLL_FAILURES = 3
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

/** The filters; each keeps the rows it shows, in the server's order. "Herkunft" keeps every
 * imported row whatever its status. */
const FILTERS: { id: string; label: string; keep: (row: PoolRow) => boolean }[] = [
  { id: 'open', label: 'Offen', keep: (row) => row.status === 'open' },
  { id: 'unrated', label: 'Noch nicht bewertet', keep: (row) => row.status === 'open' && verdictOf(row) === null },
  { id: 'rated', label: 'Bewertet', keep: (row) => row.status === 'open' && verdictOf(row) !== null },
  { id: 'applied', label: 'Beworben', keep: (row) => row.status === 'applied' },
  { id: 'done', label: 'Erledigt', keep: (row) => row.status === 'done' },
  { id: 'imported', label: 'Herkunft', keep: (row) => row.origin !== null },
]

/** The scoring pass: starts it, polls it while it runs, remembers its ID across a reload.
 * `onDone` runs when a pass finishes. `busy` is true while one runs or waits for an answer. */
function usePass(onDone: () => void) {
  const [passId, setPassId] = useState<string | null>(storedPass.get)
  const [pass, setPass] = useState<PassState | null>(null)
  const [notice, setNotice] = useState('')
  const [pollFailed, setPollFailed] = useState(false)
  const sending = useRef(false)
  const running = passId !== null && (pass === null || pass.status === 'running')
  const busy = running || pass?.status === 'awaiting_answer'

  useEffect(() => {
    if (!passId || !running || pollFailed) return
    let failures = 0
    const timer = setInterval(() => {
      api<PassState>(`/pool/passes/${passId}`).then((next) => {
        failures = 0
        if (next.status === 'done') {
          storedPass.set(null)
          setPassId(null)
          setPass(null)
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
  const start = () => send(async () => {
    const answer = await api<{ pass_id: string }>('/pool/passes', { method: 'POST' })
    storedPass.set(answer.pass_id)
    setPass(null)
    setPollFailed(false)
    setPassId(answer.pass_id)
  }, 'Es läuft schon eine andere Bewertung. Warte, bis sie fertig ist.',
  'Die Bewertung konnte nicht gestartet werden. Ist der Server erreichbar?')
  const answer = (proceed: boolean) => send(async () => {
    await api(`/pool/passes/${passId}/unscreened`, { method: 'POST', json: { continue: proceed } })
    setPass((current) => current && { ...current, status: 'running' })
  }, 'Gerade rechnet eine andere Bewertung. Antworte, wenn sie fertig ist.',
  'Die Antwort wurde nicht gespeichert. Versuch es noch einmal.')
  return { pass, busy, notice, start, answer, pollFailed, retryPoll: () => setPollFailed(false) }
}

/** The question over postings the content guard never checked: names them, then go on or abort. */
function UnscreenedQuestion({ pass, onAnswer }: { pass: PassState; onAnswer: (proceed: boolean) => void }) {
  const count = pass.unscreened.length
  return (
    <section aria-labelledby="unscreened-title"
             className="flex max-w-[760px] flex-col gap-4 rounded-xl border bg-card p-6 shadow-card">
      <div className="flex items-start gap-3">
        <ShieldAlert className="mt-0.5 size-6 flex-none text-negative" aria-hidden="true" />
        <div>
          <h2 id="unscreened-title" className="text-xl font-bold">Die Bewertung wartet auf deine Antwort</h2>
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
        Bewerte sie trotzdem, dann laufen sie mit den anderen durch. Oder brich ab: Dann wird nichts
        bewertet, und du kannst die Inhaltsprüfung einschalten und neu starten.
      </p>
      <div className="ml-9 flex flex-wrap gap-2">
        <Button onClick={() => onAnswer(true)}>Trotzdem bewerten</Button>
        <Button variant="outline" onClick={() => onAnswer(false)}>Abbrechen</Button>
      </div>
    </section>
  )
}

/** The hint thresholds as a form: the share is shown in percent and sent as 0 to 1. A failed
 * save keeps the input and offers a retry; `onSaved` reloads the pool so the hint follows. */
function Settings({ settings, onSaved }: { settings: PoolSettings; onSaved: () => void }) {
  const [threshold, setThreshold] = useState(String(settings.correction_threshold))
  const [percent, setPercent] = useState(String(Math.round(settings.correction_rate * 1000) / 10))
  const [problem, setProblem] = useState('')
  const [saving, setSaving] = useState(false)
  const [failed, setFailed] = useState(false)
  // Follow the stored settings after a reload (render-time sync, no effect).
  const [shownSettings, setShownSettings] = useState(settings)
  if (shownSettings.correction_threshold !== settings.correction_threshold
      || shownSettings.correction_rate !== settings.correction_rate) {
    setShownSettings(settings)
    setThreshold(String(settings.correction_threshold))
    setPercent(String(Math.round(settings.correction_rate * 1000) / 10))
  }

  async function save(event?: FormEvent) {
    event?.preventDefault()
    setFailed(false)
    const count = Number(threshold)
    const share = Number(percent)
    if (!threshold.trim() || !Number.isInteger(count) || count < 1) return setProblem('Gib bei den Korrekturen eine ganze Zahl ab 1 an.')
    if (!percent.trim() || !(share >= 0 && share <= 100)) return setProblem('Gib beim Anteil eine Zahl von 0 bis 100 an.')
    setProblem('')
    setSaving(true)
    try {
      await api('/pool/settings', { method: 'PUT', json: { correction_threshold: count, correction_rate: share / 100 } })
      onSaved()
    } catch {
      setFailed(true)
    } finally {
      setSaving(false)
    }
  }

  return (
    <details className="rounded-xl border bg-card px-4 py-3">
      <summary className="cursor-pointer font-bold">Einstellungen</summary>
      <form onSubmit={save} noValidate className="mt-3 flex flex-wrap items-end gap-4">
        <div className="flex flex-col gap-1">
          <label htmlFor="threshold" className="text-sm font-bold">Korrekturen bis zum Hinweis</label>
          <Input id="threshold" type="number" min={1} value={threshold} className="w-28 tabular-nums"
                 onChange={(event) => setThreshold(event.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="percent" className="text-sm font-bold">Anteil bis zum Hinweis (in %)</label>
          <Input id="percent" type="number" min={0} max={100} value={percent} className="w-28 tabular-nums"
                 onChange={(event) => setPercent(event.target.value)} />
        </div>
        <Button type="submit" variant="outline" disabled={saving}>{saving ? 'Wird gespeichert…' : 'Speichern'}</Button>
        {problem && <p role="alert" className="basis-full text-danger">{problem}</p>}
        {failed && (
          <p role="alert" className="flex basis-full flex-wrap items-center gap-3 text-danger">
            Die Einstellungen wurden nicht gespeichert.
            <Button type="button" variant="outline" onClick={() => save()}>Erneut versuchen</Button>
          </p>
        )}
      </form>
    </details>
  )
}

/** One pool row: title link, company and location, score with its button, the "Stichprobe" and
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
        <h3 className="text-lg leading-snug font-bold">
          <a id={`title-${row.posting_id}`} href={`#/anzeigen/${encodeURIComponent(row.posting_id)}`} className="text-foreground">{row.title}</a>
        </h3>
        <p className="text-[15px] text-muted-foreground">{row.company}, {row.location_raw}</p>
        {(row.exploration || row.origin) && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
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

const END = 'Keine weitere unbewertete Anzeige.'

/** The ID of the next row after `from` (the first when `from` is unknown) that `unrated` accepts,
 * wrapping around and never `from` itself; `null` if there is none. */
const nextUnrated = (rows: PoolRow[], from: string | undefined, unrated: (row: PoolRow) => boolean) => {
  const start = rows.findIndex((row) => row.posting_id === from) + 1
  return [...rows.slice(start), ...rows.slice(0, Math.max(start - 1, 0))].find(unrated)?.posting_id ?? null
}

/** The pool view (`#/pool`): ranked postings from `GET /pool` with state and text filters, the
 * application status per row, the scoring pass with its progress, the correction counter with
 * its hint, and the hint settings. Reloads whenever it becomes `active`. */
export function PoolView({ active = true }: { active?: boolean }) {
  const [pool, setPool] = useState<Pool | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)
  const [filter, setFilter] = useState('open')
  const [text, setText] = useState('')
  const [saving, setSaving] = useState<Record<string, boolean>>({})
  const [failed, setFailed] = useState<Record<string, Status>>({})
  /** The posting the shortcut keys act on; `null` until one is chosen (then the first unrated). */
  const [selected, setSelected] = useState<string | null>(null)
  /** Postings rated here: they stay in the "Noch nicht bewertet" list until the filter changes. */
  const [touched, setTouched] = useState<ReadonlySet<string>>(new Set())
  const [focusRequest, setFocusRequest] = useState<{ id: string; target: 'row' | 'reasons' | 'note' } | null>(null)
  /** Polite message when Enter finds no further unrated posting; it alternates a trailing space
   * so the same text is announced again. */
  const [end, setEnd] = useState('')
  /** Polite announcement of a status change, whose row may leave the shown list. */
  const [announce, setAnnounce] = useState('')
  const rating = useRating((answer: RatingAnswer) => {
    const id = answer.row.posting_id
    setPool((current) => current && { ...current, counter: answer.counter, next_pass: answer.next_pass,
      rows: current.rows.map((row) => (row.posting_id === id ? answer.row : row)) })
    setTouched((current) => new Set(current).add(id))
  })
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
      setLoadFailed(false)
    }, () => {
      if (mine === latest.current) setLoadFailed(true)
    })
  }, [])
  useEffect(() => {
    if (active) load()
  }, [active, load])
  /** A score from a row button replaces the row (the answer has no "Stichprobe" mark, so the row
   * keeps its own) and brings the counter and the next-pass figures along. */
  const score = useScore((scored: ScoreAnswer) => {
    const id = scored.row.posting_id
    setPool((current) => current && { ...current, counter: scored.counter, next_pass: scored.next_pass,
      rows: current.rows.map((row) => (row.posting_id === id ? { ...scored.row, exploration: row.exploration } : row)) })
  }, load)
  const { clearBusy } = score
  /** A finished pass reloads the pool and drops the rows' "scoring in progress" messages: they
   * were about that pass. */
  const passDone = useCallback(() => {
    load()
    clearBusy()
  }, [load, clearBusy])
  const { pass, busy, notice, start, answer, pollFailed, retryPoll } = usePass(passDone)

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
        setAnnounce(`${changed.title}: Status ${STATUSES.find(([id]) => id === status)![1]}.${leaves ? ' Die Anzeige ist nicht mehr in dieser Ansicht.' : ''}`)
      }
    } catch {
      setFailed((current) => ({ ...current, [postingId]: status }))
    } finally {
      setSaving((current) => without(current, postingId))
    }
  }

  const keep = FILTERS.find((entry) => entry.id === filter)!.keep
  const needle = text.trim().toLowerCase()
  const shown = pool?.rows.filter((row) => (keep(row) || (filter === 'unrated' && row.status === 'open' && touched.has(row.posting_id)))
    && (!needle || `${row.title} ${row.company}`.toLowerCase().includes(needle))) ?? []
  const unrated = (row: PoolRow) => row.status === 'open' && rating.view(row).verdict === null
  const current = shown.some((row) => row.posting_id === selected) ? selected : nextUnrated(shown, undefined, unrated) ?? shown[0]?.posting_id

  /** Give the filter its rows afresh: nothing rated here stays in it. */
  function pick(id: string) {
    setFilter(id)
    setTouched(new Set())
  }
  /** Send a level; the posting stays open and its reasons take focus, so reasons can follow. */
  function rate(row: PoolRow, verdict: Verdict, strength: Strength) {
    void rating.level(row, verdict, strength)
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
    /** The pool's shortcuts (`design.md` "Rating without a run"): off while a text field, select
     * or editable element has focus, while a modifier other than Shift is held and while the view
     * is hidden. A held key repeats only j and k, so it never rates or toggles twice. */
    function onKey(event: KeyboardEvent) {
      const row = shown.find((entry) => entry.posting_id === current)
      if (!active || !pool || !row || event.altKey || event.ctrlKey || event.metaKey) return
      if (event.repeat && event.key !== 'j' && event.key !== 'k') return
      if ((event.target as HTMLElement).closest?.('input, textarea, select, [contenteditable]:not([contenteditable="false"])')) return
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
        void rating.chip(row, chip.id)
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
  const count = pool?.next_pass.count ?? 0
  const counter = pool?.counter
  const nothingToDo = counter?.hint === 'rescore'
    ? ' Es gibt nichts zu bewerten: Alle Anzeigen sind ausgeschlossen oder zurückgehalten.' : ''
  const working = busy && !pollFailed && pass?.status !== 'awaiting_answer'
  const why = busy ? 'Eine Bewertung läuft.'
    : count === 0 ? `Es gibt keine neuen Anzeigen zu bewerten.${nothingToDo}` : ''

  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-3xl leading-tight font-bold tracking-tight">Deine Anzeigen</h1>

      {pool && (
        <div className="flex flex-wrap items-start gap-x-8 gap-y-4">
          <div className="flex flex-col gap-1.5">
            <Button onClick={start} disabled={busy || count === 0} aria-describedby={why ? 'pass-why' : undefined}>
              Neue Anzeigen bewerten ({count})
            </Button>
            {why && <p id="pass-why" className="text-sm text-muted-foreground">{why}</p>}
          </div>
          {counter && (
            <div className="flex flex-col gap-1">
              <p>Korrekturen seit der letzten Bewertung der Anzeigen: <strong>{counter.corrections}</strong></p>
              <p>{counter.rate === null ? 'Anteil ab 10 Bewertungen' : `Anteil: ${Math.round(counter.rate * 100)} %`}</p>
              <Badge className={counter.hint === 'rescore' ? 'self-start bg-negative-soft text-negative' : 'self-start bg-positive-soft text-primary'}>
                {counter.hint === 'rescore' ? 'neue Bewertung sinnvoll' : 'Ranking passt gut'}
              </Badge>
            </div>
          )}
          <div className="min-w-[280px] flex-[1_1_320px]"><Settings settings={pool.settings} onSaved={load} /></div>
        </div>
      )}

      {/* The live region holds only text that does not change per poll, so it is read once; the
          visible counts sit outside it. */}
      <div role="status">
        {working && <span className="sr-only">Die Bewertung läuft.</span>}
        {pass?.status === 'aborted' && <p className="rounded-xl border bg-card px-4 py-3">Die Bewertung wurde abgebrochen.</p>}
      </div>
      <p role="status" className="sr-only">{announce}</p>
      <p role="status" className="sr-only">{end}</p>
      {working && (
        <p className="flex items-center gap-3 rounded-xl bg-positive-soft px-4 py-3">
          <LoaderCircle className="size-5 flex-none motion-safe:animate-spin" aria-hidden="true" />
          <strong>{pass ? `Bewertung läuft: ${pass.done} von ${pass.total}` : 'Bewertung läuft'}</strong>
        </p>
      )}
      {notice && <p role="alert" className="rounded-xl border border-danger bg-danger-soft px-4 py-3">{notice}</p>}
      {busy && pollFailed && (
        <ErrorWithRetry title="Der Stand der Bewertung ist gerade nicht abrufbar"
                        detail="Der Server antwortet nicht. Die Bewertung rechnet vielleicht weiter." onRetry={retryPoll} />
      )}
      {loadFailed && pool && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-danger bg-danger-soft px-4 py-3">
          Die Anzeigen konnten nicht neu geladen werden. Die Liste kann veraltet sein.
          <Button variant="outline" onClick={load}>Erneut versuchen</Button>
        </div>
      )}
      {pass?.status === 'failed' && (
        <ErrorWithRetry title="Die Bewertung ist fehlgeschlagen"
                        detail={`${pass.error ?? 'Der Server hat keinen Grund genannt.'} Vielleicht enthält das Datenrepository eine kaputte Datei. Behebe sie und starte die Bewertung noch einmal.`}
                        onRetry={start} />
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
            <div role="group" aria-label="Filter" className="flex flex-wrap gap-1.5">
              {FILTERS.map((entry) => (
                <button key={entry.id} type="button" aria-pressed={filter === entry.id} onClick={() => pick(entry.id)}
                        className={cn('min-h-11 rounded-lg border px-3.5 font-bold',
                          filter === entry.id ? 'border-primary bg-primary text-primary-foreground' : 'bg-card')}>
                  {entry.label}
                </button>
              ))}
            </div>
          </div>
          {shown.length === 0 ? (
            <div className="flex flex-wrap items-center gap-4 rounded-xl border bg-card p-5">
              <p>Keine Anzeige passt zu diesem Filter</p>
              <Button variant="outline" onClick={() => {
                pick('open')
                setText('')
              }}>Filter zurücksetzen</Button>
            </div>
          ) : (
            <>
              <Legend />
              <ul className="flex flex-col gap-3" aria-label="Anzeigen">
                {shown.map((row) => (
                  <Row key={row.posting_id} row={row} chips={pool.reason_chips} rating={rating}
                       selected={row.posting_id === current} onSelect={() => setSelected(row.posting_id)}
                       onLevel={(verdict, strength) => rate(row, verdict, strength)} saving={!!saving[row.posting_id]}
                       failed={failed[row.posting_id]} onStatus={(status) => setStatus(row.posting_id, status)}
                       screening={pool.screening} scoreCall={score.call(row.posting_id)}
                       onScore={() => void score.run(row.posting_id)} />
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </div>
  )
}
