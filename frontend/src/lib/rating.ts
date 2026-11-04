import { useRef, useState } from 'react'
import { ThumbsDown, ThumbsUp } from 'lucide-react'
import { ApiError, putRating, type PoolRow, type RatingAnswer, type RatingBody, type Strength, type Verdict } from '@/api'
import { without } from '@/lib/utils'

/** The four rating levels, top to bottom as listed and as the keys `1` to `4` give them. */
export const LEVELS = [
  { key: '1', label: 'Ja, auf jeden Fall', verdict: 'positive', strength: 'strong', Icon: ThumbsUp },
  { key: '2', label: 'Ja, vielleicht', verdict: 'positive', strength: 'weak', Icon: ThumbsUp },
  { key: '3', label: 'Nein, eher nicht', verdict: 'negative', strength: 'weak', Icon: ThumbsDown },
  { key: '4', label: 'Nein, auf keinen Fall', verdict: 'negative', strength: 'strong', Icon: ThumbsDown },
] as const

/** The plain text of a paste that no text field takes (its target is no input, textarea, select
 * or editable element), else `null`. After a rating focus sits on the reasons, so a paste there
 * would land nowhere; the views route it into the note instead. */
export function strayPaste(event: ClipboardEvent): string | null {
  const target = event.target as HTMLElement | null
  if (target?.closest?.('input, textarea, select, [contenteditable]:not([contenteditable="false"])')) return null
  return event.clipboardData?.getData('text/plain') || null
}

/** A rating request in flight or failed: the body that was sent, and why it failed (`verdict`: no
 * verdict could be derived from the chips, `chip`: a chip is unknown to the policy pack,
 * `other`: anything else). */
type Saving = { body: RatingBody; failed?: 'verdict' | 'chip' | 'other' }

/** The rating state of several postings. `onAnswer` receives each stored answer (the new row and
 * figures). Every action stores the posting's whole rating at once; the verdict is sent only
 * when one is set, so a chip never changes it and, with none set, takes the one the server
 * derives. The strength travels with the verdict through every action and only `level` changes
 * it. The input (chips, note) stays on screen while saving and after a failure, and `retry`
 * sends the failed body again. */
export function useRating(onAnswer: (answer: RatingAnswer) => void) {
  const [saving, setSaving] = useState<Record<string, Saving>>({})
  const [notes, setNotes] = useState<Record<string, string>>({})
  /** Number of the newest request per posting; an older answer arriving later is dropped. */
  const latest = useRef<Record<string, number>>({})
  /** Settlement (never rejecting) of the last request per posting; the next one waits for it. */
  const tails = useRef<Record<string, Promise<undefined>>>({})

  /** What `row` shows now: the rating being saved wins over the stored one. */
  function view(row: PoolRow) {
    const pending = saving[row.posting_id]
    return {
      verdict: pending?.body.verdict ?? row.label?.verdict ?? null,
      // the body in flight holds the whole rating, so its missing strength is none, not the stored one
      strength: (pending ? pending.body.strength : row.label?.strength) ?? null,
      chips: pending?.body.chips ?? row.label?.chips ?? [],
      note: notes[row.posting_id] ?? row.label?.note ?? '',
      saving: pending !== undefined && !pending.failed,
      failed: pending?.failed,
    }
  }

  async function submit(id: string, body: RatingBody) {
    const mine = (latest.current[id] = (latest.current[id] ?? 0) + 1)
    setSaving((current) => ({ ...current, [id]: { body } }))
    // One PUT at a time per posting, in the order sent, so the server stores the newest last.
    const request = (tails.current[id] ?? Promise.resolve()).then(() => putRating(id, body))
    tails.current[id] = request.then(() => undefined, () => undefined)
    try {
      const answer = await request
      if (mine !== latest.current[id]) return
      setSaving((current) => without(current, id))
      // The stored note is the truth again, unless more was typed meanwhile.
      setNotes((current) => ((current[id] ?? '').trim() === (body.note ?? '') ? without(current, id) : current))
      onAnswer(answer)
    } catch (error) {
      if (mine !== latest.current[id]) return
      const failed = !(error instanceof ApiError && error.status === 422) ? 'other'
        : error.detail.startsWith('unknown reason chip') ? 'chip' : 'verdict'
      setSaving((current) => ({ ...current, [id]: { body, failed } }))
    }
  }

  /** Store `row` with `change` on top of what it shows; a strength goes only with a verdict. */
  function send(row: PoolRow, change: { verdict?: Verdict; strength?: Strength | null; chips?: string[] }) {
    const now = view(row)
    const verdict = change.verdict ?? now.verdict ?? undefined
    const strength = change.strength === undefined ? now.strength : change.strength
    return submit(row.posting_id, {
      ...(verdict && { verdict }), ...(verdict && strength && { strength }),
      chips: change.chips ?? now.chips, note: now.note.trim() || null,
    })
  }

  return {
    view,
    /** Rate at one of the four levels; the level already shown sends nothing. */
    level: (row: PoolRow, verdict: Verdict, strength: Strength) => {
      const now = view(row)
      if (now.verdict === verdict && now.strength === strength) return
      return send(row, { verdict, strength })
    },
    chip: (row: PoolRow, chip: string) => {
      const now = view(row)
      const chips = now.chips.includes(chip) ? now.chips.filter((entry) => entry !== chip) : [...now.chips, chip]
      // Nothing stored, nothing left to store: reset the local state instead of asking the
      // server to store a label without verdict (it answers 422).
      if (!now.verdict && chips.length === 0 && !row.label && !now.saving) {
        return setSaving((current) => without(current, row.posting_id))
      }
      return send(row, { chips })
    },
    setNote: (row: PoolRow, note: string) => setNotes((current) => ({ ...current, [row.posting_id]: note })),
    /** Store a changed note; with neither verdict nor chip there is nothing to store it with yet. */
    saveNote: (row: PoolRow) => {
      const now = view(row)
      if (now.note.trim() === (row.label?.note ?? '') || (!now.verdict && now.chips.length === 0)) return
      return send(row, {})
    },
    retry: (row: PoolRow) => {
      const pending = saving[row.posting_id]
      if (pending) return submit(row.posting_id, pending.body)
    },
  }
}

/** The rating state of a hook (`useRating`). */
export type Rating = ReturnType<typeof useRating>
