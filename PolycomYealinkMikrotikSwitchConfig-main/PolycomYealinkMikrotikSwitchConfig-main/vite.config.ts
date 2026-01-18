import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  server: {
    host: '0.0.0.0',
    port: 3002,
    strictPort: true,
    open: true,
    allowedHosts:['timsablab.com','timsablab.ddn.net'],
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
        // Remote diagnostics can take a while (SSH + multiple commands). Avoid proxy-level 504s.
        timeout: 5 * 60 * 1000,
        proxyTimeout: 5 * 60 * 1000,
      }
    }
  },
  plugins: [react()],
})
