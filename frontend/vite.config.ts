import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    // maplibre-gl (~1 MB minified, ~285 kB gzipped) is a known,
    // unavoidable single dependency — the warning threshold only
    // guards against OUR code regressing into a monolith again.
    chunkSizeWarningLimit: 1100,
    rollupOptions: {
      output: {
        // maplibre-gl dominates the bundle — isolate it so app-code
        // releases don't invalidate the (heavily cached) map chunk.
        manualChunks: {
          maplibre: ['maplibre-gl'],
          vendor: ['react', 'react-dom', 'zustand'],
        },
      },
    },
  },
  server: {
    port: 3010,
    strictPort: false,
    proxy: {
      '/tiles': 'http://localhost:8002',
      '/api': 'http://localhost:8002',
    },
  },
})
