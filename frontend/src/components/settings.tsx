import { useEffect, useState, type FormEvent } from 'react'
import { Settings as Gear } from 'lucide-react'
import { api, type Pool, type PoolSettings } from '@/api'
import { ErrorWithRetry, Loading } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { SETTINGS_HASH } from '@/lib/sections'
import { cn } from '@/lib/utils'

/** The gear in the app header: a link to the settings page, `current` while that page is open. It
 * sits in the header's wrapping flex row beside the wordmark and the backup button on a phone,
 * and from `sm` up at the right end, after the backup control. `data-no-shortcuts` keeps the
 * pool's key shortcuts off while it has focus. */
export function SettingsLink({ current }: { current: boolean }) {
  return (
    <a href={SETTINGS_HASH} aria-label="Einstellungen" aria-current={current ? 'page' : undefined} data-no-shortcuts
       className={cn('order-2 inline-flex size-11 items-center justify-center rounded-lg border border-transparent hover:bg-muted hover:text-foreground sm:order-5',
         current ? 'bg-muted text-foreground' : 'text-muted-foreground')}>
      <Gear className="size-5" aria-hidden="true" />
    </a>
  )
}

/** The hint thresholds as a form: the share is shown in percent and sent as 0 to 1. A failed
 * save keeps the input and offers a retry; `onSaved` runs after a stored save. */
export function SettingsForm({ settings, onSaved }: { settings: PoolSettings; onSaved: () => void }) {
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

/** The settings of the pool's hint, as the section „Scoren“ shows them. The stored values come
 * from `GET /pool`, since the API has no route of its own for them; a failed load offers a retry.
 * `onSaved` runs after a stored save, so the pool view can reload its hint. */
export function ScoringSettings({ onSaved }: { onSaved: () => void }) {
  const [settings, setSettings] = useState<PoolSettings | null>(null)
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let stale = false
    api<Pool>('/pool').then((pool) => { if (!stale) setSettings(pool.settings) },
                            () => { if (!stale) setFailed(true) })
    return () => { stale = true }
  }, [attempt])
  if (failed) {
    return <ErrorWithRetry title="Die Einstellungen konnten nicht geladen werden"
                           onRetry={() => { setFailed(false); setAttempt(attempt + 1) }} />
  }
  if (settings === null) return <Loading label="Einstellungen werden geladen" />
  return <SettingsForm settings={settings} onSaved={onSaved} />
}
