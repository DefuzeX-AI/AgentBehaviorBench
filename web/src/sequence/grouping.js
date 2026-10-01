import { unionDuration } from '../cases/timelineModel.js';

const callKinds = new Set(['agent', 'llm', 'chat', 'tool', 'http', 'sdk_wait', 'generation']);

export function groupSummary(records) {
  const ids = new Set(records.map(r => r.id));
  const roots = records.filter(r => !ids.has(r.parent_id));
  const measured = roots.filter(r => Number.isFinite(r.duration_ms));
  const intervals = measured.map(r => [r.start_ms, r.start_ms + r.duration_ms]);
  const starts = records.map(r => r.start_ms).filter(Number.isFinite);
  const ends = records.map(r => r.end_ms ?? (r.start_ms != null ? r.start_ms + (r.duration_ms || 0) : null)).filter(Number.isFinite);
  return { start_ms: starts.length ? Math.min(...starts) : null, end_ms: ends.length ? Math.max(...ends) : null,
    duration_ms: measured.length ? unionDuration(intervals) : null,
    incomplete: roots.some(r => !Number.isFinite(r.duration_ms)),
    status: ['running', 'pending', 'failed', 'unconfirmed', 'cancelled'].find(s => records.some(r => r.status === s)) || 'succeeded',
    recordIds: records.map(r => r.id), count: records.length };
}

/** Group by recorded ownership and tree structure, never by operation names. */
export function groupTimings(records) {
  const byId = new Map(records.map(r => [r.id, r]));
  const containers = records.filter(r => r.source === 'host' && r.kind === 'container');
  const agents = records.filter(r => r.kind === 'agent');
  const inputOwners = new Map();
  for (const row of agents) {
    const input = row.attributes?.input_id;
    if (input) inputOwners.set(input, [...(inputOwners.get(input) || []), row]);
  }
  function ancestor(row, predicate) {
    const seen = new Set();
    while (row && !seen.has(row.id)) {
      if (predicate(row)) return row;
      seen.add(row.id); row = byId.get(row.parent_id);
    }
    return null;
  }
  const buckets = new Map();
  function add(id, title, type, row) {
    if (!buckets.has(id)) buckets.set(id, { id, title, type, members: [] });
    buckets.get(id).members.push(row);
  }
  for (const row of records) {
    if (row.source === 'host' && row.phase === 'recover') {
      add(`recovery:${row.clock_id}`, 'Judge recovery', 'stage', row);
      continue;
    }
    if (row.kind === 'total' || row.kind === 'container' || row.kind === 'case') continue;
    if (row.source === 'host' || row.source === 'scheduler') {
      const container = containers.find(c => c.clock_id === row.clock_id) || containers[0];
      const after = ancestor(row, r => r.kind === 'cleanup') || container && row.start_ms >= container.end_ms;
      add(after ? 'completion' : 'environment', after ? 'Validation & cleanup' : 'Environment & Docker', 'stage', row);
      continue;
    }
    const agent = ancestor(row, r => r.kind === 'agent');
    const input = row.attributes?.input_id || row.attributes?.['abb.input_id'];
    const owners = inputOwners.get(input) || [];
    const owner = agent || (owners.length === 1 ? owners[0] : null);
    if (owner) {
      add(`input:${owner.id}`, `Input ${agents.indexOf(owner) + 1}`, 'calls', row);
    } else if (row.source === 'otel') {
      add('other-calls', 'Other recorded calls', 'calls', row);
    } else {
      add('sdk-work', 'SDK setup & bookkeeping', 'stage', row);
    }
  }
  const groups = [...buckets.values()].map(group => {
    const summary = groupSummary(group.members);
    const calls = group.members.filter(r => callKinds.has(r.kind));
    // Older runs may contain framework calls without typed LLM/tool spans.
    const visible = calls.length ? calls : group.members.filter(r => !group.members.some(p => p.id === r.parent_id));
    return { ...group, ...summary, records: group.type === 'calls' ? visible : [],
      inspect: { group: group.id }, acrossRun: group.id === 'sdk-work' };
  });
  const executionRecords = records.filter(r => r.source !== 'host' && r.source !== 'scheduler' || r.kind === 'container');
  const execution = { id: 'execution', title: 'Execution', ...groupSummary(executionRecords), inspect: { group: 'execution' } };
  return { groups: groups.sort((a, b) => (a.start_ms ?? Infinity) - (b.start_ms ?? Infinity)), execution };
}

export function detailTree(records) {
  const ids = new Set(records.map(row => row.id));
  const children = new Map();
  for (const row of records) {
    const parent = ids.has(row.parent_id) ? row.parent_id : null;
    if (!children.has(parent)) children.set(parent, []);
    children.get(parent).push(row);
  }
  const build = (parent, seen) => (children.get(parent) || []).map(row => ({ key: row.id, row,
    children: seen.has(row.id) ? [] : build(row.id, new Set([...seen, row.id])) }));
  return build(null, new Set());
}
