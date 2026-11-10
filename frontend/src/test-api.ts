import { vi } from 'vitest'

/** A request the stubbed API received: method, path and the parsed JSON or form body. */
export type Call = { method: string; path: string; body: unknown }

type Answer = { status?: number; body?: unknown } | Promise<never>

/** Replaces `fetch` with a router over `routes` ("METHOD /path" → answer or answer function),
 * and returns the calls it received. An unrouted request fails the test. The app shell asks
 * `GET /health` on every render, so it answers healthy with version `dev` unless a test routes
 * it itself. */
export function stubApi(routes: Record<string, Answer | ((call: Call) => Answer)>): Call[] {
  routes = { 'GET /health': { body: { status: 'ok', checks: { data_repo: 'ok' }, version: 'dev' } },
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
