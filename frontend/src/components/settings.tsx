import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { Settings as Gear } from 'lucide-react'
import { api, type Pool, type PoolSettings } from '@/api'
import { Loading } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

/** The slot of the control in the app header's wrapping flex row: on a phone it sits beside the
 * wordmark and the backup button, from `sm` up at the right end, after the backup control. */
const SLOT = 'order-2 sm:order-5'

/** The hint thresholds as a form: the share is shown in percent and sent as 0 to 1. A failed
 * save keeps the input and offers a retry; `onSaved` runs after a stored save. */
function SettingsForm({ settings, onSaved }: { settings: PoolSettings; onSaved: () => void }) {
  const [threshold, setThreshold] = useState(String(settings.correction_threshold))
  const [percent, setPercent] = useState(String(Math.round(settings.correction_rate * 1000) / 10))
  const [problem, setProblem] = useState('')
  const [saving, setSaving] = useState(false)
  const [failed, setFailed] = useState(false)
  const [saved, setSaved] = useState(false)

  async function save(event?: FormEvent) {
    event?.preventDefault()
    setFailed(false)
    setSaved(false)
    const count = Number(threshold)
    const share = Number(percent)
    if (!threshold.trim() || !Number.isInteger(count) || count < 1) return setProblem('Gib bei den Korrekturen eine ganze Zahl ab 1 an.')
    if (!percent.trim() || !(share >= 0 && share <= 100)) return setProblem('Gib beim Anteil eine Zahl von 0 bis 100 an.')
    setProblem('')
    setSaving(true)
    try {
      await api('/pool/settings', { method: 'PUT', json: { correction_threshold: count, correction_rate: share / 100 } })
      setSaved(true)
      onSaved()
    } catch {
      setFailed(true)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={save} noValidate className="flex flex-wrap items-end gap-4">
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
      {saved && <p role="status" className="basis-full text-sm text-muted-foreground">Gespeichert.</p>}
    </form>
  )
}

/** The settings button of the app header and the panel it opens (threshold and rate of the pool's
 * hint). The stored values come from `GET /pool` each time the panel opens, since the API has no
 * route of its own for them. The panel hangs from the button and closes with a second press,
 * Escape (focus returns to the button) or a click outside. `onSaved` runs after a stored save, so
 * the pool view can reload its hint. */
export function SettingsControl({ onSaved }: { onSaved: () => void }) {
  const [open, setOpen] = useState(false)
  const [settings, setSettings] = useState<PoolSettings | null>(null)
  const [failed, setFailed] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  const panelId = useId()

  /** Read the stored settings; an older answer arriving after a close is dropped. */
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!open) return
    let stale = false
    api<Pool>('/pool').then((pool) => { if (!stale) setSettings(pool.settings) },
                            () => { if (!stale) setFailed(true) })
    return () => { stale = true }
  }, [open, attempt])

  useEffect(() => {
    if (!open) return
    const close = (event: Event) => {
      if (event instanceof KeyboardEvent) {
        if (event.key !== 'Escape') return
        setOpen(false)
        button.current?.focus()
      } else if (!root.current?.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('keydown', close)
    document.addEventListener('mousedown', close)
    return () => {
      document.removeEventListener('keydown', close)
      document.removeEventListener('mousedown', close)
    }
  }, [open])

  function toggle() {
    if (!open) {
      setSettings(null)
      setFailed(false)
    }
    setOpen(!open)
  }

  return (
    // data-no-shortcuts: the pool's key shortcuts stay off while the gear has focus.
    <div ref={root} data-no-shortcuts className={`relative ${SLOT}`}>
      <Button ref={button} type="button" variant="ghost" aria-label="Einstellungen" aria-expanded={open}
              aria-controls={open ? panelId : undefined} onClick={toggle}
              className="size-11 border border-transparent p-0 text-muted-foreground hover:bg-muted hover:text-foreground">
        <Gear className="size-5" aria-hidden="true" />
      </Button>
      {open && (
        <div id={panelId} role="dialog" aria-label="Einstellungen"
             className="absolute top-full right-0 z-20 mt-2 flex w-[min(400px,calc(100vw-32px))] flex-col gap-3 rounded-xl border bg-card p-4 shadow-card">
          <div>
            <p className="font-bold">Hinweis „neu scoren sinnvoll“</p>
            <p className="text-sm text-muted-foreground">Ab wann der Hinweis unter dem Scoren-Button erscheint.</p>
          </div>
          {failed ? (
            <p role="alert" className="flex flex-wrap items-center gap-3 text-danger">
              Die Einstellungen konnten nicht geladen werden.
              <Button type="button" variant="outline" onClick={() => { setFailed(false); setAttempt(attempt + 1) }}>
                Erneut versuchen
              </Button>
            </p>
          ) : settings === null ? (
            <Loading label="Einstellungen werden geladen" />
          ) : (
            <SettingsForm settings={settings} onSaved={onSaved} />
          )}
        </div>
      )}
    </div>
  )
}
