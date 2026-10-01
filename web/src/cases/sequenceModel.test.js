import test from 'node:test';
import assert from 'node:assert/strict';
import { interactionSequence, sequenceScale, timingSequence } from '../sequence/model.js';

test('sequence keeps real durations, start order and SDK wait call relationships', () => {
  const rows = [
    { id: 'case', kind: 'case', source: 'worker', start_ms: 1000, duration_ms: 500, depth: 1 },
    { id: 'wait', parent_id: 'case', kind: 'sdk_wait', source: 'worker', start_ms: 1300, duration_ms: 200, depth: 2, status: 'running' },
    { id: 'agent', parent_id: 'case', kind: 'agent', source: 'worker', start_ms: 1000, duration_ms: 300, depth: 2, status: 'succeeded' },
  ];
  const records = timingSequence({ rows });
  assert.deepEqual(records.map(r => r.id), ['case', 'agent', 'wait']);
  assert.equal(records[2].fromLane, 2);
  assert.equal(records[2].lane, 1);
  assert.equal(records[2].duration_ms, 200);
  assert.equal(records[2].endKnown, false);
  assert.equal(records[0].primary, false);
  assert.deepEqual(sequenceScale(records), { origin: 1000, duration: 500 });
});

test('cross-process placement does not fabricate a call; explicit invocation links do', () => {
  const rows = [
    { id: 'host', kind: 'container', source: 'host', start_ms: 0 },
    { id: 'worker', kind: 'total', source: 'worker', parent_id: 'host', start_ms: 10 },
    { id: 'invoke', kind: 'execution', source: 'worker', parent_id: 'worker', start_ms: 20, attributes: { invocation_id: 'i' } },
    { id: 'llm', kind: 'llm', source: 'otel', parent_id: 'invoke', start_ms: 30, attributes: { 'abb.invocation_id': 'i' } },
    { id: 'missing', kind: 'llm', source: 'otel', parent_id: 'invoke', start_ms: 30 },
  ];
  const records = timingSequence({ rows });
  assert.equal(records.find(r => r.id === 'worker').fromLane, null);
  assert.equal(records.find(r => r.id === 'llm').fromLane, 2);
  assert.equal(records.find(r => r.id === 'missing').fromLane, null);
});

test('legacy evidence uses recorded links and never substitutes file time for event time', () => {
  const rows = [
    { id: 'snapshot', kind: 'case', timestamp: '2026-01-01T00:00:00Z', time_basis: 'file_mtime' },
    { id: 'chat', kind: 'chat', timestamp: '2026-01-01T00:00:00Z', duration_ms: 1200, status: 'complete', link_evidence: 'framework_span_id' },
    { id: 'unlinked', kind: 'chat', timestamp: '2026-01-01T00:00:01Z', duration_ms: 900, status: 'pending' },
  ];
  const records = interactionSequence(rows, { attached: new Set(['chat']) });
  assert.equal(records[0].start_ms, null);
  assert.equal(records[0].duration_ms, null);
  assert.equal(records[1].fromLane, 2);
  assert.equal(records[1].endKnown, true);
  assert.equal(records[2].fromLane, null);
  assert.equal(records[2].endKnown, false);
  assert.equal(sequenceScale(records).duration, 1900);
});
