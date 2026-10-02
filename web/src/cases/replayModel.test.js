import test from 'node:test';
import assert from 'node:assert/strict';
import { replayModel, filesAt, stateAt, nextPosition, advancePosition } from './replayModel.js';

test('seeking backward restores the recorded file version and hides future creates', () => {
  const archive = { baseline: { time_ms: 10, entries: { a: { blob: 'one' } } }, events: [
    { sequence: 1, time_ms: 20, changes: [{ path: 'a', before: { blob: 'one' }, after: { blob: 'two' } }] },
    { sequence: 2, time_ms: 30, changes: [{ path: 'a', before: { blob: 'two' }, after: null }, { path: 'b', before: null, after: { blob: 'new' } }] },
  ] };
  assert.deepEqual(filesAt(archive, 30), [['b', { blob: 'new' }]]);
  assert.deepEqual(filesAt(archive, 15), [['a', { blob: 'one' }]]);
  assert.deepEqual(filesAt(archive, 5), []);
});

test('concurrent calls remain running until their own recorded ends', () => {
  const model = replayModel([
    { id: 'one', kind: 'tool', timestamp: 10, ended: 40, status: 'succeeded' },
    { id: 'two', kind: 'http', timestamp: 20, ended: 30, status: 'failed' },
  ]);
  assert.equal(stateAt(model.events[0], 25), 'running');
  assert.equal(stateAt(model.events[1], 25), 'running');
  assert.equal(stateAt(model.events[0], 35), 'running');
  assert.equal(stateAt(model.events[1], 35), 'failed');
  assert.equal(nextPosition(model.points, 25, 1), 30);
  assert.equal(nextPosition(model.points, 25, -1), 20);
});

test('no terminal timestamp is not presented as a completed response', () => {
  const model = replayModel([{ id: 'x', kind: 'chat', timestamp: 10, ended: null }]);
  assert.equal(stateAt(model.events[0], 20), 'No recorded end');
});

test('input envelopes do not duplicate mapped user messages from the same invocation', () => {
  const model = replayModel([
    { id: 'mapped', kind: 'input', timestamp: 10, artifact_file: 'evaluation/inputs/0001/mapped-input.json' },
    { id: 'envelope', kind: 'input', timestamp: 11, artifact_file: 'evaluation/inputs/0001/request.json' },
    { id: 'other', kind: 'input', timestamp: 20, artifact_file: 'invocation-other/output/request.json' },
  ]);
  assert.deepEqual(model.events.map(e => e.id), ['mapped', 'other']);
});

test('wait compression preserves original event times and lands on the next event', () => {
  const model = { points: [10, 5000, 7000], start: 10, end: 7000 };
  assert.equal(advancePosition(model, 10, 100, false), 110);
  assert.equal(advancePosition(model, 10, 100, true), 5000);
  assert.deepEqual(model.points, [10, 5000, 7000]);
});
