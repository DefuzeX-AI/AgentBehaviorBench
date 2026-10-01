import test from 'node:test';
import assert from 'node:assert/strict';
import { inspectFileDiff } from './fileDiffModel.js';

const added = { change_type: 'created', complete: true, after_size: 11,
  diff: '--- /dev/null\n+++ /workspace/note.md\n@@ -0,0 +1,2 @@\n+# Hi\n+Hello\n' };

test('new Markdown preview preserves complete content and raw patch', () => {
  const model = inspectFileDiff(added);
  assert.equal(model.preview.content, '# Hi\nHello\n');
  assert.equal(model.preview.side, 'after');
  assert.equal(model.patch, added.diff);
  assert.equal(model.additions, 2);
  assert.equal(model.deletions, 0);
});

test('deleted content and no-newline UTF-8 evidence remain exact', () => {
  const model = inspectFileDiff({ change_type: 'deleted', complete: true, before_size: 6,
    diff: '--- /workspace/file.txt\n+++ /dev/null\n@@ -1 +0,0 @@\n-你好\n\\ No newline at end of file\n' });
  assert.equal(model.preview.content, '你好');
  assert.equal(model.preview.side, 'before');
  assert.equal(model.deletions, 1);
});

test('partial, mismatched or missing size evidence never becomes a full preview', () => {
  for (const update of [{ complete: false }, { complete: undefined }, { after_size: 12 }, { after_size: undefined },
    { diff: added.diff.replace('+1,2', '+4,2') }, { diff: added.diff.replace('+1,2', '+1,9') },
    { diff: added.diff.replace('--- /dev/null', '--- /workspace/existing.md') }]) {
    assert.equal(inspectFileDiff({ ...added, ...update }).preview, null);
  }
});

test('modified files expose real changes without claiming to have full source', () => {
  const model = inspectFileDiff({ change_type: 'modified', complete: true,
    diff: '--- /workspace/a.py\n+++ /workspace/a.py\n@@ -10,2 +10,2 @@\n context\n-old\n+new\n' });
  assert.equal(model.preview, null);
  assert.equal(model.additions, 1);
  assert.equal(model.deletions, 1);
  assert.equal(model.file.hunks[0].additionStart, 10);
});

test('invalid and multi-file patches keep original evidence accessible', () => {
  for (const patch of ['not a patch', added.diff + added.diff, 'x'.repeat(2_000_001)]) {
    const model = inspectFileDiff({ ...added, diff: patch });
    assert.ok(model.error);
    assert.equal(model.patch, patch);
    assert.equal(model.preview, null);
  }
});
