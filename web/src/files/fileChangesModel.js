export const changeStyles = {
  created: { label: 'Created', mark: '+', tone: 'created' },
  deleted: { label: 'Deleted', mark: '−', tone: 'deleted' },
  modified: { label: 'Modified', mark: '~', tone: 'modified' },
  moved: { label: 'Moved', mark: '→', tone: 'moved' },
  renamed: { label: 'Renamed', mark: '→', tone: 'moved' },
};

export const changeStyle = type => changeStyles[type] || { label: type || 'Recorded change', mark: '•', tone: 'unknown' };

export function fileSnapshots(inputs = []) {
  return inputs.flatMap((step, index) => {
    const evidence = step.submission?.file_evidence || step.evidence?.file_evidence;
    if (!evidence) return [];
    const inputId = step.input?.input_id || step.request?.input_id || step.result?.input_id || step.submission?.input_id;
    const id = `files:${inputId || `index-${index}`}`;
    return [{ id, inputId, label: `Input ${index + 1}`, complete: evidence.complete === true,
      errors: evidence.errors || [], source: step.submission?.file_evidence ? 'submission.file_evidence' : 'evidence.file_evidence',
      changes: (evidence.changes || []).map((change, i) => ({
        id: `${id}:${i}:${change.path}:${change.change_type}`, path: change.path || '(path not recorded)',
        type: change.change_type, fileType: change.file_type, original: change,
      })),
    }];
  });
}

// Only attach to an unambiguous recorded Input. Never infer a tool or event time.
export function placeFileSnapshots(snapshots, groups) {
  const byGroup = new Map(), unplaced = [];
  for (const snapshot of snapshots) {
    const candidates = snapshot.inputId ? groups.filter(group => group.type === 'calls' && group.members.some(row =>
      (row.attributes?.input_id || row.attributes?.['abb.input_id']) === snapshot.inputId)) : [];
    const owners = candidates.filter(group => group.members.some(row => row.kind === 'agent' && row.attributes?.input_id === snapshot.inputId));
    const matches = owners.length ? owners : candidates;
    if (matches.length !== 1) { unplaced.push(snapshot); continue; }
    const key = matches[0].id;
    byGroup.set(key, [...(byGroup.get(key) || []), snapshot]);
  }
  return { byGroup, unplaced };
}
