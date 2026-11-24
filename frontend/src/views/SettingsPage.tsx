import { ScoringSettings } from '@/components/settings'
import { SECTIONS, sectionHash, type SectionId } from '@/lib/sections'
import { cn } from '@/lib/utils'

const PANEL = 'flex flex-col gap-3.5 rounded-xl border bg-card p-5 shadow-card'

/** The settings page (`#/einstellungen`, `#/einstellungen/<section>`): its sections are listed
 * beside the content, and above it at a phone's width; each has its own address. `section` is
 * the open one, and `onSaved` runs after the hint settings of „Scoren“ were stored, so the pool
 * view can reload its hint. */
export function SettingsPage({ section, onSaved }: { section: SectionId; onSaved: () => void }) {
  return (
    <div className="mx-auto flex max-w-[960px] flex-col gap-6">
      <h1 className="text-3xl leading-tight font-bold tracking-tight">Einstellungen</h1>
      <div className="flex flex-col gap-6 md:flex-row md:items-start">
        <nav aria-label="Bereiche der Einstellungen" className="flex flex-wrap gap-1 md:w-48 md:flex-none md:flex-col">
          {SECTIONS.map((item) => (
            <a key={item.id} href={sectionHash(item.id)} aria-current={item.id === section ? 'page' : undefined}
               className={cn('rounded-lg px-3.5 py-2.5 no-underline',
                 item.id === section ? 'bg-muted font-bold text-foreground'
                   : 'font-medium text-muted-foreground hover:text-foreground')}>
              {item.label}
            </a>
          ))}
        </nav>
        <div className="min-w-0 flex-1">
          {section === 'scoren' && (
            <section aria-labelledby="settings-scoring" className={PANEL}>
              <div>
                <h2 id="settings-scoring" className="text-lg font-bold">Hinweis „neu scoren sinnvoll“</h2>
                <p className="mt-0.5 text-[15px] text-muted-foreground">Ab wann der Hinweis unter dem Scoren-Button erscheint.</p>
              </div>
              <ScoringSettings onSaved={onSaved} />
            </section>
          )}
          {section === 'postfach' && (
            <section aria-labelledby="settings-mailbox" className={PANEL}>
              <h2 id="settings-mailbox" className="text-lg font-bold">Postfach</h2>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}
