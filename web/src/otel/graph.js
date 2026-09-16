import { traceTree } from './tree.js';

export function executionGraph(spans) {
  const nodes = [], edges = [];
  let row = 0;
  function visit(span, depth, parent) {
    const id = `${span.trace_id}:${span.span_id}`;
    const state = span.live ? 'Running' : span.status?.status_code === 'ERROR' ? 'Error' : 'Completed';
    nodes.push({ id, position: { x: depth * 280, y: row++ * 85 },
      data: { label: `${span.name}\n${state}`, span },
      className: span.live ? 'trajectory-live' : state === 'Error' ? 'trajectory-error' : '',
      sourcePosition: 'right', targetPosition: 'left' });
    if (parent) edges.push({ id: `${parent}>${id}`, source: parent, target: id,
      animated: Boolean(span.live), markerEnd: { type: 'arrowclosed' } });
    span.children.forEach(child => visit(child, depth + 1, id));
  }
  traceTree(spans).forEach(span => visit(span, 0, null));
  return { nodes, edges };
}
