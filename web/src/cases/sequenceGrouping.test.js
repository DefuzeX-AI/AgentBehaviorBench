import test from 'node:test';
import assert from 'node:assert/strict';
import { detailTree, groupSummary, groupOperations, groupTimings, sequenceEntries } from '../sequence/grouping.js';
import { timingSequence } from '../sequence/model.js';
import { fileSnapshots, placeFileSnapshots } from '../files/fileChangesModel.js';

const row = (id, kind, start, duration, parent_id, source = 'host', attributes = {}) => ({
  id, name: id, kind, start_ms: start, end_ms: start + duration, duration_ms: duration,
  parent_id, source, attributes, status: 'succeeded', clock_id: source, depth: 0,
});

test('a real Docker subtree folds together without inventing environment stages', () => {
  const rows = [row('total', 'total', 0, 10000), row('queue', 'wait', 0, 10, null, 'scheduler'),
    row('overlay', 'preparation', 10, 90, 'total'), row('docker', 'preparation', 100, 6900, 'total'),
    row('image', 'image', 200, 2200, 'docker'), row('fingerprint', 'preparation', 200, 2160, 'image'),
    row('build', 'build', 2400, 1100, 'docker'), row('container', 'container', 7000, 2900, 'total'),
    row('cleanup', 'cleanup', 9900, 100, 'total')];
  const { groups } = groupOperations(timingSequence({ rows }));
  const environment = groups.find(g => g.title === 'docker');
  assert.equal(environment.duration_ms, 6900);
  assert.equal(environment.recordIds.length, 4);
  assert.deepEqual(environment.records, []);
  const tree = detailTree(environment.members);
  assert.equal(tree.find(n => n.key === 'docker').children[0].children[0].key, 'fingerprint');
  assert.equal(groups.find(g => g.title === 'cleanup').duration_ms, 100);
  assert.ok(groups.some(g => g.title === 'queue'));
  assert.ok(groups.some(g => g.title === 'overlay'));
});

test('Agent nesting stays intact and submission remains a separate recorded operation', () => {
  const rows = [row('total', 'total', 0, 1000), row('container', 'container', 0, 1000, 'total'),
    row('worker', 'total', 10, 980, 'container', 'worker'), row('case', 'case', 20, 900, 'worker', 'worker'),
    row('agent', 'agent', 30, 600, 'case', 'worker', { input_id: 'input-a' }),
    row('invoke', 'execution', 35, 590, 'agent', 'worker'), row('wrapper', 'chain', 40, 500, 'invoke', 'otel'),
    row('llm', 'llm', 50, 400, 'wrapper', 'otel'),
    row('submit', 'sdk_wait', 630, 200, 'case', 'worker', { input_id: 'input-a' }),
    row('flush', 'evidence', 620, 5, 'case', 'worker')];
  const { groups, execution } = groupOperations(timingSequence({ rows }));
  const input = groups.find(g => g.type === 'calls');
  assert.deepEqual(input.records.map(r => r.id), ['agent', 'llm']);
  assert.ok(input.recordIds.includes('wrapper'));
  assert.equal(input.duration_ms, 600);
  assert.equal(execution.duration_ms, 1000);
  assert.deepEqual(groups.find(g => g.title === 'flush').recordIds, ['flush']);
  assert.deepEqual(groups.find(g => g.title === 'submit').recordIds, ['submit']);
  assert.ok(groups.findIndex(g => g.title === 'flush') < groups.findIndex(g => g.title === 'submit'));
});

test('concurrent Inputs do not merge by proximity, and ambiguous identifiers remain separate', () => {
  const rows = [row('a', 'agent', 10, 100, null, 'worker', { input_id: 'shared' }),
    row('b', 'agent', 20, 100, null, 'worker', { input_id: 'shared' }),
    row('wait', 'sdk_wait', 110, 10, null, 'worker', { input_id: 'shared' })];
  const { groups } = groupOperations(timingSequence({ rows }));
  assert.equal(groups.filter(g => g.type === 'calls').length, 3);
  assert.deepEqual(groups.find(g => g.title === 'wait').recordIds, ['wait']);
});

test('unfinished stages and recovery keep their own state and measurements', () => {
  const unfinished = { ...row('docker', 'preparation', 0, 50), status: 'unconfirmed' };
  const recovery = { ...row('recovery', 'total', 500, 100), phase: 'recover', clock_id: 'recovery' };
  const wait = { ...row('wait', 'sdk_wait', 510, 50, 'recovery'), phase: 'recover', clock_id: 'recovery' };
  const { groups } = groupOperations(timingSequence({ rows: [unfinished, recovery, wait] }));
  assert.equal(groups[0].status, 'unconfirmed');
  assert.equal(groups[1].title, 'wait');
  assert.equal(groups[1].duration_ms, 50);
  assert.equal(groupSummary([{ ...unfinished, duration_ms: null }]).duration_ms, null);
});

