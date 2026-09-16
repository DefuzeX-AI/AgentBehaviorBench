import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { runsPlugin } from './server/runs.js';
import { suiteProxySettings } from './server/suiteProxy.js';

const suite = suiteProxySettings();
export default defineConfig({
  cacheDir: '../cache/vite',
  plugins: [react(), ...suite.plugins, ...(!suite.proxy ? [runsPlugin(fileURLToPath(new URL('../results/observe', import.meta.url)))] : [])],
  server: { proxy: suite.proxy }, preview: { proxy: suite.proxy },
});
