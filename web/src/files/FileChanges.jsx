import { useState } from 'react';
import { Button } from 'antd';
import FileChangeCard from './FileChangeCard.jsx';
import './fileChanges.css';

export default function FileChanges({ snapshot, animatedIds, onSelect }) {
  const [limit, setLimit] = useState(12);
  return <section className="file-changes" aria-label={`${snapshot.label} file changes`}>
    <div className="file-changes-heading"><strong>File changes</strong><span>{snapshot.changes.length} paths · {snapshot.label} snapshot{!snapshot.complete && ' · Partial evidence'}</span></div>
    <p>Before/after changes for this Input; intermediate operations and their times are not recorded. Deletion is a file action, not an execution error.</p>
    {snapshot.changes.length ? <div className="file-changes-grid">{snapshot.changes.slice(0, limit).map(change =>
      <FileChangeCard key={change.id} change={change} snapshot={snapshot} animate={animatedIds?.has(change.id)} onSelect={onSelect} />)}</div>
      : <p>{snapshot.complete ? 'No net file changes recorded.' : 'No file changes available in this partial snapshot.'}</p>}
    {!!snapshot.errors.length && <p role="status">Some file evidence could not be captured. Review Tools &amp; Files for capture details.</p>}
    {snapshot.changes.length > limit && <Button size="small" onClick={() => setLimit(n => n + 24)}>Show more ({snapshot.changes.length - limit} remaining)</Button>}
  </section>;
}
