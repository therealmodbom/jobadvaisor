import { vi } from 'vitest'

/** A request the stubbed API received: method, path and the parsed JSON or form body. */
export type Call = { method: string; path: string; body: unknown }

type Reply = { status?: number; body?: unknown }
type Answer = Reply | Promise<Reply>

/** The default `GET /backup`: a backed-up repository with nothing pending. */
const QUIET_BACKUP = {
  pending: false, uncommitted: 0, unpushed: 0, branch: 'main', remote: 'origin/main',
  operation: null, running: false, progress: null, last_result: null,
  last_success: '2026-11-12T09:12:00Z', last_failure: null,
}

/** Replaces `fetch` with a router over `routes` ("METHOD /path" → answer or answer function),
 * and returns the calls it received. An unrouted request fails the test. The app shell asks
 * `GET /health` and `GET /backup` on every render, and the intake view and the shell ask
 * `GET /unsettled-links`, so it answers healthy with version `dev`, a quiet backup (nothing
 * pending) and an empty list of unsettled links unless a test routes them itself. */
export function stubApi(routes: Record<string, Answer | ((call: Call) => Answer)>): Call[] {
  routes = { 'GET /health': { body: { status: 'ok', checks: { data_repo: 'ok' }, version: 'dev' } },
             'GET /backup': { body: QUIET_BACKUP },
             'GET /unsettled-links': { body: { links: [], run_id: null } },
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
    const status = answer.status ?? 200
    // A 204 has no body; `Response` refuses to carry one.
    return new Response(status === 204 ? null : JSON.stringify(answer.body ?? {}), {
      status, headers: { 'Content-Type': 'application/json' },
    })
  }))
  return calls
}

/** An answer that never arrives, for waiting states. */
export const pending = () => new Promise<never>(() => {})
