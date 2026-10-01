import { useMemo, useState } from 'react';
import { Select, Typography } from 'antd';
import { formatTime } from '../cases/timelineModel.js';
import { sequenceScale, timingLanes } from './model.js';
import { sequenceEntries } from './grouping.js';
import './sequence.css';

const labels = { succeeded: 'Completed', complete: 'Completed', failed: 'Failed', running: 'Running',
  pending: 'Waiting', unconfirmed: 'End unconfirmed', recorded: 'Recorded', unknown: 'Unknown', cancelled: 'Cancelled' };
const percent = (duration, reference) => Number.isFinite(duration) && reference > 0 ? Math.min(100, duration / reference * 100) : null;

function DurationBar({ duration, reference }) {
  const ratio = percent(duration, reference);
  return <span className="sequence-duration-track" aria-hidden="true">{ratio != null && <i style={{ width: `${ratio}%` }} />}</span>;
}

function CallArrows({ row, from, to }) {
  const rightward = to > from;
  const range = { left: `${Math.min(from, to)}%`, width: `${Math.abs(to - from)}%` };
  return <div className="sequence-arrows" role="img"
    aria-label={`${row.linkLabel}: ${timingLanes[row.fromLane]} to ${timingLanes[row.lane]}${row.endKnown ? ', confirmed end' : ', no confirmed end'}`}>
    <span className={`sequence-activation${row.endKnown ? '' : ' sequence-activation-open'}`} style={{ left: `${to}%` }} />
    <span className={`sequence-arrow sequence-call sequence-arrow-${rightward ? 'right' : 'left'}`} style={range} />
    {row.endKnown && <span className={`sequence-arrow sequence-return sequence-arrow-${rightward ? 'left' : 'right'}`} style={range} />}
  </div>;
}

function participatingLanes(records) {
  return [...new Set(records.flatMap(r => [r.lane, r.fromLane]).filter(l => l != null))].sort((a, b) => a - b);
}

function CallRow({ row, lanes, origin, reference, onInspect, selectedId, inputReference }) {
  const position = lane => (lanes.indexOf(lane) + 0.5) / lanes.length * 100;
  const linked = row.fromLane != null && row.fromLane !== row.lane;
  return <div className="sequence-row" data-operation={row.id}>
    <div className="sequence-time">{row.start_ms != null && origin != null ? `+${formatTime(row.start_ms - origin)}` : 'Not recorded'}</div>
    <div className="sequence-body">
      <div className={`sequence-action${linked ? ' sequence-action-linked' : ''}`}>
        {linked && <CallArrows row={row} from={position(row.fromLane)} to={position(row.lane)} />}
        <button className={`sequence-card sequence-lane-${row.lane} sequence-status-${row.status}`}
          style={{ gridColumn: lanes.indexOf(row.lane) + 1 }} aria-pressed={selectedId === row.id}
          title={`${row.title} · ${formatTime(row.duration_ms)} · ${labels[row.status] || row.status}`}
          onClick={() => onInspect(row.inspect)}>
          <span className="sequence-call-line"><strong>{row.title}</strong><span className="sequence-duration">{formatTime(row.duration_ms)}</span></span>
          <DurationBar duration={row.duration_ms} reference={reference} />
          {inputReference && <small className="sequence-input-reference">Input · {inputReference}</small>}
          {!['succeeded', 'complete', 'recorded'].includes(row.status) && <small>{labels[row.status] || row.status}</small>}
        </button>
      </div>
    </div>
  </div>;
}

function Canvas({ lanes, children }) {
  return <div className="sequence-scroll" tabIndex={0} role="region" aria-label="Scrollable sequence lanes">
    <div className="sequence-grid" style={{ '--lane-count': Math.max(1, lanes.length), minWidth: Math.max(320, 96 + lanes.length * 180) }}>
      <div className="sequence-header"><span>Start offset</span>{lanes.map(lane => <strong key={lane}>{timingLanes[lane]}</strong>)}</div>
      <div className="sequence-canvas">
        <div className="sequence-lifelines">{lanes.map(lane => <i key={lane} />)}</div>
        {children}
      </div>
    </div>
  </div>;
}

function CallLanes({ records, origin, onInspect, selectedId }) {
  const lanes = participatingLanes(records);
  const longest = Math.max(0, ...records.map(r => r.duration_ms || 0));
  return <Canvas lanes={lanes}>{records.map(row => <CallRow key={row.id} row={row} lanes={lanes}
    origin={origin} reference={longest} onInspect={onInspect} selectedId={selectedId} />)}</Canvas>;
}

