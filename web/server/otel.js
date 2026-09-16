import { createReadStream } from 'node:fs';
import { readdir, realpath, readFile } from 'node:fs/promises';
import { createInterface } from 'node:readline';
import path from 'node:path';

const valid = value => /^[a-zA-Z0-9_-]+$/.test(value);
async function safe(root, file) {
  const base = await realpath(root);
  const resolved = await realpath(file);
  if (!resolved.startsWith(base + path.sep)) throw new Error('Path escapes the allowed root');
  return resolved;
}

export async function otelSpans(root, run) {
  if (!valid(run)) throw new Error('Invalid run ID');
  const directory = await safe(root, path.join(root, run));
  const entries = await readdir(directory, { withFileTypes: true });
  const spans = [], warnings = [], statuses = [];
  const folders = entries.filter(e => e.isDirectory() && e.name.startsWith('invocation-')).map(e => ({ name: e.name, relative: `${e.name}/output` }));
  try {
    const inputs = await safe(directory, path.join(directory, 'evaluation/inputs'));
    for (const e of await readdir(inputs, { withFileTypes: true })) {
      if (e.isDirectory() && /^\d{4}$/.test(e.name)) folders.push({ name: e.name, relative: `evaluation/inputs/${e.name}` });
    }
  } catch {}
  for (const entry of folders) {
    const output = await safe(directory, path.join(directory, entry.relative)).catch(() => null);
    if (!output) continue;
    for (const filename of ['otel-live.jsonl', 'otel.jsonl']) {
    try {
      const file = await safe(output, path.join(output, filename));
      const lines = createInterface({ input: createReadStream(file), crlfDelay: Infinity });
      let line = 0;
      for await (const text of lines) {
        line++;
        if (!text) continue;
        try {
          const row = JSON.parse(text);
          if (row.source === 'otel' && row.event === 'span') spans.push({ ...row.data, invocation: entry.name, output_directory: entry.relative });
        } catch { warnings.push(`${entry.name}/otel.jsonl line ${line} is incomplete or invalid`); }
      }
    } catch (error) { if (error.code !== 'ENOENT') warnings.push(`Unable to read OTel for ${entry.name}`); }
    }
    try {
      const file = await safe(output, path.join(output, 'otel-status.json'));
      statuses.push({ invocation: entry.name, ...JSON.parse(await readFile(file, 'utf8')) });
    } catch { statuses.push({ invocation: entry.name, status: 'running_or_unavailable' }); }
  }
  return { spans: [...new Map(spans.map(s => [`${s.trace_id}:${s.span_id}`, s])).values()], warnings, statuses };
}

export async function otelPayload(root, run, spanId, label) {
  if (!/^[0-9a-f]{16}$/.test(spanId) || !['input', 'output', 'error', 'metadata', 'events'].includes(label)) throw new Error('Invalid payload');
  const { spans } = await otelSpans(root, run);
  const span = spans.find(s => s.span_id === spanId);
  const ref = span?.attributes?.[`abb.${label}_ref`];
  if (!ref) throw new Error('This step does not contain the requested payload');
  const output = await safe(root, path.join(root, run, span.output_directory));
  const file = await safe(output, path.join(output, ref));
  const text = await readFile(file, 'utf8');
  return label === 'events' ? text.split('\n').filter(Boolean).map(line => JSON.parse(line)) : JSON.parse(text);
}
