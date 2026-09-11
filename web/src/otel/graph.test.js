import test from 'node:test';
import assert from 'node:assert/strict';
import { executionGraph } from './graph.js';
test('graph keeps parallel siblings and stable identities across live updates', () => {
  const spans = [{ trace_id: 't', span_id: 'r', name: 'root', live: true },
    { trace_id: 't', span_id: 'a', parent_span_id: 'r', name: 'a', live: true },
    { trace_id: 't', span_id: 'b', parent_span_id: 'r', name: 'b' }];
  const graph = executionGraph(spans);
  assert.equal(graph.nodes.length, 3);
  assert.deepEqual(graph.edges.map(e => e.source), ['t:r', 't:r']);
  assert.equal(graph.edges[0].animated, true);
  const finished = executionGraph(spans.map(s => ({ ...s, live: false })));
  assert.deepEqual(finished.nodes.map(n => n.id), graph.nodes.map(n => n.id));
  assert.equal(finished.edges[0].animated, false);
});
