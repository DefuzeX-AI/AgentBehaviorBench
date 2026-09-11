export function traceTree(spans) {
  const nodes = new Map(spans.map(span => [`${span.trace_id}:${span.span_id}`, { ...span, children: [] }]));
  const roots = [];
  for (const node of nodes.values()) {
    const parent = nodes.get(`${node.trace_id}:${node.parent_span_id}`);
    // Guard corrupted cycles; malformed spans remain inspectable at root.
    let cursor = parent;
    const seen = new Set([node]);
    while (cursor && !seen.has(cursor)) {
      seen.add(cursor);
      cursor = nodes.get(`${cursor.trace_id}:${cursor.parent_span_id}`);
    }
    if (parent && !cursor) parent.children.push(node);
    else roots.push(node);
  }
  return roots;
}

export function duration(span) {
  try { return Number(BigInt(span.end_time_unix_nano) - BigInt(span.start_time_unix_nano)) / 1e6; }
  catch { return null; }
}
