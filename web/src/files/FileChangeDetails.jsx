import { Descriptions, Tag, Typography } from 'antd';
import { changeStyle } from './fileChangesModel.js';

export default function FileChangeDetails({ change, snapshot }) {
  const record = change.original;
  return <div className="file-change-details">
    <Typography.Paragraph>Recorded from the workspace before/after snapshots for {snapshot.label}. Exact operation time and the responsible tool were not recorded.</Typography.Paragraph>
    <Descriptions bordered column={1} size="small" items={[
      { key: 'path', label: 'Path', children: <Typography.Text copyable>{change.path}</Typography.Text> },
      { key: 'action', label: 'Change', children: <Tag>{changeStyle(change.type).label}</Tag> },
      { key: 'type', label: 'Type', children: change.fileType || 'Not recorded' },
      ...(record.old_path ? [{ key: 'old', label: 'Previous path', children: record.old_path }] : []),
      { key: 'input', label: 'Input ID', children: snapshot.inputId || 'Not recorded' },
      { key: 'size', label: 'Bytes before → after', children: `${record.before_size ?? '—'} → ${record.after_size ?? '—'}` },
      { key: 'source', label: 'Evidence', children: `${snapshot.source} · ${snapshot.complete && record.complete !== false ? 'Complete' : 'Partial'}` },
    ]} />
    <h4>File diff</h4>
    {typeof record.diff === 'string' && record.diff ? <pre className="file-change-diff">{record.diff}</pre>
      : <p>{change.fileType === 'directory' ? 'Directory change; no text diff.' : record.reason || 'No text diff was captured.'}</p>}
    <details><summary>Original file evidence</summary><pre className="file-change-diff">{JSON.stringify(record, null, 2)}</pre></details>
  </div>;
}
