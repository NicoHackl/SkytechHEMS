import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/* Auslieferung unter dem HA-Ingress: Der Pfad /api/hassio_ingress/<token>/ steht
   erst zur Laufzeit fest. Deshalb relative Asset-Pfade (base) und relative
   API-Aufrufe in api.ts — siehe docs/frontend.md, D-036. */
export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    // aiohttp liefert direkt aus app/static/ aus; das Bundle ist eingecheckt (D-035).
    outDir: '../app/static',
    emptyOutDir: true,
  },
  server: {
    host: '127.0.0.1',
    port: 5174,
    proxy: {
      // Dev: gleiche Origin wie in Produktion, kein CORS. Ziel ist das laufende Add-on.
      '/api': { target: 'http://127.0.0.1:8099', changeOrigin: true },
    },
  },
})
