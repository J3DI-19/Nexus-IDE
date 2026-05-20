import { defineConfig, splitVendorChunkPlugin } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), splitVendorChunkPlugin()],
  build: {
    rollupOptions: {
      input: 'index.html',
      output: {
        manualChunks(id) {
          const moduleId = id.replace(/\\/g, '/')
          if (moduleId.includes('node_modules/@monaco-editor') || moduleId.includes('node_modules/monaco-editor')) {
            return 'vendor-monaco'
          }
          if (moduleId.includes('node_modules/@xterm')) {
            return 'vendor-xterm'
          }
          if (moduleId.includes('node_modules/lucide-react')) {
            return 'vendor-icons'
          }
          if (moduleId.includes('node_modules/react') || moduleId.includes('node_modules/react-dom')) {
            return 'vendor-react'
          }
          return undefined
        },
      },
    },
    chunkSizeWarningLimit: 450,
  },
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
