import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, type Posting, type PostingPageData, type ScoreAnswer, type Status } from '@/api'
import { Badge, OriginalLink, PostingFields, ScoreButton, ScoreProblem, ScoreText, StatusControl } from '@/components/posting'
import { Button } from '@/components/ui/button'
import { ReasonsAndNote, VerdictButtons } from '@/components/rating'
import { addedLabel } from '@/lib/german'
import { strayPaste, useRating } from '@/lib/rating'
import { useScore } from '@/lib/score'
import { cn } from '@/lib/utils'
import { ErrorWithRetry, Loading } from '@/components/states'

const BackLink = () => <a href="#/pool" className="self-start text-primary underline underline-offset-2">Zurück zur Liste</a>

/** The page of one posting (`#/anzeigen/<id>`; `postingId` is the decoded ID) from
 * `GET /postings/{id}`: when it was added (above the title), title, company and location, original link, score with reasoning and the
 * compared examples (links to their pages), "Bearbeiten" for correcting title, company and
 * location (`PostingFields`), the rating (verdict, reason chips and note, stored
 * at once by `PUT .../rating` with saving and retry), the application status
 * (`PATCH`, with saving and retry), the import origin and the full text. Shows loading, a 404
 * message or a retryable error, and starts afresh when `postingId` changes. */
export function PostingPage({ postingId }: { postingId: string }) {
  return <LoadedPage key={postingId} postingId={postingId} />
}

