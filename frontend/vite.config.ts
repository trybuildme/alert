import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3010,
    strictPort: false,
    proxy: {
      '/tiles': 'http://localhost:8002',
      '/api': 'http://localhost:8002',
    },
  },
})
