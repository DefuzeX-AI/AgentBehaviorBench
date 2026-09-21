import { readFileSync, createReadStream } from 'node:fs';
import { realpath } from 'node:fs/promises';
import path from 'node:path';
const rules = JSON.parse(readFileSync(new URL('../../agentbench/observe/failure_rules.json', import.meta.url), 'utf8'));

export function classifyFailure(tool, error, source, span_id) {
  const code = error && typeof error === 'object' ? error.code : null;
  const message = error && typeof error === 'object' ? error.message : error;
  if (typeof message !== 'string' || !message.trim()) return null;
  const rule = rules.find(r => r.provider === tool.split('.')[0]
    && (code ? r.codes.includes(code) : message.startsWith(r.message_prefix)));
  return { category: rule?.category || 'tool_error', summary: rule?.summary || `${tool} failed`,
    message: message.slice(0, 2000), tool, source, span_id };
}

export async function toolFailures(directory, step) {
  const relative = `inputs/${step}/framework.jsonl`;
  const spans = new Map(), seen = new Set(), failures = [];
  try {
    const file = await realpath(path.join(directory, relative));
    if (!file.startsWith(directory + path.sep)) return [];
    let pending = '', consumed = 0, number = 0;
    for await (const chunk of createReadStream(file, { encoding: 'utf8', highWaterMark: 65536 })) {
      consumed += chunk.length;
      if (consumed > 8 * 1024 * 1024) break;
      pending += chunk;
      let end;
      while ((end = pending.indexOf('\n')) >= 0) {
        const line = pending.slice(0, end); pending = pending.slice(end + 1); number++;
        if (line.length > 262144 || number > 100000) return failures;
        let row;
        try { row = JSON.parse(line); } catch { continue; }
        const data = row?.data;
        if (!data || typeof data.span_id !== 'string') continue;
        if (row.event === 'span_start' && data.kind === 'tool') spans.set(data.span_id, String(data.name || 'Tool').slice(0, 200));
        if (row.event !== 'span_error' || !spans.has(data.span_id)) continue;
        const failure = classifyFailure(spans.get(data.span_id), data.error, `evaluation/${relative}:${number}`, data.span_id);
        if (!failure) continue;
        const key = JSON.stringify([failure.tool, failure.message]);
        if (seen.has(key)) continue;
        seen.add(key); failures.push(failure);
        if (failures.length === 10) return failures;
      }
      if (pending.length > 262144) break;
    }
  } catch { /* Missing or partial evidence must not hide the original failure. */ }
  return failures;
}
