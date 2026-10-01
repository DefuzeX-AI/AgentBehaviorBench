import test from 'node:test';
import assert from 'node:assert/strict';
import { detailTree, groupSummary, groupTimings } from '../sequence/grouping.js';
import { timingSequence } from '../sequence/model.js';

const row = (id, kind, start, duration, parent_id, source = 'host', attributes = {}) => ({
  id, name: id, kind, start_ms: start, end_ms: start + duration, duration_ms: duration,
  parent_id, source, attributes, status: 'succeeded', clock_id: source, depth: 0,
});

test('Docker preparation is one stage; nested image and build time is counted once', () => {
  const rows = [row('total', 'total', 0, 10000), row('queue', 'wait', 0, 10, null, 'scheduler'),
    row('overlay', 'preparation', 10, 90, 'total'), row('docker', 'preparation', 100, 6900, 'total'),
    row('image', 'image', 200, 2200, 'docker'), row('fingerprint', 'preparation', 200, 2160, 'image'),
    row('build', 'build', 2400, 1100, 'docker'), row('container', 'container', 7000, 2900, 'total'),
    row('cleanup', 'cleanup', 9900, 100, 'total')];
  const { groups } = groupTimings(timingSequence({ rows }));
  const environment = groups.find(g => g.id === 'environment');
  assert.equal(environment.duration_ms, 7000);
  assert.equal(environment.recordIds.length, 6);
  assert.deepEqual(environment.records, []);
  const tree = detailTree(environment.members);
  assert.equal(tree.find(n => n.key === 'docker').children[0].children[0].key, 'fingerprint');
  assert.equal(groups.find(g => g.id === 'completion').duration_ms, 100);
});

test('Input grouping uses identity and ancestry, preserving the complete hidden framework tree', () => {
  const rows = [row('total', 'total', 0, 1000), row('container', 'container', 0, 1000, 'total'),
    row('worker', 'total', 10, 980, 'container', 'worker'), row('case', 'case', 20, 900, 'worker', 'worker'),
    row('agent', 'agent', 30, 600, 'case', 'worker', { input_id: 'input-a' }),
    row('invoke', 'execution', 35, 590, 'agent', 'worker'), row('wrapper', 'chain', 40, 500, 'invoke', 'otel'),
    row('llm', 'llm', 50, 400, 'wrapper', 'otel'),
    row('submit', 'sdk_wait', 630, 200, 'case', 'worker', { input_id: 'input-a' }),
    row('flush', 'evidence', 620, 5, 'case', 'worker')];
  const { groups, execution } = groupTimings(timingSequence({ rows }));
  const input = groups.find(g => g.type === 'calls');
  assert.deepEqual(input.records.map(r => r.id), ['agent', 'llm', 'submit']);
  assert.ok(input.recordIds.includes('wrapper'));
  assert.equal(input.duration_ms, 800);
  assert.equal(execution.duration_ms, 1000);
  assert.deepEqual(groups.find(g => g.id === 'sdk-work').recordIds, ['flush']);
});

test('concurrent Inputs do not merge by proximity, and ambiguous identifiers remain separate', () => {
  const rows = [row('a', 'agent', 10, 100, null, 'worker', { input_id: 'shared' }),
    row('b', 'agent', 20, 100, null, 'worker', { input_id: 'shared' }),
    row('wait', 'sdk_wait', 110, 10, null, 'worker', { input_id: 'shared' })];
  const { groups } = groupTimings(timingSequence({ rows }));
  assert.equal(groups.filter(g => g.type === 'calls').length, 2);
  assert.deepEqual(groups.find(g => g.id === 'sdk-work').recordIds, ['wait']);
});

test('unfinished stages and recovery keep their own state and measurements', () => {
  const unfinished = { ...row('docker', 'preparation', 0, 50), status: 'unconfirmed' };
  const recovery = { ...row('recovery', 'total', 500, 100), phase: 'recover', clock_id: 'recovery' };
  const wait = { ...row('wait', 'sdk_wait', 510, 50, 'recovery'), phase: 'recover', clock_id: 'recovery' };
  const { groups } = groupTimings(timingSequence({ rows: [unfinished, recovery, wait] }));
  assert.equal(groups[0].status, 'unconfirmed');
  assert.equal(groups[1].title, 'Judge recovery');
  assert.equal(groups[1].duration_ms, 100);
  assert.equal(groupSummary([{ ...unfinished, duration_ms: null }]).duration_ms, null);
});
