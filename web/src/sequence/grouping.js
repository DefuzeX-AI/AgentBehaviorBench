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

/** Fold real operation subtrees, without synthetic environment/SDK buckets. */
export function groupOperations(records) {
  const byId = new Map(records.map(row => [row.id, row]));
  const envelopes = new Set(['total', 'container', 'case']);
  const buckets = new Map();
  for (const row of records) {
    if (envelopes.has(row.kind)) continue;
    let root = row;
    const seen = new Set([row.id]);
    let parent = byId.get(root.parent_id);
    while (parent && !envelopes.has(parent.kind) && !seen.has(parent.id)) {
      seen.add(parent.id);
      root = parent;
      parent = byId.get(root.parent_id);
    }
    const id = `operation:${root.id}`;
    if (!buckets.has(id)) buckets.set(id, { id, title: root.name, root, members: [] });
    buckets.get(id).members.push(row);
  }
  const groups = [...buckets.values()].map(group => {
    const calls = group.members.filter(row => callKinds.has(row.kind));
    const summary = groupSummary(group.members);
    return { ...group, ...summary, type: calls.length ? 'calls' : 'stage',
      inputId: group.root.attributes?.input_id || group.root.attributes?.['abb.input_id'],
      records: calls.sort((a, b) => a.start_ms - b.start_ms),
      basis: group.members.length > 1 ? 'Recorded parent and children' : 'Recorded operation',
      inspect: { group: group.id } };
  }).sort((a, b) => (a.start_ms ?? Infinity) - (b.start_ms ?? Infinity));
  const executionRecords = records.filter(row => row.source !== 'host' && row.source !== 'scheduler' || row.kind === 'container');
  const execution = { id: 'execution', title: 'Execution', ...groupSummary(executionRecords), inspect: { group: 'execution' } };
  return { groups, execution };
}

const inputKey = group => group.inputId ? JSON.stringify([group.root.phase ?? null, group.inputId]) : null;

/** Presentation groups use explicit Input IDs; original operation ancestry is retained. */
export function groupTimings(records) {
  const { groups: operations, execution } = groupOperations(records);
  const owners = new Map();
  for (const group of operations) {
    const key = inputKey(group);
    if (key && group.members.some(row => row.kind === 'agent')) {
      if (!owners.has(key)) owners.set(key, []);
      owners.get(key).push(group);
    }
  }
  const buckets = new Map();
  for (const operation of operations) {
    const candidates = owners.get(inputKey(operation));
    const owner = operation.type === 'calls' && candidates?.length === 1 ? candidates[0] : operation;
    if (!buckets.has(owner.id)) buckets.set(owner.id, { owner, operations: [] });
    buckets.get(owner.id).operations.push(operation);
  }
  const groups = [...buckets.values()].map(({ owner, operations: children }) => {
    const members = children.flatMap(group => group.members);
    return { ...owner, ...groupSummary(members), members, operations: children,
      title: owner.inputId && owner.members.some(row => row.kind === 'agent') ? `Input · ${owner.inputId}` : owner.title,
      records: children.flatMap(group => group.records).sort((a, b) => a.start_ms - b.start_ms),
      basis: children.length > 1 ? 'Recorded Input ID; original parents preserved' : owner.basis };
  }).sort((a, b) => (a.start_ms ?? Infinity) - (b.start_ms ?? Infinity));
  // Collapse only the consecutive non-call prefix/suffix, never the operations between calls.
  const first = groups.findIndex(group => group.type === 'calls');
  if (first >= 0) {
    const lastCallStart = Math.max(...groups.flatMap(group => group.records).map(row => row.start_ms ?? -Infinity));
    const trailing = groups.findIndex((group, index) => index > first && group.type === 'stage' && group.start_ms > lastCallStart);
    const suffix = trailing < 0 ? groups.length : trailing;
    const fold = (items, id, title) => {
      if (!items.length) return [];
      const members = items.flatMap(group => group.members);
      return [{ id, title, type: 'stage', members, records: [], operations: items,
        ...groupSummary(members), basis: 'Recorded operations; open for details', inspect: { group: id } }];
    };
    return { groups: [...fold(groups.slice(0, first), 'sequence:before', 'Before first action'),
      ...groups.slice(first, suffix), ...fold(groups.slice(suffix), 'sequence:after', 'Finishing steps')], operations, execution };
  }
  return { groups, operations, execution };
}

/** One chronological canvas, even when an Input's calls surround independent bookkeeping. */
export function sequenceEntries(groups) {
  const entries = groups.flatMap(group => group.type === 'calls'
    ? group.records.map(row => ({ id: row.id, start_ms: row.start_ms, row, group }))
    : [{ id: group.id, start_ms: group.start_ms, group }])
    .sort((a, b) => (a.start_ms ?? Infinity) - (b.start_ms ?? Infinity));
  const first = new Map(), last = new Map();
  entries.forEach((entry, index) => {
    if (entry.row) {
      if (!first.has(entry.group.id)) first.set(entry.group.id, index);
      last.set(entry.group.id, index);
    }
  });
  return entries.map((entry, index) => ({ ...entry,
    heading: first.get(entry.group.id) === index, footer: !entry.row || last.get(entry.group.id) === index }));
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
