import { useMemo, useState } from 'react';
import { Alert, Button, Drawer, Tag } from 'antd';
import useLiveJson from '../useLiveJson.js';
import { formatTime, makeTimeline } from './timelineModel.js';
import { timingSequence } from '../sequence/model.js';
import { groupTimings } from '../sequence/grouping.js';
import SequenceDiagram from '../sequence/SequenceDiagram.jsx';
import TimingDetails from './TimingDetails.jsx';
import './sharedPreparation.css';

export default function SharedPreparation({ run, revision, index }) {
  const { data, error } = useLiveJson(`/api/observe/runs/${run}/timeline`, revision);
  const [selection, setSelection] = useState(null), [expanded, setExpanded] = useState(false);
  const model = useMemo(() => makeTimeline(data), [data]);
  const sequence = useMemo(() => timingSequence(model), [model]);
  const grouped = useMemo(() => groupTimings(sequence), [sequence]);
  const generation = grouped.groups.filter(group => group.members.some(row => row.kind === 'generation'));
  const shown = expanded ? grouped : { ...grouped, groups: generation };
  const group = grouped.groups.find(item => item.id === selection);
  const row = model.rows.find(item => item.id === selection);
  const ids = new Set(group?.recordIds || (row ? [row.id] : []));
  const details = model.rows.filter(item => { if (ids.has(item.parent_id)) ids.add(item.id); return ids.has(item.id); });
  return <section className="shared-preparation" aria-label={`Shared Case preparation ${index + 1}`}>
    <header><div><strong>Shared Case preparation {index + 1}</strong> <Tag>Shared</Tag></div><strong>{formatTime(model.total_ms)}</strong></header>
    <p>Recorded before Case execution. Shared batch cost; excluded from this attempt's total. Generation includes the SDK call and saving the Case, not server-only compute time.</p>
    {error && <Alert type="warning" message="Unable to refresh shared preparation" description={error} />}
    {!data && !error && <p role="status">Loading saved preparation…</p>}
    {!!model.rows.length && <>
      <Button className="shared-preparation-toggle" onClick={() => setExpanded(value => !value)}>{expanded ? 'Show generation only' : 'Show preparation setup & all recorded operations'}</Button>
      {!expanded && !generation.length && <p>No Case generation timing was recorded. Open all operations for available preparation evidence.</p>}
      <SequenceDiagram records={sequence} grouped={shown} start={model.start} end={model.end} selectedId={selection}
        onInspect={({ timing, group: groupId }) => setSelection(groupId || timing.id)} />
    </>}
    {data && !model.rows.length && <p>No saved preparation timings are available for this run.</p>}
    {model.warnings.map(warning => <Alert key={warning} type="warning" message={warning} />)}
    <Drawer title={group?.title || row?.name || 'Shared preparation details'} open={Boolean(group || row)} size="large" destroyOnHidden onClose={() => setSelection(null)}>
      {!!details.length && <TimingDetails key={`${run}:${selection}`} records={details} focusId={row?.id} run={run} spans={data?.spans} />}
    </Drawer>
  </section>;
}
