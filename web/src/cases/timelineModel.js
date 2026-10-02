const terminal = new Set(['succeeded', 'failed', 'cancelled', 'skipped']);
export const formatTime = ms => !Number.isFinite(ms) ? 'Not recorded' : ms < 1000 ? `${ms.toFixed(0)} ms`
  : ms < 60000 ? `${(ms / 1000).toFixed(2)} s` : `${Math.floor(ms / 60000)}m ${((ms % 60000) / 1000).toFixed(1)}s`;
const epoch = value => value == null ? NaN : typeof value === 'number' ? (value < 1e12 ? value * 1000 : value) : Date.parse(value);

export function unionDuration(intervals) {
  let total = 0, end = -Infinity;
  for (const [a, b] of intervals.filter(([a, b]) => Number.isFinite(a) && b >= a).sort((a, b) => a[0] - b[0])) {
    total += Math.max(0, b - Math.max(a, end));
    end = Math.max(end, b);
  }
  return total;
}

export function makeTimeline(data, attempt = null) {
  const now = data?.observed_at_ms;
  const roots = (data?.operations || []).filter(s => s.kind === 'total' && s.source === 'host'
    && (!attempt?.attempt_id || !s.attempt_id || s.attempt_id === attempt.attempt_id));
  const hostClocks = new Set(roots.map(s => s.clock_id));
  const recoveryClocks = new Set(roots.filter(s => s.phase === 'recover').map(s => s.clock_id));
  const recoveryOnly = roots.length > 0 && roots.every(s => s.phase === 'recover');
  const closed = attempt?.status ? terminal.has(attempt.status) : Boolean(attempt?.finished_at) || terminal.has(data?.metadata?.status);
  const wallQueue = s => s.source === 'host' && s.clock_id === 'host-wall' && s.phase === 'judge'
    && s.kind === 'wait' && (!attempt?.attempt_id || s.attempt_id === attempt.attempt_id);
  const operations = (data?.operations || []).filter(s => s.source === 'host'
    ? hostClocks.has(s.clock_id) || wallQueue(s) : !recoveryOnly).map(row => {
    const fresh = Number.isFinite(now) && now - row.observed_at_ms < 15000 && now >= row.observed_at_ms;
    const status = row.status === 'running' && ((!recoveryClocks.has(row.clock_id) && closed) || !fresh) ? 'unconfirmed' : row.status;
    // Only persisted measurements advance the chart. A lost process never grows forever.
    return { ...row, status, attributes: row.attributes || {}, measured: true };
  });
  const host = operations.find(s => s.kind === 'total' && s.source === 'host');
  const container = operations.find(s => s.kind === 'container');
  for (const row of operations) if (row.kind === 'total' && row.source === 'worker') row.parent_id = container?.id || null;
  const invocation = new Map(operations.filter(s => s.attributes.invocation_id).map(s => [s.attributes.invocation_id, s.id]));
  const otel = (recoveryOnly ? [] : data?.spans || []).filter(s => s.start_time_unix_nano != null && Number.isFinite(Number(s.start_time_unix_nano)));
  const otelById = new Map(otel.map(s => [`${s.trace_id}:${s.span_id}`, s]));
  for (const s of otel) {
    const parent = `${s.trace_id}:${s.parent_span_id}`;
    const id = `${s.trace_id}:${s.span_id}`;
    const invocationId = invocation.get(s.attributes?.['abb.invocation_id']);
    const start = Number(s.start_time_unix_nano) / 1e6;
    const ended = s.end_time_unix_nano != null && s.end_time_unix_nano !== 'None' && Number.isFinite(Number(s.end_time_unix_nano));
    const end = ended ? Number(s.end_time_unix_nano) / 1e6 : start;
    // The existing abb.execute envelope includes evidence finalization; keep its
    // children but use the explicitly measured invocation as their display parent.
    if (s.name === 'abb.execute' && invocationId) continue;
    const parentSpan = otelById.get(parent);
    operations.push({ id, parent_id: parentSpan?.name === 'abb.execute' && invocationId ? invocationId
      : otelById.has(parent) ? parent : invocationId || null,
    name: s.name, kind: s.attributes?.['abb.kind'] || 'framework', source: 'otel',
    start_ms: start, end_ms: Math.max(start, end), duration_ms: ended ? Math.max(0, end - start) : null,
    status: !ended ? 'unconfirmed' : s.status?.status_code === 'ERROR' ? 'failed' : 'succeeded',
    attributes: s.attributes || {}, measured: ended });
  }
  const queued = epoch(attempt?.queued_at), dispatched = epoch(attempt?.started_at);
  const attemptEnd = !attempt?.status || terminal.has(attempt.status) ? epoch(attempt?.finished_at) : NaN;
  const lastHostEnd = roots.length ? Math.max(...roots.map(s => s.end_ms)) : NaN;
  if (host && Number.isFinite(dispatched) && host.start_ms - dispatched >= 1) operations.push({ id: 'before-evaluation',
    name: 'Dispatch / validation before evaluation', source: 'scheduler', kind: 'runtime',
    start_ms: dispatched, end_ms: host.start_ms, duration_ms: host.start_ms - dispatched, status: 'succeeded', attributes: {} });
  if (host && Number.isFinite(attemptEnd) && attemptEnd - lastHostEnd >= 1) operations.push({ id: 'after-evaluation',
    name: 'Result validation / completion', source: 'scheduler', kind: 'runtime',
    start_ms: lastHostEnd, end_ms: attemptEnd, duration_ms: attemptEnd - lastHostEnd, status: 'succeeded', attributes: {} });
  if (Number.isFinite(queued) && dispatched >= queued) operations.push({ id: 'schedule-queue', name: 'Wait for execution slot',
    source: 'scheduler', kind: 'wait', start_ms: queued, end_ms: dispatched, duration_ms: dispatched - queued,
    status: 'succeeded', attributes: {}, parent_id: null });
  const retryStart = epoch(attempt?.retry_wait_started_at), retryEnd = epoch(attempt?.retry_released_at);
  if (Number.isFinite(retryStart) && retryEnd >= retryStart) operations.push({ id: 'retry-wait', name: 'Retry backoff',
    source: 'scheduler', kind: 'wait', start_ms: retryStart, end_ms: retryEnd, duration_ms: retryEnd - retryStart,
    status: 'succeeded', attributes: {}, parent_id: null });
  const byId = new Map(operations.map(s => [s.id, s]));
  const children = new Map();
  for (const row of operations) {
    let cursor = byId.get(row.parent_id), seen = new Set([row.id]);
    while (cursor && !seen.has(cursor.id)) { seen.add(cursor.id); cursor = byId.get(cursor.parent_id); }
    if (cursor || !byId.has(row.parent_id)) row.parent_id = null;
    if (!children.has(row.parent_id)) children.set(row.parent_id, []);
    children.get(row.parent_id).push(row);
  }
  const rows = [];
  function visit(parent, depth) {
    for (const row of (children.get(parent) || []).sort((a, b) => a.start_ms - b.start_ms)) {
      const nested = children.get(row.id) || [];
      const comparable = nested.every(c => c.source === row.source || c.source === 'otel' && row.source === 'worker');
      const covered = unionDuration(nested.map(c => [Math.max(c.start_ms, row.start_ms), Math.min(c.end_ms, row.end_ms)]));
      rows.push({ ...row, depth, childIds: nested.map(c => c.id),
        self_ms: !comparable || !Number.isFinite(row.duration_ms) ? null : Math.max(0, row.duration_ms - covered) });
      visit(row.id, depth + 1);
    }
  }
  visit(null, 0);
  const start = rows.length ? Math.min(...rows.map(s => s.start_ms)) : null;
  const end = rows.length ? Math.max(...rows.map(s => s.end_ms)) : null;
  const kindDuration = (kind, source) => {
    const measured = rows.filter(s => s.kind === kind && (!source || s.source === source));
    return measured.length ? unionDuration(measured.map(s => [s.start_ms, s.end_ms])) : null;
  };
  const attemptTotal = Number.isFinite(dispatched) && attemptEnd >= dispatched ? attemptEnd - dispatched : null;
  const activeTotal = roots.length ? unionDuration([...roots, ...operations.filter(wallQueue)]
    .map(s => [s.start_ms, s.end_ms])) : null;
  return { rows, start, end, total_ms: attemptTotal ?? activeTotal,
    total_label: attemptTotal != null ? 'Attempt elapsed' : 'Recorded evaluation time', agent_ms: host ? kindDuration('agent') : null,
    sdk_ms: host ? kindDuration('sdk_wait') : null, running: rows.some(s => s.status === 'running'),
    phases: [{ label: 'Preparation', duration_ms: kindDuration('preparation', 'host') },
      { label: 'Container execution', duration_ms: kindDuration('container', 'host') },
      { label: 'Cleanup', duration_ms: kindDuration('cleanup', 'host') },
      ...(operations.some(s => s.phase === 'judge') ? [
        { label: 'Judge queue', duration_ms: unionDuration(operations.filter(wallQueue).map(s => [s.start_ms, s.end_ms])) },
        { label: 'Host Judge', duration_ms: kindDuration('judge', 'host') }] : [])],
    hasTimings: Boolean(host), warnings: data?.warnings || [] };
}
