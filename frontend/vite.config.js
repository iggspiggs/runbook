import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    // When running inside Docker the backend is reachable at http://backend:8000.
    // Set VITE_PROXY_TARGET in your environment (docker-compose passes it via
    // VITE_API_URL) to override.  Falls back to localhost for local dev.
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          flow: ['reactflow', '@dagrejs/dagre'],
          state: ['zustand', 'axios'],
        },
      },
    },
  },
})
