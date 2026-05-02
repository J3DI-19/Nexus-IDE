import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/scan': 'http://localhost:5000',
      '/prompt': 'http://localhost:5000',
      '/apply': 'http://localhost:5000',
      '/run': 'http://localhost:5000'
    }
  }
})
