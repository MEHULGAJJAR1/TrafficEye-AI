import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const proxy = {
  '/api': { target: process.env.TE_BACKEND_URL || 'http://127.0.0.1:8000', ws: true, changeOrigin: false },
};
export default defineConfig({
  plugins: [react()],
  server: { host: '0.0.0.0', port: 5173, strictPort: true, allowedHosts: ['.e2b.app', 'localhost', '127.0.0.1'], proxy },
  preview: { host: '0.0.0.0', port: 4173, strictPort: true, allowedHosts: ['.e2b.app', 'localhost', '127.0.0.1'], proxy },
  build: { sourcemap: false, chunkSizeWarningLimit: 700, rollupOptions: { output: { manualChunks: { charts: ['recharts'] } } } },
});
