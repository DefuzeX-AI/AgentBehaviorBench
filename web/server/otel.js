import { createReadStream } from 'node:fs';
import { realpath, readFile } from 'node:fs/promises';
import { createInterface } from 'node:readline';
import path from 'node:path';

const valid = value => /^[a-zA-Z0-9_-]+$/.test(value);
async function safe(root, file) {
  const base = await realpath(root);
  const resolved = await realpath(file);
  if (!resolved.startsWith(base + path.sep)) throw new Error('Path escapes the allowed root');
  return resolved;
}

function attributeValue(value = {}) {
  if (value.arrayValue) return (value.arrayValue.values || []).map(attributeValue);
  if (value.kvlistValue) return attributesOf(value.kvlistValue.values);
  return Object.values(value)[0];
}

function attributesOf(attributes = []) {
  return Object.fromEntries(attributes.map(a => [a.key, attributeValue(a.value)]));
}

export async function otelSpans(root, run) {
  if (!valid(run)) throw new Error('Invalid run ID');
  const directory = await safe(root, path.join(root, run));
  // Only spans the Agent itself exported; nothing is derived from other records.
  const spans = [], warnings = [], statuses = [];
  try {
    const folder = await safe(directory, path.join(directory, 'otel'));
    const status = JSON.parse(await readFile(await safe(folder, path.join(folder, 'status.json')), 'utf8'));
    statuses.push({ ...status, invocation: 'Agent' });
    if (status.record_count ?? status.span_count) {
      const file = await safe(folder, path.join(folder, 'spans.jsonl'));
      const lines = createInterface({ input: createReadStream(file), crlfDelay: Infinity });
      let line = 0;
      for await (const text of lines) {
        line++;
        if (!text.trim()) continue;
        const row = JSON.parse(text);
        const s = row.span;
        const attributes = attributesOf(s.attributes);
        spans.push({ trace_id: s.traceId, span_id: s.spanId, parent_span_id: s.parentSpanId, name: s.name,
          start_time_unix_nano: s.startTimeUnixNano, end_time_unix_nano: s.endTimeUnixNano,
          attributes, events: s.events, scope: row.scope, origin: row.origin, resource: row.resource,
          status: { status_code: ({ 0: "UNSET", 1: "OK", 2: "ERROR" })[s.status?.code] || "UNSET" },
          raw: s, output_directory: 'otel', invocation: 'Agent', record_line: line });
      }
    }
  } catch (e) { if (e.code !== 'ENOENT') warnings.push('Unable to read Agent trace: ' + e.message); }
  return { spans: [...new Map(spans.map(s => [`${s.trace_id}:${s.span_id}`, s])).values()], warnings, statuses };
}
