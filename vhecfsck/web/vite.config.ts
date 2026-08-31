import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  root: resolve(__dirname),
  build: {
    outDir: resolve(__dirname, 'dist'),
    emptyOutDir: true,
    target: 'esnext',
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks: {
          three: ['three']
        }
      }
    }
  },
  server: {
    port: 5173,
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true
      }
    }
  },
  test: {
    environment: 'happy-dom',
    globals: true,
    include: ['tests/unit/**/*.test.ts', 'tests/visual/**/*.test.ts', 'tests/perf/**/*.test.ts']
  }
});
