import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { runsPlugin } from './server/runs.js';

export default defineConfig({ plugins: [react(), runsPlugin(fileURLToPath(new URL('../results/observe', import.meta.url)))] });
