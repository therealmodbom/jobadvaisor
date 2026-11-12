import { vi } from 'vitest'

/** A request the stubbed API received: method, path and the parsed JSON or form body. */
export type Call = { method: string; path: string; body: unknown }

type Answer = { status?: number; body?: unknown } | Promise<never>

/** The default `GET /backup`: a backed-up repository with nothing pending. */
const QUIET_BACKUP = {
  pending: false, uncommitted: 0, unpushed: 0, branch: 'main', remote: 'origin/main',
  operation: null, running: false, progress: null, last_result: null,
  last_success: '2026-11-12T09:12:00Z', last_failure: null,
}

/** Replaces `fetch` with a router over `routes` ("METHOD /path" → answer or answer function),
 * and returns the calls it received. An unrouted request fails the test. The app shell asks
 * `GET /health` and `GET /backup` on every render, so it answers healthy with version `dev` and
 * a quiet backup (nothing pending) unless a test routes them itself. */
export function stubApi(routes: Record<string, Answer | ((call: Call) => Answer)>): Call[] {
  routes = { 'GET /health': { body: { status: 'ok', checks: { data_repo: 'ok' }, version: 'dev' } },
             'GET /backup': { body: QUIET_BACKUP },
             ...routes }
  const calls: Call[] = []
  vi.stubGlobal('fetch', vi.fn(async (path: string, init: RequestInit = {}) => {
    const method = init.method ?? 'GET'
    const raw = init.body
    const body = raw instanceof FormData ? Object.fromEntries(raw)
      : typeof raw === 'string' ? JSON.parse(raw) : undefined
    const call = { method, path, body }
    calls.push(call)
    const route = routes[`${method} ${path}`]
    if (!route) throw new Error(`unrouted request ${method} ${path}`)
    const answer = await (typeof route === 'function' ? route(call) : route)
    return new Response(JSON.stringify(answer.body ?? {}), {
      status: answer.status ?? 200, headers: { 'Content-Type': 'application/json' },
    })
  }))
  return calls
}

/** An answer that never arrives, for waiting states. */
export const pending = () => new Promise<never>(() => {})
