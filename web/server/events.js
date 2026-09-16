import { createReadStream } from 'node:fs';
import { realpath, readdir } from 'node:fs/promises';
import { createInterface } from 'node:readline';
import path from 'node:path';

export async function eventPage(root, run, offset = 0, limit = 100) {
  if (!/^[a-zA-Z0-9_-]+$/.test(run) || !Number.isSafeInteger(offset) || offset < 0) throw new Error('Invalid cursor');
  const base = await realpath(root), directory = await realpath(path.join(base, run));
  if (!directory.startsWith(base + path.sep)) throw new Error('Path outside runs');
  const candidates = ['network.jsonl'];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.isDirectory() && entry.name.startsWith('invocation-')) candidates.push(`${entry.name}/output/framework.jsonl`);
  }
  try {
    const inputs = await realpath(path.join(directory, 'evaluation/inputs'));
    if (!inputs.startsWith(directory + path.sep)) throw new Error('Path outside run');
    for (const name of (await readdir(inputs)).sort()) if (/^\d{4}$/.test(name)) candidates.push(`evaluation/inputs/${name}/framework.jsonl`);
  } catch (e) { if (e.code !== 'ENOENT') throw e; }
  const events = [], warnings = [];
  let index = 0;
  for (const name of candidates) {
    let file;
    try { file = await realpath(path.join(directory, name)); }
    catch (e) { if (e.code === 'ENOENT') continue; throw e; }
    if (!file.startsWith(directory + path.sep)) throw new Error('Path outside run');
    const stream = createReadStream(file), lines = createInterface({ input: stream, crlfDelay: Infinity });
    try {
      for await (const text of lines) {
        if (!text) continue;
        if (index++ < offset) continue;
        if (events.length >= limit) return { events, warnings, next: index - 1 };
        try { events.push({ file: name, raw: JSON.parse(text) }); }
        catch { warnings.push(`${name}: incomplete or invalid JSON`); }
      }
    } finally { lines.close(); stream.destroy(); }
  }
  return { events, warnings, next: null };
}