function StageBlock({ group, reference, origin, onInspect, selectedId }) {
  return <button className={`sequence-stage sequence-status-${group.status}`} aria-pressed={selectedId === group.id}
    onClick={() => onInspect(group.inspect)}>
    <span className="sequence-stage-name"><strong>{group.title}</strong><small>{group.count} recorded steps · Starts +{formatTime(group.start_ms - origin)} · {group.basis} · View details →</small></span>
    <span className="sequence-stage-duration"><strong>{formatTime(group.duration_ms)}{group.incomplete ? ' +' : ''}</strong>
      <DurationBar duration={group.duration_ms} reference={reference} /><small>{labels[group.status] || group.status}</small></span>
  </button>;
}

export default function SequenceDiagram({ records, grouped, start, end, onInspect, selectedId, renderGroupFooter }) {
  const [filter, setFilter] = useState('overview');
  const scale = useMemo(() => sequenceScale(records, start, end), [records, start, end]);
  const groups = grouped?.groups || [];
  const longest = Math.max(0, ...groups.map(g => g.duration_ms || 0));
  const slow = new Set([...groups].sort((a, b) => (b.duration_ms || 0) - (a.duration_ms || 0)).slice(0, 3).map(g => g.id));
  const visible = groups.filter(g => filter === 'overview' || slow.has(g.id));
  const entries = sequenceEntries(visible);
  // Determine positions from the full run, so filtering and Input boundaries cannot move a lane.
  const lanes = participatingLanes(groups.flatMap(group => group.records));
  const overlapping = new Set(groups.filter(group => group.inputId && groups.some(other =>
    other.id !== group.id && other.type === 'calls' && other.start_ms < group.end_ms && group.start_ms < other.end_ms)).map(group => group.id));
  return <section className="execution-sequence" aria-label="Execution sequence with timings">
    <div className="sequence-toolbar"><div><Typography.Text strong>Execution sequence</Typography.Text>
      <p>One continuous flow with fixed lanes. Inputs use recorded IDs; small steps stay in start order. Click any block for its original records.</p></div>
      {grouped && <Select aria-label="Sequence stages" value={filter} onChange={setFilter}
        options={[{ value: 'overview', label: 'Full flow' }, { value: 'slow', label: '3 longest groups' }]} />}</div>
    {grouped ? <Canvas lanes={lanes}>{entries.map(entry => {
      const { group, row } = entry;
      return <div className="sequence-section" key={entry.id}>
        {entry.heading && <button className="sequence-input-heading" onClick={() => onInspect(group.inspect)}>
          <strong>{group.title}</strong><span>{formatTime(group.duration_ms)} measured · {group.count} records · View details →</span></button>}
        {row ? <CallRow row={row} lanes={lanes} origin={scale.origin}
          inputReference={overlapping.has(group.id) ? group.inputId : null}
          reference={Math.max(0, ...group.records.map(r => r.duration_ms || 0))} onInspect={onInspect} selectedId={selectedId} />
          : group.id.startsWith('sequence:') ? <StageBlock group={group} reference={longest} origin={scale.origin} onInspect={onInspect} selectedId={selectedId} />
            : <div className="sequence-row sequence-bookkeeping">
              <div className="sequence-time">+{formatTime(group.start_ms - scale.origin)}</div>
              <button className={`sequence-inline-stage sequence-status-${group.status}`} aria-pressed={selectedId === group.id} onClick={() => onInspect(group.inspect)}>
                <span>{group.title} <small>· Details →</small></span><span>{formatTime(group.duration_ms)}{group.incomplete ? ' +' : ''}
                  {!['succeeded', 'complete', 'recorded'].includes(group.status) && ` · ${labels[group.status] || group.status}`}</span>
              </button>
            </div>}
        {entry.footer && renderGroupFooter?.(group)}
      </div>;
    })}</Canvas> : <CallLanes records={records} origin={scale.origin} onInspect={onInspect} selectedId={selectedId} />}
    {grouped && !visible.length && <p className="sequence-empty">No recorded stages in this selection.</p>}
    <div className="sequence-footer">Solid: recorded call relationship · Dashed: confirmed end · Compact rows do not imply equal duration</div>
  </section>;
}
