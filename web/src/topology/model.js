const kinds = new Set(['case', 'agent', 'llm', 'chat', 'tool', 'http', 'sdk_wait', 'generation']);
const active = new Set(['running', 'pending', 'unconfirmed']);

function participant(row) {
  if (!kinds.has(row.kind) || ['host', 'scheduler'].includes(row.source)) return null;
  const kind = row.kind === 'chat' ? 'llm' : row.kind;
  const title = kind === 'case' ? 'Case runner' : kind === 'agent' ? 'Agent'
    : kind === 'sdk_wait' ? 'SDK submit / wait' : row.name || kind;
  // Keep distinct recorded models separate without using invocation IDs or prompt data.
  const model = kind === 'llm' ? row.attributes?.['gen_ai.request.model'] || row.attributes?.['gen_ai.response.model'] : null;
  return { id: `topology:${JSON.stringify([kind, title, model || null])}`, kind, title, model };
}

function summary(rows) {
  const measured = rows.filter(r => Number.isFinite(r.duration_ms));
  return { count: rows.length, recordIds: rows.map(r => r.id),
    duration_ms: measured.length ? measured.reduce((sum, r) => sum + r.duration_ms, 0) : null,
    missing: rows.length - measured.length,
    failed: rows.filter(r => r.status === 'failed').length,
    unfinished: rows.filter(r => active.has(r.status)).length };
}

function provenParent(child, parent) {
  if (child.source === parent.source) {
    return !(child.clock_id && parent.clock_id && child.clock_id !== parent.clock_id);
  }
  return child.source === 'otel' && parent.source === 'worker'
    && Boolean(child.attributes?.['abb.invocation_id'])
    && child.attributes['abb.invocation_id'] === parent.attributes?.invocation_id;
}

/** Aggregate participants using recorded ancestry, never timestamps or lane proximity. */
export function buildTopology(records) {
  const byId = new Map(records.map(row => [row.id, row]));
  const owners = new Map(), buckets = new Map(), connections = new Map();
  for (const row of byId.values()) {
    const entity = participant(row);
    if (!entity) continue;
    owners.set(row.id, entity.id);
    if (!buckets.has(entity.id)) buckets.set(entity.id, { ...entity, rows: [] });
    buckets.get(entity.id).rows.push(row);
  }
  for (const row of byId.values()) {
    const target = owners.get(row.id);
    if (!target) continue;
    let cursor = row;
    const seen = new Set([row.id]);
    while (cursor.parent_id && !seen.has(cursor.parent_id)) {
      const parent = byId.get(cursor.parent_id);
      if (!parent || !provenParent(cursor, parent)) break;
      seen.add(parent.id);
      const source = owners.get(parent.id);
      if (source) {
        const id = `topology-edge:${JSON.stringify([source, target])}`;
        if (!connections.has(id)) connections.set(id, { id, source, target, rows: [] });
        connections.get(id).rows.push(row);
        break;
      }
      cursor = parent;
    }
  }
  const nodes = [...buckets.values()].map(({ rows, ...entity }) => ({ ...entity, ...summary(rows) }));
  const byNode = new Map(nodes.map(node => [node.id, node]));
  const edges = [...connections.values()].map(({ rows, ...edge }) => ({ ...edge,
    title: `${byNode.get(edge.source).title} → ${byNode.get(edge.target).title}`, ...summary(rows) }));
  return { nodes, edges };
}

/** A stable layered layout, including disconnected participants and cyclic calls. */
export function topologyPositions(nodes, edges) {
  const ordered = [...nodes].sort((a, b) => a.id.localeCompare(b.id));
  const incoming = new Set(edges.filter(e => e.source !== e.target).map(e => e.target));
  const outgoing = new Map(nodes.map(n => [n.id, []]));
  edges.forEach(e => outgoing.get(e.source)?.push(e.target));
  const depth = new Map();
  function walk(root) {
    if (depth.has(root.id)) return;
    depth.set(root.id, 0);
    const queue = [root.id];
    for (let i = 0; i < queue.length; i++) {
      for (const target of outgoing.get(queue[i]) || []) {
        if (depth.has(target)) continue;
        depth.set(target, depth.get(queue[i]) + 1); queue.push(target);
      }
    }
  }
  ordered.filter(n => !incoming.has(n.id)).forEach(walk);
  ordered.forEach(walk);
  const levels = new Map();
  ordered.forEach(node => { const d = depth.get(node.id); if (!levels.has(d)) levels.set(d, []); levels.get(d).push(node); });
  const height = Math.max(1, ...[...levels.values()].map(level => level.length));
  const positions = new Map();
  for (const [d, level] of levels) level.forEach((node, index) => positions.set(node.id,
    { x: d * 390, y: (index + (height - level.length) / 2) * 190 }));
  return positions;
}
