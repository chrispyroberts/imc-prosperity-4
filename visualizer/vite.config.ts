import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  base: '/',
  server: {
    proxy: {
      '/dashboard.json': 'http://127.0.0.1:8001',
      '/run_summary.csv': 'http://127.0.0.1:8001',
      '/session_summary.csv': 'http://127.0.0.1:8001',
      '/sample_paths': 'http://127.0.0.1:8001',
      '/sessions': 'http://127.0.0.1:8001',
      '/static_charts': 'http://127.0.0.1:8001',
    },
  },
  build: {
    minify: true,
    sourcemap: false,
  },
  resolve: {
    alias: {
      '@tabler/icons-react': '@tabler/icons-react/dist/esm/icons/index.mjs',
    },
  },
});
