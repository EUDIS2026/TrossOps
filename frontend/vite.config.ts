import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// TROSSOPS_API overrides the API the dev server proxies to (e.g. a second backend in public-demo mode)
const api = process.env.TROSSOPS_API ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': { target: api, changeOrigin: true } } },
  preview: { port: 4173, proxy: { '/api': { target: api, changeOrigin: true } } },
  build: {
    target: 'es2022', sourcemap: true, chunkSizeWarningLimit: 1600,
    rollupOptions: { output: { manualChunks: { maplibre: ['maplibre-gl'], three: ['three'], milsymbol: ['milsymbol'], h3: ['h3-js'], react: ['react', 'react-dom'] } } },
  },
})
