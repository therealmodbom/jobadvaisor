import { useEffect, useState } from 'react'
import { api } from '@/api'

/** The version this frontend was built with: the release tag from `VITE_APP_VERSION`, `dev` for
 * a local or CI build. Read on every call so tests can stub it. */
export function frontendVersion(): string {
  return import.meta.env.VITE_APP_VERSION || 'dev'
}

/** The version the backend reports (`GET /version`): `null` until a fetch has succeeded, then the
 * last one fetched. It is fetched on mount and whenever the tab becomes visible again; a failed
 * fetch changes nothing, so a known version (and the banner it caused) stays. */
export function useBackendVersion(): string | null {
  const [version, setVersion] = useState<string | null>(null)
  useEffect(() => {
    let mounted = true
    const load = () => {
      api<{ version: string }>('/version').then(
        (answer) => { if (mounted) setVersion(answer.version) },
        () => {},
      )
    }
    const onVisibility = () => { if (document.visibilityState === 'visible') load() }
    load()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      mounted = false
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])
  return version
}
