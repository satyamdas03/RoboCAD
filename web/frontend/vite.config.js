import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/generate': 'http://localhost:8000',
      '/designs': 'http://localhost:8000',
      '/exports': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/onshape': 'http://localhost:8000',
    },
  },
})
