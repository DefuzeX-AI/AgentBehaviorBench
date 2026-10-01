import { changeStyle } from './fileChangesModel.js';

export default function FileChangeTooltip({ change, snapshot }) {
  return <div className="file-change-tooltip">
    <strong>{changeStyle(change.type).label} · {change.fileType || 'Unknown file type'}</strong>
    <div>{change.path}</div>
    {change.original.old_path && <div>From: {change.original.old_path}</div>}
    <div>{snapshot.label} · Before/after snapshot</div>
    <div>Exact operation time and tool attribution not recorded.</div>
    <div>Click for diff and evidence.</div>
  </div>;
}
