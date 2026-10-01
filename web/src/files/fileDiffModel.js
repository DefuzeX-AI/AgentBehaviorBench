import { parsePatchFiles } from '@pierre/diffs';

export function inspectFileDiff(record) {
  const patch = typeof record.diff === 'string' ? record.diff : '';
  if (!patch) return { patch, error: 'No text diff was captured.', preview: null };
  if (patch.length > 2_000_000) return { patch, error: 'This patch is too large for the formatted view. The complete raw patch remains available.', preview: null };
  try {
    const files = parsePatchFiles(patch, undefined, true).flatMap(item => item.files);
    if (files.length !== 1 || !files[0].hunks.length) throw new Error('Expected one file with recorded changes');
    const file = files[0];
    const additions = file.hunks.reduce((sum, hunk) => sum + hunk.additionLines, 0);
    const deletions = file.hunks.reduce((sum, hunk) => sum + hunk.deletionLines, 0);
    const preview = completeContent(record, patch, file);
    return { patch, file, additions, deletions, preview, error: null };
  } catch {
    return { patch, error: 'This patch could not be formatted. The original evidence is shown below.', preview: null };
  }
}

function completeContent(record, patch, file) {
  const created = record.change_type === 'created', deleted = record.change_type === 'deleted';
  if ((!created && !deleted) || record.complete !== true) return null;
  if (!(created ? /^--- \/dev\/null\r?$/m : /^\+\+\+ \/dev\/null\r?$/m).test(patch)) return null;
  const side = created ? 'addition' : 'deletion', other = created ? 'deletion' : 'addition';
  let next = 1;
  for (const hunk of file.hunks) {
    if (hunk[`${side}Start`] !== next || hunk[`${other}Count`] !== 0 || hunk[`${side}Lines`] !== hunk[`${side}Count`]) return null;
    next += hunk[`${side}Count`];
  }
  const lines = file[`${side}Lines`];
  if (lines.length !== next - 1) return null;
  const content = lines.join('');
  const size = created ? record.after_size : record.before_size;
  if (!Number.isSafeInteger(size) || size < 0 || new TextEncoder().encode(content).length !== size) return null;
  return { content, side: created ? 'after' : 'before' };
}
