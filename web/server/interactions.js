// Keep one normalization implementation for the Python viewer and Vite.
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { realpath } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const project = fileURLToPath(new URL('../../', import.meta.url));
export async function interactionPage(root, run, query, signal) {
  if (!/^[a-zA-Z0-9_-]+$/.test(run)) throw new Error('Invalid run');
  const base = await realpath(root), directory = await realpath(path.join(base, run));
  if (!directory.startsWith(base + path.sep)) throw new Error('Path outside runs');
  const venv = path.join(project, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const python = process.env.ABB_PYTHON || (existsSync(venv) ? venv : 'python3');
  return new Promise((resolve, reject) => {
    const child = spawn(python, ['-m', 'agentbench.observe.interactions', directory, JSON.stringify(query)],
      { cwd: project, shell: false, signal });
    const output = [];
    child.stdout.on('data', chunk => output.push(chunk));
    child.stderr.resume();
    child.on('error', reject);
    child.on('close', code => {
      if (code !== 0) return reject(new Error('Interaction index unavailable'));
      try { resolve(JSON.parse(Buffer.concat(output).toString('utf8'))); } catch (error) { reject(error); }
    });
  });
}
