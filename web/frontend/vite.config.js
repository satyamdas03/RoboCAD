import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/health': 'http://127.0.0.1:8000',
      '/generate': 'http://127.0.0.1:8000',
      '/decompose': 'http://127.0.0.1:8000',
      '/classify-domain': 'http://127.0.0.1:8000',
      '/capabilities': 'http://127.0.0.1:8000',
      '/robot-templates': 'http://127.0.0.1:8000',
      '/designs': 'http://127.0.0.1:8000',
      '/exports': 'http://127.0.0.1:8000',
      '/onshape': 'http://127.0.0.1:8000',
    },
  },
})
