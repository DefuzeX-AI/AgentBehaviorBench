// Read-only prototype: collapse framework wrappers structurally, never by Agent name.
export const kinds = { chat: 'Chat', tool: 'Tool', http: 'HTTP', sdk: 'SDK', case: 'Case', input: 'Input', output: 'Output', submission: 'Submission', judge: 'Judge', span: 'Call' };
export const inputKey = r => r.input_id ? JSON.stringify([r.case_id, r.input_id]) : '';
export const spanKey = s => `${s.invocation}:${s.trace_id}:${s.span_id}`;
export const time = value => value ? new Date(value).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3, hour12: false }) : 'No timestamp';
export const elapsed = value => value == null ? '—' : value < 1000 ? `${Math.round(value)} ms` : `${(value / 1000).toFixed(2)} s`;
export const statusText = value => ({ complete: 'Completed', recorded: 'Recorded', failed: 'Error', pending: 'Waiting for response', unknown: 'Insufficient information' }[value] || value);

export function makeModel(rows, spans) {
  const inputGroups = new Map();
  for (const row of rows) if (inputKey(row) && !inputGroups.has(inputKey(row))) inputGroups.set(inputKey(row), { key: inputKey(row), label: row.input_id, caseId: row.case_id });
  const nodes = new Map(spans.map(s => [spanKey(s), { id: spanKey(s), span: s, children: [], rows: [] }]));
  const framework = new Map();
  for (const n of nodes.values()) {
    const f = n.span.attributes?.['abb.framework_span_id'];
    if (f) framework.set(f, [...(framework.get(f) || []), n]);
  }
  const attached = new Set();
  for (const row of rows) {
    const matches = framework.get(row.framework_span_id) || [];
    if (matches.length === 1) { matches[0].rows.push(row); attached.add(row.id); }
  }
  const invocationInputs = new Map();
  for (const n of nodes.values()) for (const row of n.rows) if (inputKey(row)) {
    const found = invocationInputs.get(n.span.invocation) || new Set();
    found.add(inputKey(row)); invocationInputs.set(n.span.invocation, found);
  }
  const roots = [];
  for (const n of nodes.values()) {
    const parentId = `${n.span.invocation}:${n.span.trace_id}:${n.span.parent_span_id}`;
    const parent = nodes.get(parentId);
    let cursor = parent, cycle = false; const seen = new Set([n.id]);
    while (cursor) {
      if (seen.has(cursor.id)) { cycle = true; break; }
      seen.add(cursor.id);
      cursor = nodes.get(`${cursor.span.invocation}:${cursor.span.trace_id}:${cursor.span.parent_span_id}`);
    }
    if (parent && !cycle) { n.parent = parent; parent.children.push(n); } else roots.push(n);
    const inputs = invocationInputs.get(n.span.invocation);
    const explicit = inputKey({ input_id: n.span.attributes?.['abb.input_id'], case_id: n.span.attributes?.['abb.case_id'] });
    n.inputKey = explicit || (inputs?.size === 1 ? [...inputs][0] : '');
  }
  for (const n of nodes.values()) n.children.sort((a, b) => String(a.span.start_time).localeCompare(String(b.span.start_time)));
  return { rows, nodes, roots, attached, inputs: [...inputGroups.values()] };
}

export function descendants(node) {
  return [node, ...node.children.flatMap(descendants)];
}

export function branches(node) {
  return node.children.map(child => {
    let target = child; const via = [];
    while (!target.rows.length && target.children.length === 1) { via.push(target); target = target.children[0]; }
    return { target, via };
  });
}

export function metrics(node) {
  const all = descendants(node), rows = all.flatMap(n => n.rows);
  return { spans: all.length, chats: rows.filter(r => r.kind === 'chat').length, tools: all.filter(n => n.span.attributes?.['abb.kind'] === 'tool').length };
}

export function spanKind(node) {
  return node.rows[0]?.kind || (node.span.attributes?.['abb.kind'] === 'llm' ? 'chat' : node.span.attributes?.['abb.kind'] === 'tool' ? 'tool' : 'span');
}
