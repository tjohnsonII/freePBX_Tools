import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  server: {
    host: '0.0.0.0',
    port: 3002,
    strictPort: true,
    open: true,
    allowedHosts:['timsablab.com','timsablab.ddn.net','polycom.123hostedtools.com'],
    headers: {
      'Cache-Control': 'no-cache, no-store, must-revalidate',
    },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
        ws: true,  // required for /api/jobs/{id}/ws WebSocket streaming
        // Remote diagnostics + tool runs can take a while. Avoid proxy-level 504s.
        timeout: 5 * 60 * 1000,
        proxyTimeout: 5 * 60 * 1000,
      }
    }
  },
  plugins: [react()],
})
