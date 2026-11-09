import { useEffect, useState } from 'react'
import { StaleBanner, VersionFooter } from '@/components/version'
import { cn } from '@/lib/utils'
import { useBackendVersion } from '@/lib/version'
import { ChatView } from '@/views/ChatView'
import { IntakeView } from '@/views/IntakeView'
import { PoolView } from '@/views/PoolView'
import { PostingPage } from '@/views/PostingPage'

/** The three views by URL hash; the first is the default for an empty or unknown hash. Hash
 * routing keeps every view reachable after a reload without the backend having to tell app
 * paths from API paths such as `/pool`. */
const VIEWS = [
  { hash: '#/pool', label: 'Anzeigen', title: 'Deine Anzeigen' },
  { hash: '#/hinzufuegen', label: 'Anzeige hinzufügen', title: 'Anzeige hinzufügen' },
  { hash: '#/fragen', label: 'Fragen', title: 'Fragen zu deinen Anzeigen' },
] as const

type View = (typeof VIEWS)[number]

/** The list import: "Anzeige hinzufügen" with its source "Liste" chosen. */
const IMPORT_HASH = '#/importieren'

const POSTING_PREFIX = '#/anzeigen/'

/** The ID of the posting page the hash opens (`#/anzeigen/<id>`, URI-decoded), else `null`. */
function postingIdOf(hash: string): string | null {
  if (!hash.startsWith(POSTING_PREFIX) || hash.length === POSTING_PREFIX.length) return null
  const rest = hash.slice(POSTING_PREFIX.length)
  try {
    return decodeURIComponent(rest)
  } catch {
    return rest
  }
}

/** The app shell: the stale-page banner (only when the server runs another version), the header
 * with the main navigation, the open view and the version footer; the three main
 * views stay mounted but hidden (so an import keeps polling), a posting page mounts only while
 * its route is open and keeps "Anzeigen" current in the navigation. The page sets its own
 * document title. */
function App() {
  const [hash, setHash] = useState(() => window.location.hash)
  useEffect(() => {
    const follow = () => setHash(window.location.hash)
    window.addEventListener('hashchange', follow)
    return () => window.removeEventListener('hashchange', follow)
  }, [])
  const postingId = postingIdOf(hash)
  const importing = hash === IMPORT_HASH
  const view: View = importing ? VIEWS[1] : VIEWS.find((entry) => entry.hash === hash) ?? VIEWS[0]
  useEffect(() => {
    document.title = `${postingId ? 'Anzeige' : view.title} – JobAdvAIsor`
  }, [view, postingId])

  const backendVersion = useBackendVersion()

  const content = {
    '#/pool': <PoolView active={view === VIEWS[0] && postingId === null} />,
    '#/hinzufuegen': <IntakeView list={importing} />,
    '#/fragen': <ChatView />,
  }
  return (
    <>
      <StaleBanner backend={backendVersion} />
      <header className="border-b bg-card">
        <div className="mx-auto flex min-h-16 max-w-[1200px] flex-wrap items-center gap-x-8 gap-y-2 px-6">
          <a href={VIEWS[0].hash} className="text-[19px] font-bold tracking-tight text-foreground no-underline">
            JobAdvAIsor
          </a>
          <nav aria-label="Hauptnavigation" className="flex flex-auto flex-wrap gap-1">
            {VIEWS.map((item) => (
              <a key={item.hash} href={item.hash} aria-current={item === view ? 'page' : undefined}
                 className={cn('rounded-lg px-3.5 py-2.5 no-underline',
                   item === view ? 'bg-muted font-bold text-foreground'
                     : 'font-medium text-muted-foreground hover:text-foreground')}>
                {item.label}
              </a>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto box-border max-w-[1200px] px-6 pt-8 pb-16">
        {/* Every view stays mounted and only the open one shows, so a conversation, an intake
            result or a computing pass survives a look at another view. */}
        {VIEWS.map((item) => <div key={item.hash} hidden={postingId !== null || item !== view}>{content[item.hash]}</div>)}
        {postingId !== null && <PostingPage postingId={postingId} />}
      </main>
      <VersionFooter backend={backendVersion} />
    </>
  )
}

export default App
