/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The app calls Express and FastAPI directly (see src/config/api.js); both send
// permissive CORS headers, so there is no dev proxy and no reverse proxy.
// envDir points Vite at the repo-root .env, the single place API URLs and
// secrets live, so VITE_EXPRESS_URL / VITE_AI_URL are picked up from there.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  envDir: fileURLToPath(new URL('..', import.meta.url)),

  // Vitest — jsdom env + a setup file that registers jest-dom matchers.
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    css: false,
  },
})
