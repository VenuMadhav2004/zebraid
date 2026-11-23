import process from 'node:process'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // 127.0.0.1, not localhost: Node may resolve localhost to ::1 while uvicorn listens on IPv4.
  const target = env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'
  return {
    plugins: [react(), tailwindcss()],
    server: {
      host: '0.0.0.0', // reachable from outside the container
      port: 5173,
      strictPort: true,
      hmr: false,
      allowedHosts: ['.ngrok-free.app', '.ngrok-free.dev', '.ngrok.io', '.ngrok.app'],
      // Browser calls /api/* on the Vite origin; Vite forwards to FastAPI.
      // First matching key wins, so the more specific /api/v1 rule must come first.
      proxy: {
        // Versioned API: backend serves it at /api/v1/*, so the path is kept as-is.
        '/api/v1': {
          target,
          changeOrigin: true,
          timeout: 0,
          proxyTimeout: 0,
        },
        // Unversioned probes: backend serves /health and /health/db at the root,
        // so /api/health -> /health.
        '/api': {
          target,
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api/, ''),
        },
      },
    },
  }
})
