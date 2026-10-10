import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Same-origin /api in dev, matching the nginx proxy in Docker, so the API needs no CORS setup.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/docs': 'http://localhost:8000',
      '/openapi.json': 'http://localhost:8000',
    },
  },
})