test('generation is visible and SDK steps separated by execution never collapse together', () => {
  const rows = [row('worker', 'total', 0, 1000, null, 'worker'),
    row('SDK init', 'sdk', 0, 10, 'worker', 'worker'),
    row('Generate Case', 'generation', 10, 600, 'worker', 'worker'),
    row('SDK init again', 'sdk', 610, 20, 'worker', 'worker'),
    row('custom future stage', 'new-kind', 630, 20, 'worker', 'worker')];
  const { groups } = groupOperations(timingSequence({ rows }));
  assert.deepEqual(groups.map(g => g.title), ['SDK init', 'Generate Case', 'SDK init again', 'custom future stage']);
  assert.equal(groups[1].records[0].kind, 'generation');
  assert.equal(groups[3].count, 1);
});

test('identically named operations remain separate and parallel spans retain their timings', () => {
  const rows = [row('a', 'preparation', 0, 50), row('b', 'preparation', 10, 70)];
  rows.forEach(r => { r.name = 'Prepare session'; });
  const { groups } = groupOperations(timingSequence({ rows }));
  assert.equal(groups.length, 2);
  assert.notEqual(groups[0].id, groups[1].id);
  assert.equal(groups[0].end_ms, 50);
  assert.equal(groups[1].start_ms, 10);
});


test('one Input includes Agent calls and SDK submission while bookkeeping retains start order', () => {
  const rows = [row('setup', 'preparation', 0, 10), row('init', 'sdk', 10, 10),
    row('agent', 'agent', 30, 600, null, 'worker', { input_id: 'input-a' }),
    row('llm', 'llm', 50, 400, 'agent', 'worker'),
    row('flush', 'evidence', 620, 5, null, 'worker'),
    row('submit', 'sdk_wait', 630, 200, null, 'worker', { input_id: 'input-a' }),
    row('save', 'evidence', 831, 10, null, 'worker')];
  const grouped = groupTimings(timingSequence({ rows }));
  const input = grouped.groups.find(g => g.inputId === 'input-a');
  assert.deepEqual(input.records.map(r => r.id), ['agent', 'llm', 'submit']);
  assert.equal(input.duration_ms, 800);
  assert.equal(input.members.find(r => r.id === 'submit').parent_id, null);
  assert.deepEqual(grouped.groups[0].recordIds, ['setup', 'init']);
  assert.deepEqual(grouped.groups.at(-1).recordIds, ['save']);
  const entries = sequenceEntries(grouped.groups);
  assert.deepEqual(entries.map(e => e.id), ['sequence:before', 'agent', 'llm', 'operation:flush', 'submit', 'sequence:after']);
  assert.deepEqual(entries.filter(e => e.heading).map(e => e.id), ['agent']);
  assert.equal(entries.find(e => e.id === 'submit').footer, true);
  assert.equal(entries.find(e => e.id === 'llm').footer, false);
  const snapshots = fileSnapshots([{ input: { input_id: 'input-a' }, submission: { file_evidence: { complete: true, changes: [] } } }]);
  const files = placeFileSnapshots(snapshots, grouped.groups);
  assert.equal(files.byGroup.get(entries.find(e => e.id === 'submit').group.id)[0], snapshots[0]);
  assert.equal(files.unplaced.length, 0);
  assert.deepEqual(grouped.groups.flatMap(g => g.recordIds).sort(), rows.map(r => r.id).sort());
});

test('ambiguous Input IDs and recovery phases never merge by nearby timestamps', () => {
  const rows = [row('a', 'agent', 10, 100, null, 'worker', { input_id: 'same' }),
    row('b', 'agent', 20, 100, null, 'worker', { input_id: 'same' }),
    row('wait', 'sdk_wait', 110, 10, null, 'worker', { input_id: 'same' })];
  assert.equal(groupTimings(timingSequence({ rows })).groups.length, 3);
  rows[1].phase = 'recover';
  rows[2].phase = 'recover';
  const groups = groupTimings(timingSequence({ rows })).groups;
  assert.equal(groups.length, 2);
  assert.deepEqual(groups.find(g => g.root.id === 'b').recordIds, ['b', 'wait']);
});

test('concurrent Input presentations never reorder individual calls or duplicate records', () => {
  const rows = [row('a', 'agent', 10, 100, null, 'worker', { input_id: 'a' }),
    row('b', 'agent', 20, 100, null, 'worker', { input_id: 'b' }),
    row('wait-b', 'sdk_wait', 120, 10, null, 'worker', { input_id: 'b' }),
    row('wait-a', 'sdk_wait', 130, 10, null, 'worker', { input_id: 'a' })];
  const entries = sequenceEntries(groupTimings(timingSequence({ rows })).groups);
  assert.deepEqual(entries.map(e => e.id), ['a', 'b', 'wait-b', 'wait-a']);
  assert.deepEqual(entries.filter(e => e.heading).map(e => e.id), ['a', 'b']);
});
