import { fileURLToPath } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

/** API routes the dev server forwards to the FastAPI backend, so no CORS setup is needed. */
const API_ROUTES = ['/postings', '/runs', '/agent', '/policy-pack', '/imports', '/pool', '/health']
/** Dev ports, chosen to stay clear of other local backends on 8000 and Vite's 5173; the
 * .vscode tasks and launch configs start the backend on API_PORT. */
const API_PORT = 8710
const DEV_PORT = 5710

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    port: DEV_PORT,
    strictPort: true,
    proxy: Object.fromEntries(API_ROUTES.map((route) => [route, `http://127.0.0.1:${API_PORT}`])),
  },
  // TZ is pinned so date assertions read the same on every machine and in CI.
  test: { environment: 'jsdom', setupFiles: ['./src/test-setup.ts'], env: { TZ: 'Europe/Berlin' } },
})
