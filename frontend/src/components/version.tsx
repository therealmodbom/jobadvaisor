import { Button } from '@/components/ui/button'
import { frontendVersion } from '@/lib/version'

/** Announces a page older (or newer) than the server: shown while the backend version is known
 * and differs from the frontend's. The reload button is the only way out; nothing reloads by
 * itself, so the views keep what they hold until the user chooses. */
export function StaleBanner({ backend }: { backend: string | null }) {
  const frontend = frontendVersion()
  if (backend === null || backend === frontend) return null
  return (
    <div role="status" className="border-b bg-positive-soft">
      <div className="mx-auto flex max-w-[1200px] flex-wrap items-center gap-x-4 gap-y-2 px-6 py-3">
        <p className="text-foreground">
          Diese Seite ist veraltet: Sie läuft mit {frontend}, das Backend mit {backend}.
        </p>
        <Button variant="outline" onClick={() => window.location.reload()}>Neu laden</Button>
      </div>
    </div>
  )
}

/** The version line at the foot of every view: frontend version, backend version ("unbekannt"
 * until a fetch has succeeded) and the origin the page's requests go to. A full-width rule and
 * the card background set it off from the content, like the header at the top. */
export function VersionFooter({ backend }: { backend: string | null }) {
  return (
    <footer className="border-t bg-card text-sm text-muted-foreground">
      <div className="mx-auto max-w-[1200px] px-6 py-4">
        Frontend {frontendVersion()} · Backend {backend ?? 'unbekannt'} · {window.location.origin}
      </div>
    </footer>
  )
}
