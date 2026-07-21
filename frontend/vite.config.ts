import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// The dev server proxies /api and system routes to the FastAPI backend so the
// browser talks to a single origin (matches the local-first deployment posture).
// Backend origin. Override with API_PROXY_TARGET to point the dev server at a backend on
// a different port (e.g. a second instance running alongside one that already holds 8000).
const apiTarget = process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    // Honor the PORT env var (used by the preview harness); default to 5200 otherwise.
    port: Number(process.env.PORT) || 5200,
    proxy: {
      '/api': apiTarget,
      '/healthz': apiTarget,
    },
  },
  test: {
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // Component tests (.tsx) render React and need a DOM; the pure-logic lib tests (.ts)
    // read golden fixtures off disk via import.meta.url, which must stay a file:// URL —
    // so they keep the default node environment.
    environmentMatchGlobs: [['**/*.tsx', 'jsdom']],
  },
})
