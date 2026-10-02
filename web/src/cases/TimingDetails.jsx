import { lazy, Suspense, useMemo, useState } from 'react';
import { Descriptions, Tag, Tree, Typography } from 'antd';
import { detailTree } from '../sequence/grouping.js';
import { formatTime } from './timelineModel.js';

const SpanDetails = lazy(() => import('../otel/TraceView.jsx').then(module => ({ default: module.SpanDetails })));

export default function TimingDetails({ records, focusId, run, spans }) {
  const tree = useMemo(() => detailTree(records), [records]);
  const [focused, setFocused] = useState(() => focusId || [...tree].sort((a, b) => (b.row.duration_ms || 0) - (a.row.duration_ms || 0))[0]?.key);
  const selected = records.find(r => r.id === focused) || records[0];
  const byId = useMemo(() => new Map(records.map(r => [r.id, r])), [records]);
  const longest = Math.max(0, ...tree.map(n => n.row.duration_ms || 0));
  const span = spans?.find(s => `${s.trace_id}:${s.span_id}` === selected?.id);
  if (!selected) return <p>No saved steps in this stage.</p>;
  return <div className="timing-details">
    <Typography.Text type="secondary">{records.length} recorded steps. Children are included in their parent; do not add their durations. Select a step to inspect it.</Typography.Text>
    <Tree className="timing-step-tree" treeData={tree} blockNode defaultExpandAll height={320}
      selectedKeys={[selected.id]} onSelect={keys => { if (keys[0]) setFocused(keys[0]); }}
      titleRender={({ row }) => {
        const parent = byId.get(row.parent_id);
        const comparable = !parent || row.source === parent.source || row.source === 'otel' && parent.source === 'worker';
        const reference = parent?.duration_ms ?? longest;
        const ratio = comparable && reference > 0 && Number.isFinite(row.duration_ms) ? Math.min(100, row.duration_ms / reference * 100) : null;
        return <span className={`timing-tree-row timing-tree-${row.status}`} title={`${row.name} · ${formatTime(row.duration_ms)} · ${row.status}`}>
          <span className="timing-tree-name">{row.name}</span><span className="timing-tree-meter">{ratio != null && <i style={{ width: `${ratio}%` }} />}</span>
          <strong>{formatTime(row.duration_ms)}</strong><span className="timing-tree-state">{row.status}</span>
        </span>;
      }} />
    <Descriptions title={selected.name} bordered size="small" column={2} items={[
      { key: 'duration', label: 'Elapsed', children: formatTime(selected.duration_ms) },
      { key: 'self', label: 'Outside measured children', children: formatTime(selected.self_ms) },
      { key: 'status', label: 'Status', children: <Tag>{selected.status}</Tag> },
      { key: 'source', label: 'Source', children: selected.source },
      { key: 'start', label: 'Started', children: new Date(selected.start_ms).toISOString() },
      { key: 'input', label: 'Input', children: selected.attributes?.input_id || selected.attributes?.['abb.input_id'] || '—' },
    ]} />
    {span && <Suspense fallback={<p>Loading span details…</p>}><SpanDetails key={`${run}:${selected.id}`} run={run} span={span} /></Suspense>}
    <details><summary>Complete timing record</summary><pre className="timing-record">{JSON.stringify(selected, null, 2)}</pre></details>
  </div>;
}