/** The page state for one posting; remounted per ID so nothing of the previous posting stays. */
function LoadedPage({ postingId }: { postingId: string }) {
  const [data, setData] = useState<PostingPageData | null>(null)
  const [error, setError] = useState<'missing' | 'failed' | null>(null)
  const [saving, setSaving] = useState(false)
  const [failed, setFailed] = useState<Status | undefined>()
  const [editing, setEditing] = useState(false)
  const editToggle = useRef<HTMLButtonElement>(null)
  const rating = useRating((answer) => setData((current) => current && { ...current, row: answer.row }))

  /** Number of the newest load; an older answer arriving later is dropped. */
  const latest = useRef(0)
  const load = useCallback(() => {
    const mine = ++latest.current
    api<PostingPageData>(`/postings/${encodeURIComponent(postingId)}`).then((next) => {
      if (mine === latest.current) setData(next)
    }, (problem) => {
      if (mine === latest.current) setError(problem instanceof ApiError && problem.status === 404 ? 'missing' : 'failed')
    })
  }, [postingId])
  useEffect(load, [load])

  /** A score from the button replaces the page's data (the counter and next-pass figures are the pool's). */
  const score = useScore(({ row, posting, score, examples, reason_chips, screening }: ScoreAnswer) =>
    setData({ row, posting, score, examples, reason_chips, screening }), load)

  const title = data?.posting.title
  useEffect(() => {
    if (title) document.title = `${title} – JobAdvAIsor`
  }, [title])

  const loaded = data?.row
  useEffect(() => {
    /** A paste that no text field takes goes to the note, which gets focus, because focus sits on
     * the reasons after a rating. */
    function onPaste(event: ClipboardEvent) {
      const text = strayPaste(event)
      if (!loaded || !text) return
      event.preventDefault()
      const note = rating.view(loaded).note
      rating.setNote(loaded, note ? `${note}\n${text}` : text)
      document.getElementById(`note-${loaded.posting_id}`)?.focus()
    }
    window.addEventListener('paste', onPaste)
    return () => window.removeEventListener('paste', onPaste)
  })

  async function setStatus(status: Status) {
    setSaving(true)
    setFailed(undefined)
    try {
      await api(`/postings/${encodeURIComponent(postingId)}`, { method: 'PATCH', json: { status } })
      setData((current) => current && { ...current, row: { ...current.row, status } })
    } catch {
      setFailed(status)
    } finally {
      setSaving(false)
    }
  }

  function closeEditor() {
    setEditing(false)
    editToggle.current?.focus()
  }

  /** A saved correction: the stored posting replaces the page's, the row follows for the status control. */
  function corrected(stored: Posting) {
    const { title, company, location_raw } = stored
    setData((current) => current && { ...current, posting: stored, row: { ...current.row, title, company, location_raw } })
    closeEditor()
  }

  if (error === 'missing') {
    return (
      <div className="flex flex-col gap-4">
        <BackLink />
        <p className="text-xl font-bold">Diese Anzeige gibt es nicht (mehr).</p>
      </div>
    )
  }
  if (error) {
    return <ErrorWithRetry title="Die Anzeige konnte nicht geladen werden"
                           detail="Der Server ist nicht erreichbar oder hat einen Fehler gemeldet."
                           onRetry={() => {
                             setError(null)
                             load()
                           }} />
  }
  if (!data) return <Loading label="Anzeige wird geladen" />

  const { row, posting, examples } = data
  const call = score.call(postingId)
  return (
    <div className="flex flex-col gap-5">
      <BackLink />
      <div className="flex flex-col items-start gap-3">
        <div>
          <p className="text-[11px] leading-4 text-subtle-foreground">
            <time dateTime={new Date(row.added_at).toISOString()}>{addedLabel(row.added_at)}</time>
          </p>
          <h1 className="text-3xl leading-tight font-bold tracking-tight">{posting.title}</h1>
          <p className="text-muted-foreground">{posting.company}, {posting.location_raw}</p>
        </div>
        <Button ref={editToggle} type="button" variant="outline" size="sm" aria-expanded={editing}
                onClick={() => setEditing(!editing)}>
          Bearbeiten
        </Button>
        {editing && (
          <PostingFields postingId={postingId} posting={posting} onSaved={corrected}>
            <Button type="button" variant="outline" onClick={closeEditor}>Abbrechen</Button>
          </PostingFields>
        )}
      </div>
      <OriginalLink url={posting.urls[0]} />

      <section aria-labelledby="score-title" aria-busy={call.computing || undefined}
               className="flex max-w-[80ch] flex-col gap-3 rounded-xl border bg-card p-5">
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
          <h2 id="score-title" className="text-lg font-bold">Score</h2>
          <ScoreButton row={row} screening={data.screening} call={call} onScore={() => void score.run(postingId)} />
        </div>
        <ScoreProblem call={call} />
        {row.state === 'unscored' && !row.score_problem
          ? <p>Noch kein Score – starte in der Liste „Neue Anzeigen bewerten“.</p>
          : (
            <p className={cn(call.computing && 'text-muted-foreground')}>
              <ScoreText row={row} />{call.computing && row.state === 'scored' && ' · wird neu berechnet …'}
            </p>
          )}
        {row.state === 'scored' && data.score && (
          <>
            <p className={cn(call.computing && 'text-muted-foreground')}>{data.score.reasoning}</p>
            {examples.length > 0 && (
              <div>
                <p className="font-bold">Verglichen mit:</p>
                <ul className="ml-5 list-disc">
                  {examples.map((example) => (
                    <li key={example.posting_id}>
                      <a href={`#/anzeigen/${encodeURIComponent(example.posting_id)}`} className="text-primary underline underline-offset-2">
                        {example.title}, {example.company}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </section>

      <section aria-labelledby="rating-title" className="flex max-w-[80ch] flex-col items-start gap-2 rounded-xl border bg-card p-5">
        <h2 id="rating-title" className="text-lg font-bold">Deine Bewertung</h2>
        {!rating.view(row).verdict && <p>Noch keine Bewertung</p>}
        <VerdictButtons row={row} rating={rating} onLevel={(verdict, strength) => {
          void rating.level(row, verdict, strength)
          document.getElementById(`reasons-${row.posting_id}`)?.focus()
        }} />
        <ReasonsAndNote row={row} chips={data.reason_chips} rating={rating} highlight={!!rating.view(row).verdict} />
      </section>

      <div className="flex flex-wrap items-start gap-x-8 gap-y-3">
        <StatusControl id="posting-status" title={posting.title} value={row.status} saving={saving}
                       failed={failed} onStatus={setStatus} />
        {row.origin && (
          <Badge className="bg-muted text-foreground">
            Importiert aus {row.origin.table}{row.origin.fit && `, Einschätzung: ${row.origin.fit}`}{row.origin.status && `, Status: ${row.origin.status}`}
          </Badge>
        )}
      </div>

      <section aria-labelledby="text-title">
        <h2 id="text-title" className="mb-2 text-lg font-bold">Anzeigentext</h2>
        <p className="max-w-[80ch] whitespace-pre-line">{posting.text}</p>
      </section>
    </div>
  )
}
