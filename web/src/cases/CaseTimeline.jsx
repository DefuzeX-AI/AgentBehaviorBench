import { lazy, Suspense, useMemo, useState } from 'react';
import { Alert, Button, Drawer, Segmented, Select, Statistic, Table, Typography } from 'antd';
import SequenceDiagram from '../sequence/SequenceDiagram.jsx';
import { timingSequence } from '../sequence/model.js';
import { groupTimings } from '../sequence/grouping.js';
import { buildTopology } from '../topology/model.js';
import TimingDetails from './TimingDetails.jsx';
import useLiveJson from '../useLiveJson.js';
import { formatTime, makeTimeline } from './timelineModel.js';
import './timeline.css';
import FileChanges from '../files/FileChanges.jsx';
import FileChangeDetails from '../files/FileChangeDetails.jsx';
import { fileSnapshots, placeFileSnapshots } from '../files/fileChangesModel.js';
import useFileChangeAnimation from '../files/useFileChangeAnimation.js';

const { Text } = Typography;
const Waterfall = lazy(() => import('./CaseWaterfall.jsx'));
const Topology = lazy(() => import('../topology/TopologyDiagram.jsx'));

const emptyInputs = [];

export default function CaseTimeline({ run, revision, attempt, preparationRuns = [], inputs = emptyInputs, evidenceReady = false, evidenceError }) {
  const [scope, setScope] = useState('case'), [selection, setSelection] = useState(null);
  const [fileSelection, setFileSelection] = useState(null);
  const [view, setView] = useState(() => {
    const saved = new URLSearchParams(location.search).get('timingView');
    return ['waterfall', 'topology'].includes(saved) ? saved : 'sequence';
  });
  const selectedRun = scope === 'case' ? run : scope;
  const { data, error } = useLiveJson(selectedRun ? `/api/observe/runs/${selectedRun}/timeline` : null, revision);
  const model = useMemo(() => makeTimeline(data, scope === 'case' ? attempt : null), [data, attempt, scope]);
  const sequence = useMemo(() => timingSequence(model), [model]);
  const grouped = useMemo(() => groupTimings(sequence), [sequence]);
  const topology = useMemo(() => buildTopology(model.rows), [model]);
  const snapshots = useMemo(() => fileSnapshots(inputs), [inputs]);
  const files = useMemo(() => placeFileSnapshots(snapshots, grouped.groups), [snapshots, grouped]);
  const animatedIds = useFileChangeAnimation(snapshots, evidenceReady);
  const fileSnapshot = snapshots.find(snapshot => snapshot.id === fileSelection?.snapshot.id);
  const selectedFile = fileSnapshot?.changes.find(change => change.id === fileSelection?.change.id);
  const inspectTiming = id => { setSelection(id); setFileSelection(null); };
  const inspectFile = value => { setFileSelection(value); setSelection(null); };
  const renderFiles = list => list.map(snapshot => <FileChanges key={snapshot.id} snapshot={snapshot} animatedIds={animatedIds} onSelect={inspectFile} />);
  const selectedGroup = [...grouped.groups, grouped.execution].find(g => g.id === selection);
  const selectedParticipant = [...topology.nodes, ...topology.edges].find(g => g.id === selection);
  const selected = model.rows.find(row => row.id === selection);
  const detailRecords = useMemo(() => {
    if (selectedGroup) {
      const ids = new Set(selectedGroup.recordIds);
      return model.rows.filter(row => ids.has(row.id));
    }
    const ids = new Set(selectedParticipant?.recordIds || (selected ? [selected.id] : []));
    // makeTimeline emits parents before children.
    return model.rows.filter(row => { if (ids.has(row.parent_id)) ids.add(row.id); return ids.has(row.id); });
  }, [model, selected, selectedGroup, selectedParticipant]);
  const columns = [
    { title: 'Stage', dataIndex: 'name', render: (name, row) => <Button type="link" onClick={() => inspectTiming(row.id)}>{name}</Button> },
    { title: 'Offset', render: (_, row) => formatTime(row.start_ms - model.start) },
    { title: 'Duration', dataIndex: 'duration_ms', render: formatTime, sorter: (a, b) => (a.duration_ms ?? -1) - (b.duration_ms ?? -1) },
    { title: 'Status', dataIndex: 'status' },
  ];
  return <section className="case-timeline" aria-label="Case timings">
    {!!preparationRuns.length && <label>Timing scope <Select value={scope} onChange={value => { setScope(value); setSelection(null); setFileSelection(null); }}
      options={[{ value: 'case', label: 'Selected Case attempt' }, ...preparationRuns.map((id, i) => ({ value: id, label: `Shared Case preparation ${i + 1}` }))]} /></label>}
    {scope !== 'case' && <Alert type="info" showIcon message="Shared preparation is measured once for the batch. It is not added to every Case's execution total." />}
    {error && <Alert type="warning" showIcon message="Unable to refresh timings" description={error} />}
    <div className="timing-summary">
      <Statistic title={model.total_label} value={formatTime(model.total_ms)} />
      <Statistic title="Agent turns (included in total)" value={formatTime(model.agent_ms)} />
      <Statistic title="SDK submit / wait (included in total)" value={formatTime(model.sdk_ms)} />
    </div>
    {model.hasTimings && <div className="timing-phases" aria-label="Recorded runtime phases">
      {model.phases.map(phase => <span key={phase.label}>{phase.label} <strong>{formatTime(phase.duration_ms)}</strong></span>)}
    </div>}
    {!data && selectedRun && !error && <p>Loading saved timings…</p>}
    {!selectedRun && <p>No execution artifact is available yet.</p>}
    {data && !model.hasTimings && <Alert type="info" showIcon message="This older run has no lifecycle timings." description="Available traces are shown below. Missing preparation and SDK timings are not reconstructed." />}
    {model.rows.some(s => s.status === 'unconfirmed') && <Alert type="warning" showIcon message="Some stages have no confirmed end. Their last recorded measurement is retained; time is not extrapolated." />}
    {model.warnings.map(w => <Alert key={w} type="warning" message={w} />)}
    {!!model.rows.length && <>
      <Segmented aria-label="Timing view" value={view} options={[{ label: 'Sequence', value: 'sequence' }, { label: 'Waterfall', value: 'waterfall' }, { label: 'Topology', value: 'topology' }]}
        onChange={value => { setView(value); const url = new URL(location.href); url.searchParams.set('timingView', value); history.replaceState(null, '', url); }} />
      {view === 'sequence' ? <SequenceDiagram key={selectedRun || 'pending'} records={sequence} grouped={grouped} start={model.start} end={model.end}
        selectedId={selection} onInspect={({ timing, group }) => inspectTiming(group || timing.id)}
        renderGroupFooter={scope === 'case' ? group => renderFiles(files.byGroup.get(group.id) || []) : undefined} />
        : view === 'topology' ? <Suspense fallback={<p>Loading topology…</p>}><Topology key={selectedRun || 'pending'} graph={topology} onSelect={inspectTiming} selectedId={selection} /></Suspense>
          : <Suspense fallback={<p>Loading waterfall…</p>}><Waterfall key={selectedRun || 'pending'} model={model} onSelect={inspectTiming} /></Suspense>}
      <Text type="secondary">Nested and parallel durations overlap; they are not added together. Host and container positions use wall-clock anchors. Recorded lifecycle durations use each process's monotonic clock.</Text>
      <details><summary>All recorded stages · {model.rows.length}</summary>
        <Table size="small" rowKey="id" columns={columns} dataSource={model.rows} pagination={{ pageSize: 20 }} scroll={{ x: 580 }} />
      </details>
    </>}
    {scope === 'case' && <>
      {evidenceError && <Alert type="warning" message="Unable to refresh file evidence" description={evidenceError} />}
      {renderFiles(view === 'sequence' && model.rows.length ? files.unplaced : snapshots)}
      {evidenceReady && !snapshots.length && <Text type="secondary">No file snapshot evidence was captured for this attempt.</Text>}
    </>}
    <Drawer title={selectedFile ? `File change · ${selectedFile.path}` : selectedParticipant?.title || selectedGroup?.title || selected?.name || 'Stage details'} open={Boolean(selectedFile || selected || selectedGroup || selectedParticipant)}
      onClose={() => { setSelection(null); setFileSelection(null); }} size="large" destroyOnHidden>
      {selectedFile ? <FileChangeDetails change={selectedFile} snapshot={fileSnapshot} />
        : !!detailRecords.length && <TimingDetails key={`${selectedRun}:${selection}`} records={detailRecords} focusId={selected?.id} run={selectedRun} spans={data?.spans} />}
    </Drawer>
  </section>;
}
