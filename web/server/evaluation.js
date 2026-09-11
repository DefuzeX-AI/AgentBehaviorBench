import { readFile, realpath, readdir } from 'node:fs/promises';
import path from 'node:path';

export async function evaluation(root, run) {
  if (!/^[a-zA-Z0-9_-]+$/.test(run)) throw new Error('Invalid run');
  const base = await realpath(root);
  const directory = await realpath(path.join(root, run, 'evaluation'));
  if (!directory.startsWith(base + path.sep)) throw new Error('Path outside runs');
  async function read(relative) {
    try {
      const file = await realpath(path.join(directory, relative));
      if (!file.startsWith(directory + path.sep)) throw new Error('Path outside evaluation');
      return JSON.parse(await readFile(file, 'utf8'));
    } catch (error) { if (error.code === 'ENOENT') return null; throw error; }
  }
  let steps = [];
  try {
    const inputs = await realpath(path.join(directory, 'inputs'));
    if (!inputs.startsWith(directory + path.sep)) throw new Error('Path outside evaluation');
    steps = (await readdir(inputs)).filter(name => /^\d{4}$/.test(name)).sort();
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  let metadata = {};
  try {
    const metadataFile = await realpath(path.join(root, run, 'run.json'));
    if (!metadataFile.startsWith(base + path.sep)) throw new Error('Path outside runs');
    metadata = JSON.parse(await readFile(metadataFile, 'utf8'));
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  return { public_result: metadata.evaluation_result || {}, execution_status: metadata.status, manifest: await read('manifest.json'), process: await read('process.json'),
    case: await read('case.json'), judge: await read('judge/report.json'), error: await read('error.json'),
    inputs: await Promise.all(steps.map(async step => ({ step,
      input: await read(`inputs/${step}/input.json`), result: await read(`inputs/${step}/result.json`),
      submission: await read(`inputs/${step}/submission.json`), evidence: await read(`inputs/${step}/evidence.json`),
    }))) };
}
