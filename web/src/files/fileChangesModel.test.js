import test from 'node:test';
import assert from 'node:assert/strict';
import { fileSnapshots, placeFileSnapshots, changeStyle } from './fileChangesModel.js';

const input = (id, changes, complete = true) => ({ input: { input_id: id }, submission: { file_evidence: { complete, changes } } });
const group = (id, inputId) => ({ id, type: 'calls', members: [{ attributes: { 'abb.input_id': inputId } }] });

test('retains snapshot evidence without inventing transient operations or timestamps', () => {
  const changes = [{ path: 'backup/data.json', change_type: 'created', file_type: 'file', after_hash: 'same' },
    { path: 'artifact_staging/data.json', change_type: 'created', file_type: 'file', after_hash: 'same' }];
  const [snapshot] = fileSnapshots([input('step-1', changes)]);
  assert.equal(snapshot.changes.length, 2);
  assert.equal(snapshot.changes.some(c => c.type === 'moved'), false);
  assert.deepEqual(snapshot.changes.map(c => c.original), changes);
  assert.equal('timestamp' in snapshot.changes[0], false);
  assert.deepEqual(fileSnapshots([input('step-1', changes)]), [snapshot]);
});

test('matches by recorded Input ID, never by array order or tool name', () => {
  const snapshots = fileSnapshots([input('step-2', []), input('step-1', [])]);
  const placed = placeFileSnapshots(snapshots, [group('first', 'step-1'), group('second', 'step-2')]);
  assert.equal(placed.byGroup.get('first')[0].inputId, 'step-1');
  assert.equal(placed.byGroup.get('second')[0].inputId, 'step-2');
  assert.equal(placed.unplaced.length, 0);
  assert.equal(placeFileSnapshots(snapshots, [group('a', 'step-1'), group('b', 'step-1')]).unplaced.length, 2);
});

test('missing, partial and empty snapshots remain distinct', () => {
  assert.deepEqual(fileSnapshots([{}]), []);
  const [empty, partial] = fileSnapshots([input('a', []), { result: { input_id: 'b' }, evidence: { file_evidence: { complete: false, changes: [], errors: ['inaccessible path'] } } }]);
  assert.equal(empty.complete, true);
  assert.equal(partial.complete, false);
  assert.deepEqual(partial.errors, ['inaccessible path']);
  assert.equal(partial.inputId, 'b');
});

test('recorded move source and unknown actions are preserved', () => {
  const [snapshot] = fileSnapshots([input('step', [{ path: 'new', old_path: 'old', change_type: 'renamed' }, { path: 'link', change_type: 'permissions_changed' }])]);
  assert.equal(snapshot.changes[0].original.old_path, 'old');
  assert.equal(changeStyle(snapshot.changes[0].type).tone, 'moved');
  assert.equal(changeStyle(snapshot.changes[1].type).tone, 'unknown');
  assert.equal(changeStyle('deleted').label, 'Deleted');
});
