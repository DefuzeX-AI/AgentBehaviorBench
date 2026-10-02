export const replayTime = value => value == null ? NaN : typeof value === 'number' ? value : Date.parse(value);

export function replayModel(rows = [], archive = {}) {
  const mappedInputs = new Set(rows.filter(row => row.artifact_file?.endsWith('/mapped-input.json'))
    .map(row => row.artifact_file.replace(/mapped-input\.json$/, 'request.json')));
  const events = rows.filter(row => ['input', 'output', 'chat', 'tool', 'tool_call', 'http', 'judge'].includes(row.kind)
    && !mappedInputs.has(row.artifact_file))
    .map(row => ({ ...row, time: replayTime(row.timestamp), end: replayTime(row.ended), source: 'interaction' }))
    .filter(row => Number.isFinite(row.time));
  for (const event of archive.events || []) events.push({ id: `file:${event.sequence}`, kind: 'file',
    title: `${event.changes.length} file changes · ${event.reason}`, time: event.time_ms, source: 'file', event });
  events.sort((a, b) => a.time - b.time || a.id.localeCompare(b.id));
  const points = [...new Set([archive.baseline?.time_ms, ...events.flatMap(e => [e.time, e.end])]
    .filter(Number.isFinite))].sort((a, b) => a - b);
  return { events, points, start: points[0] ?? 0, end: points.at(-1) ?? 0 };
}

export function filesAt(archive, time) {
  const entries = new Map();
  if (archive.baseline && archive.baseline.time_ms <= time)
    for (const [path, value] of Object.entries(archive.baseline.entries)) entries.set(path, value);
  for (const event of archive.events || []) {
    if (event.time_ms > time) continue;
    for (const change of event.changes) {
      if (change.after == null) entries.delete(change.path);
      else entries.set(change.path, change.after);
    }
  }
  return [...entries].sort(([a], [b]) => a.localeCompare(b));
}

export function stateAt(event, time) {
  if (event.time > time) return 'future';
  if (Number.isFinite(event.end) && event.end > time) return 'running';
  if (!Number.isFinite(event.end) && ['chat', 'tool', 'tool_call', 'http'].includes(event.kind)) return 'No recorded end';
  return event.status || 'recorded';
}

export function nextPosition(points, current, direction) {
  return direction > 0 ? points.find(point => point > current) ?? points.at(-1) ?? current
    : [...points].reverse().find(point => point < current) ?? points[0] ?? current;
}

export function advancePosition(model, current, elapsed, skipWait) {
  let next = Math.min(model.end, current + elapsed);
  const upcoming = model.points.find(point => point > next);
  if (skipWait && upcoming != null && upcoming - next > 2000) next = upcoming;
  return next;
}
