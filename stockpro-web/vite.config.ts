import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://127.0.0.1:5000',
      '/stream': 'http://127.0.0.1:5000',
      '/continue': 'http://127.0.0.1:5000',
      '/popup_start': 'http://127.0.0.1:5000',
      '/start_generation': 'http://127.0.0.1:5000',
      '/commit_session': 'http://127.0.0.1:5000',
      '/ws': { target: 'ws://127.0.0.1:5000', ws: true },
    },
  },
})
