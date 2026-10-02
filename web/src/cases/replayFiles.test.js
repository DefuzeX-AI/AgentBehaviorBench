import test from 'node:test';
import assert from 'node:assert/strict';
import { filesAt } from './replayModel.js';
import { parentDirectories, replayFiles } from './replayFiles.js';

test('tree preserves folders, change ancestors and deleted files at the playback position', () => {
  const initial = { type: 'file', blob: 'one' };
  const changes = [{ path: 'src/a.txt', before: initial, after: null },
    { path: 'src/new/b.txt', before: null, after: { type: 'file', blob: 'two' } }];
  const archive = { baseline: { time_ms: 10, entries: { 'src/a.txt': initial, 'unchanged.txt': initial } },
    events: [{ time_ms: 20, changes }] };
  const after = replayFiles(filesAt(archive, 20), changes, true);
  assert.equal(after.changedCount, 2);
  assert.equal(after.tree.length, 1);
  assert.equal(after.tree[0].key, 'src');
  assert.equal(after.tree[0].changedCount, 2);
  assert.equal(after.tree[0].children[0].key, 'src/new');
  assert.equal(after.tree[0].children[0].children[0].change, 'A');
  assert.equal(after.tree[0].children[1].change, 'D');
  const before = replayFiles(filesAt(archive, 15), []);
  assert.equal(before.changedCount, 0);
  assert.equal(before.tree[0].children.length, 1);
  assert.equal(before.tree[0].children[0].key, 'src/a.txt');
  assert.deepEqual(parentDirectories(changes.map(c => c.path)), ['src', 'src/new']);
});

test('the latest change replaces deletion badges after recreation', () => {
  const value = { type: 'file' };
  const model = replayFiles([['a', value]], [{ path: 'a', before: value, after: null }, { path: 'a', before: null, after: value }]);
  assert.equal(model.changedCount, 1);
  assert.equal(model.tree[0].change, 'A');
});
