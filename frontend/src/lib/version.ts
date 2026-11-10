import { useEffect, useState } from 'react'
import { api, ApiError } from '@/api'

/** The version this frontend was built with: the release tag from `VITE_APP_VERSION`, `dev` for
 * a local or CI build. Read on every call so tests can stub it. */
export function frontendVersion(): string {
  return import.meta.env.VITE_APP_VERSION || 'dev'
}

/** The version the backend reports (`GET /health`): `null` until a fetch has succeeded, then the
 * last one fetched. It is fetched on mount and whenever the tab becomes visible again. A 503
 * answer (a check failed) still carries the version and counts; any other failure, or an answer
 * without a version, changes nothing, so a known version (and the banner it caused) stays. */
export function useBackendVersion(): string | null {
  const [version, setVersion] = useState<string | null>(null)
  useEffect(() => {
    let mounted = true
    const take = (answer: Record<string, unknown>) => {
      if (mounted && typeof answer.version === 'string') setVersion(answer.version)
    }
    const load = () => {
      api<Record<string, unknown>>('/health').then(take, (error) => {
        if (error instanceof ApiError && error.status === 503) take(error.body)
      })
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
