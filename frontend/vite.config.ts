import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: 'localhost',
    port: 5173,
    proxy: {
      '/api/learning': {
        target: 'http://127.0.0.1:8767',
        changeOrigin: true,
      },
      '/api/story-editor': {
        target: 'http://127.0.0.1:8766',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      input: {
        storyEditor: 'story-editor.html',
        learning: 'learning.html',
      },
    },
  },
});
