/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from 'vite'
import { fileURLToPath } from 'node:url'
import http from 'node:http'
import net from 'node:net'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// ── /api routing in dev ─────────────────────────────────────────────────────
// The browser only ever talks to :5173 (no CORS). Each /api request goes to
// whichever backend is actually running, re-checked every couple of seconds,
// so nothing needs configuring and switching modes needs no restart:
//   local (.\dev-local.ps1)  Express on :3000 answers -> Express :3000, and
//                            /api/ai/* -> FastAPI on BACKEND_AI_PORT with the
//                            /api/ai prefix stripped, as NGINX does.
//   docker (compose up)      otherwise -> NGINX on :80, which routes internally.
// Vite's built-in proxy fixes its target at startup, hence this middleware.

const EXPRESS_PORT = 3000
const NGINX_PORT = 80

function portOpen(port, host = '127.0.0.1', timeoutMs = 300) {
  return new Promise((resolve) => {
    const sock = net.connect({ port, host })
    const done = (ok) => { sock.destroy(); resolve(ok) }
    sock.setTimeout(timeoutMs, () => done(false))
    sock.once('connect', () => done(true))
    sock.once('error', () => done(false))
  })
}

// Cached briefly so a burst of requests doesn't open a probe socket each.
let localCheck = { at: 0, up: false }
async function localBackendUp() {
  if (Date.now() - localCheck.at > 2000) {
    localCheck = { at: Date.now(), up: await portOpen(EXPRESS_PORT) }
  }
  return localCheck.up
}

function apiRouter(aiPort) {
  return {
    name: 'docling-api-router',
    configureServer(server) {
      server.middlewares.use('/api', async (req, res) => {
        const path = req.originalUrl
        let port = NGINX_PORT
        let upstreamPath = path
        if (await localBackendUp()) {
          const isAi = path === '/api/ai' || path.startsWith('/api/ai/') || path.startsWith('/api/ai?')
          port = isAi ? aiPort : EXPRESS_PORT
          upstreamPath = isAi ? path.slice('/api/ai'.length) || '/' : path
        }

        const upstream = http.request({
          host: '127.0.0.1',
          port,
          path: upstreamPath,
          method: req.method,
          headers: { ...req.headers, host: `127.0.0.1:${port}` },
        }, (up) => {
          res.writeHead(up.statusCode, up.headers)
          up.pipe(res) // streams, so SSE events pass through as they arrive
        })
        upstream.on('error', (err) => {
          if (res.headersSent) return res.destroy(err)
          res.writeHead(502, { 'content-type': 'application/json' })
          res.end(JSON.stringify({
            error: `No backend is running (${err.code} on port ${port}). ` +
              'Start .\\dev-local.ps1 for the local setup, or `docker compose up` for Docker.',
          }))
        })
        // Browser gave up (navigated away, aborted): stop the upstream work too.
        res.on('close', () => upstream.destroy())
        req.pipe(upstream)
      })
    },
  }
}

const repoRoot = fileURLToPath(new URL('..', import.meta.url))

export default defineConfig(({ mode }) => ({
  plugins: [
    react(),
    tailwindcss(),
    // FastAPI's local port comes from BACKEND_AI_PORT in the repo-root .env, the
    // same value backend_ai/main.py binds to.
    apiRouter(Number(loadEnv(mode, repoRoot, '').BACKEND_AI_PORT || 8000)),
  ],
  server: {
    proxy: {
      '/latex-api': {
        target: 'https://latexonline.cc',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/latex-api/, '')
      }
    }
  },
  // Vitest — jsdom env + a setup file that registers jest-dom matchers.
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    css: false,
  },
}))
