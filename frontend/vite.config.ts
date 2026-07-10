import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies /api and system routes to the FastAPI backend so the
// browser talks to a single origin (matches the local-first deployment posture).
export default defineConfig({
  plugins: [react()],
  server: {
    // Honor the PORT env var (used by the preview harness); default to 5200 otherwise.
    port: Number(process.env.PORT) || 5200,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/healthz': 'http://127.0.0.1:8000',
    },
  },
})
