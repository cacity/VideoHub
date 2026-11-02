import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

const learningBuild = createHash('sha256').update([
  'learning.html', 'src/learning.tsx', 'src/learning-shortcuts.ts', 'src/learning-api.ts',
  'src/learning-panel.tsx', 'src/learning-resize.tsx', 'src/learning.css',
  'src/learning-markdown.tsx', 'src/learning-mindmap.tsx', 'package-lock.json',
].map(name => readFileSync(new URL(name, import.meta.url))).join('\n')).digest('hex').slice(0, 12);

export default defineConfig({
  plugins: [react(), {
    name: 'learning-build-id',
    transformIndexHtml: html => html.replace('__VIDEOHUB_LEARNING_BUILD__', learningBuild),
  }],
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
