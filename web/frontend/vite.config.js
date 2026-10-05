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
      '/hermes': 'http://127.0.0.1:8000',
      '/morphology': 'http://127.0.0.1:8000',
      '/verify': 'http://127.0.0.1:8000',
      '/deep-verify': 'http://127.0.0.1:8000',
      '/train-brain': 'http://127.0.0.1:8000',
      '/marketplace': 'http://127.0.0.1:8000',
      '/compose-scene': 'http://127.0.0.1:8000',
      '/worlds': 'http://127.0.0.1:8000',
      '/scenes': 'http://127.0.0.1:8000',
    },
  },
})
