import { readFile, realpath, readdir } from 'node:fs/promises';
import path from 'node:path';
import { toolFailures } from './failures.js';

export async function evaluation(root, run) {
  if (!/^[a-zA-Z0-9_-]+$/.test(run)) throw new Error('Invalid run');
  const base = await realpath(root);
  const runDirectory = await realpath(path.join(base, run));
  if (!runDirectory.startsWith(base + path.sep)) throw new Error('Path outside runs');
  // Observe runs can have metadata before any evaluation artifacts exist.
  let directory;
  try {
    directory = await realpath(path.join(runDirectory, 'evaluation'));
    if (!directory.startsWith(runDirectory + path.sep)) throw new Error('Path outside run');
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  async function read(relative) {
    if (!directory) return null;
    try {
      const file = await realpath(path.join(directory, relative));
      if (!file.startsWith(directory + path.sep)) throw new Error('Path outside evaluation');
      return JSON.parse(await readFile(file, 'utf8'));
    } catch (error) { if (error.code === 'ENOENT') return null; throw error; }
  }
  let steps = [];
  if (directory) {
    try {
      const inputs = await realpath(path.join(directory, 'inputs'));
      if (!inputs.startsWith(directory + path.sep)) throw new Error('Path outside evaluation');
      steps = (await readdir(inputs)).filter(name => /^\d{4}$/.test(name)).sort();
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  let metadata = {};
  try {
    const metadataFile = await realpath(path.join(runDirectory, 'run.json'));
    if (!metadataFile.startsWith(runDirectory + path.sep)) throw new Error('Path outside run');
    metadata = JSON.parse(await readFile(metadataFile, 'utf8'));
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  return { public_result: metadata.evaluation_result || {}, execution_status: metadata.status ?? null, manifest: await read('manifest.json'), process: await read('process.json'),
    case: await read('case.json'), judge: await read('judge/report.json'), error: await read('error.json'),
    inputs: await Promise.all(steps.map(async step => ({ step,
      failures: await toolFailures(directory, step),
      input: await read(`inputs/${step}/input.json`), result: await read(`inputs/${step}/result.json`),
      submission: await read(`inputs/${step}/submission.json`), evidence: await read(`inputs/${step}/evidence.json`),
    }))) };
}
