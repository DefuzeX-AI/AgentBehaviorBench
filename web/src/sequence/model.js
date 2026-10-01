export const timingLanes = ['Runtime', 'SDK / Judge', 'Agent / framework', 'LLM', 'Tools / HTTP'];

export function timingLane(row) {
  if (row.kind === 'llm' || row.kind === 'chat') return 3;
  if (row.kind === 'tool' || row.kind === 'http') return 4;
  if (['sdk_wait', 'sdk', 'generation'].includes(row.kind)) return 1;
  if (row.source === 'otel' || ['agent', 'execution', 'case', 'input'].includes(row.kind)) return 2;
  return row.source === 'worker' ? 2 : 0;
}

export function timingSequence(model) {
  const byId = new Map(model.rows.map(row => [row.id, row]));
  return model.rows.map(row => {
    const lane = timingLane(row);
    let parent = byId.get(row.parent_id);
    // Enclosing totals and cross-process placement are not call evidence.
    while (parent && timingLane(parent) === lane && parent.source === row.source) parent = byId.get(parent.parent_id);
    const invocationLink = row.source === 'otel' && parent?.source === 'worker'
      && row.attributes?.['abb.invocation_id'] && row.attributes['abb.invocation_id'] === parent.attributes?.invocation_id;
    const linked = parent && parent.kind !== 'total' && (parent.source === row.source || invocationLink);
    return { ...row, title: row.name, lane, fromLane: linked ? timingLane(parent) : null,
      linkLabel: linked ? 'Parent call' : null,
      endKnown: !['running', 'unconfirmed'].includes(row.status),
      primary: !['total', 'container', 'case', 'execution', 'framework'].includes(row.kind),
      inspect: { timing: row },
    };
  }).sort((a, b) => a.start_ms - b.start_ms || a.depth - b.depth);
}

export function interactionSequence(rows, model) {
  return rows.map(row => {
    const lane = row.kind === 'chat' ? 3 : ['tool', 'http'].includes(row.kind) ? 4 : ['input', 'output'].includes(row.kind) ? 2 : 1;
    const linked = model.attached.has(row.id) && (row.kind === 'tool'
      || ['chat', 'http'].includes(row.kind) && row.link_evidence === 'framework_span_id');
    const timestamp = row.time_basis === 'file_mtime' ? NaN : Date.parse(row.timestamp);
    return { id: row.id, title: row.title, kind: row.kind, lane, fromLane: linked ? 2 : null,
      start_ms: Number.isFinite(timestamp) ? timestamp : null, duration_ms: row.duration_ms ?? null,
      status: row.status, endKnown: row.status === 'complete',
      linkLabel: linked ? 'Request' : null, inspect: { row },
      primary: row.kind !== 'http',
    };
  });
}

export function sequenceScale(records, start, end) {
  const starts = records.map(row => row.start_ms).filter(Number.isFinite);
  const ends = records.filter(row => Number.isFinite(row.start_ms)).map(row => row.start_ms + (row.duration_ms || 0));
  const origin = start ?? (starts.length ? Math.min(...starts) : null);
  const finish = end ?? (ends.length ? Math.max(...ends) : null);
  return { origin, duration: origin != null && finish != null ? Math.max(0, finish - origin) : null };
}
