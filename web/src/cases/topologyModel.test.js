import test from 'node:test';
import assert from 'node:assert/strict';
import { buildTopology, topologyPositions } from '../topology/model.js';

const row = (id, kind, parent_id, extra = {}) => ({ id, kind, parent_id, name: kind, source: 'worker', status: 'succeeded', duration_ms: 10, ...extra });

test('topology aggregates repeated calls and follows framework ancestry to the actual caller', () => {
  const records = [row('case', 'case'), row('a1', 'agent', 'case'), row('a2', 'agent', 'case'),
    row('invoke1', 'execution', 'a1', { attributes: { invocation_id: 'one' } }),
    row('invoke2', 'execution', 'a2', { attributes: { invocation_id: 'two' } }),
    row('l1', 'llm', 'invoke1', { name: 'Chat', source: 'otel', duration_ms: 30, attributes: { 'abb.invocation_id': 'one' } }),
    row('l2', 'llm', 'invoke2', { name: 'Chat', source: 'otel', duration_ms: 50, attributes: { 'abb.invocation_id': 'two' } }),
    row('wait', 'sdk_wait', 'case')];
  const graph = buildTopology(records);
  assert.equal(graph.nodes.length, 4);
  const agent = graph.nodes.find(n => n.kind === 'agent'), llm = graph.nodes.find(n => n.kind === 'llm');
  assert.equal(agent.count, 2);
  assert.equal(llm.count, 2);
  assert.equal(llm.duration_ms, 80);
  const link = graph.edges.find(e => e.source === agent.id && e.target === llm.id);
  assert.deepEqual(link.recordIds, ['l1', 'l2']);
  assert.equal(link.duration_ms, 80);
  assert.equal(graph.edges.length, 3);
  assert.equal(graph.edges.find(e => e.target === graph.nodes.find(n => n.kind === 'sdk_wait').id).source,
    graph.nodes.find(n => n.kind === 'case').id);
});

test('missing ancestry, cross-process placement and clock mismatches never invent edges', () => {
  const graph = buildTopology([row('a', 'agent', null, { clock_id: 'one' }),
    row('b', 'tool', 'a', { clock_id: 'two' }), row('c', 'llm', 'a', { source: 'otel' }),
    row('d', 'http', 'missing'), row('e', 'case', null, { source: 'host' })]);
  assert.equal(graph.nodes.length, 4);
  assert.equal(graph.edges.length, 0);
});

test('missing durations, failures, unfinished calls and different models remain distinct', () => {
  const graph = buildTopology([row('a', 'llm', null, { duration_ms: null, status: 'unconfirmed', attributes: { 'gen_ai.request.model': 'm1' } }),
    row('b', 'llm', null, { duration_ms: 0, status: 'failed', attributes: { 'gen_ai.request.model': 'm2' } })]);
  assert.equal(graph.nodes.length, 2);
  assert.equal(graph.nodes[0].duration_ms, null);
  assert.equal(graph.nodes[0].missing, 1);
  assert.equal(graph.nodes[0].unfinished, 1);
  assert.equal(graph.nodes[1].duration_ms, 0);
  assert.equal(graph.nodes[1].failed, 1);
});

test('cycles, recursion and disconnected participants have stable finite positions', () => {
  const graph = buildTopology([row('a', 'tool', 'b', { name: 'search' }), row('b', 'tool', 'a', { name: 'lookup' }),
    row('c', 'tool', 'a', { name: 'search' }), row('d', 'llm', null)]);
  assert.ok(graph.edges.some(e => e.source === e.target));
  const positions = topologyPositions(graph.nodes, graph.edges);
  assert.equal(positions.size, 3);
  assert.deepEqual(topologyPositions([...graph.nodes].reverse(), graph.edges), positions);
  assert.ok([...positions.values()].every(p => Number.isFinite(p.x) && Number.isFinite(p.y)));
  assert.deepEqual(buildTopology([]), { nodes: [], edges: [] });
});
