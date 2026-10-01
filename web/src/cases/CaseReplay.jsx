import { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Checkbox, Drawer, Empty, Popover, Select, Slider, Tag } from 'antd';
import useLiveJson from '../useLiveJson.js';
import ReadableContent from './ReadableContent.jsx';
import { UserOutlined, RobotOutlined, ToolOutlined, GlobalOutlined, ReloadOutlined, SettingOutlined, CaretRightOutlined, PauseOutlined, StepBackwardOutlined, StepForwardOutlined } from '@ant-design/icons';
import ReplayMessage from './ReplayMessage.jsx';
import ReplayFiles from './ReplayFiles.jsx';
import ReplayJudgeCard from './ReplayJudgeCard.jsx';
import { responseMessages } from '../interactions/protocols.js';
import { advancePosition, filesAt, nextPosition, replayModel, stateAt } from './replayModel.js';
import './replay.css';

const stamp = ms => `${Math.floor(Math.max(0, ms) / 60000)}:${(Math.max(0, ms) / 1000 % 60).toFixed(1).padStart(4, '0')}`;
const lanes = [['input', 'output', 'chat'], ['tool', 'tool_call'], ['http'], ['file'], ['judge']];
const labels = ['Conversation', 'Tools / MCP', 'Network', 'Files', 'Judge'];

async function get(url, signal) {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error('Unable to load replay records');
  return response.json();
}

function useReplay(run, reload) {
  const [state, setState] = useState({});
  useEffect(() => {
    const controller = new AbortController();
    setState({});
    async function load() {
      const base = `/api/observe/runs/${run}`;
      const [archive, first] = await Promise.all([
        get(`${base}/replay`, controller.signal), get(`${base}/interactions?page_size=100`, controller.signal),
      ]);
      const warnings = [...(archive.warnings || []), ...(first.warnings || [])];
      const rows = [...first.items], events = [...archive.events];
      let cursor = archive.next;
      while (cursor != null) {
        const page = await get(`${base}/replay?offset=${cursor}&through=${archive.manifest.event_count}`, controller.signal);
        events.push(...page.events.filter(event => event.sequence <= archive.manifest.event_count));
        warnings.push(...page.warnings);
        cursor = page.next;
        if (page.events.some(event => event.sequence >= archive.manifest.event_count)) break;
      }
      for (let page = 2; page <= Math.ceil(first.total / 100); page++) {
        const data = await get(`${base}/interactions?page_size=100&page=${page}`, controller.signal);
        if (data.revision !== first.revision) {
          warnings.push('Run records changed during loading. Refresh to obtain a consistent replay.');
          break;
        }
        rows.push(...data.items);
      }
      if (!controller.signal.aborted) setState({ archive: { ...archive, events },
        rows: [...new Map(rows.map(row => [row.id, row])).values()], warnings: [...new Set(warnings)] });
    }
    if (run) load().catch(error => { if (!controller.signal.aborted) setState({ error: error.message }); });
    return () => controller.abort();
  }, [run, reload]);
  return state;
}

function EventContent({ run, event, time, details = false, onInspect }) {
  const { data, error } = useLiveJson(event?.source === 'interaction'
    ? `/api/observe/runs/${run}/interactions?id=${event.id}` : null, null, false);
  if (!event) return <p>Select an event to inspect its recorded evidence.</p>;
  if (event.source === 'file') return <><p>Observed file versions · {event.event.reason}</p>
    <p>These changes are not attributed to a tool.</p>
    {details && <ReadableContent value={event.event} />}</>;
  if (error) return <Alert type="warning" title={error} />;
  if (!data) return <p>Loading recorded content…</p>;
  const finished = Number.isFinite(event.end) && event.end <= time;
  if (details) return <div className="replay-evidence">
    <p>{event.title} · {stateAt(event, time)}</p>
    <p>{event.time_basis === 'file_mtime' ? 'Approximate position from artifact modification time.' : 'Position from recorded timestamps.'}</p>
    {data.request && Object.keys(data.request).length > 0 && <><h4>Request / input</h4><ReadableContent value={data.request?.payload ?? data.request?.input ?? data.request} /></>}
    {finished && <><h4>Response / output</h4><ReadableContent value={data.response?.client_payload ?? data.response?.payload ?? data.response?.output ?? data.response} /></>}
    {data.artifact != null && <ReadableContent value={data.artifact} />}
    <small>Call: {data.call_id || data.framework_span_id || 'No recorded ID'} · Input: {data.input_id || 'Unlinked'}</small>
  </div>;
  if (event.kind === 'input') return <ReplayMessage value={data.artifact?.payload ?? data.artifact?.input ?? data.artifact} />;
  if (event.kind === 'output') return <ReplayMessage value={data.artifact?.output ?? data.artifact} />;
  if (event.kind === 'judge') return <ReplayJudgeCard report={data.artifact} onInspect={onInspect} />;
  if (event.kind === 'chat' && finished) {
    const reply = responseMessages(data.response?.client_payload ?? data.response?.payload);
    return reply.messages.length ? <>{reply.messages.map((message, i) => <div key={message.id || i}>
      <ReplayMessage value={message} />
      {message.reasoning && <details className="replay-message-tools"><summary>Recorded reasoning</summary><ReadableContent value={message.reasoning} /></details>}
    </div>)}</> : <p>Model response recorded. Select to inspect.</p>;
  }
  return <p>{finished ? 'Result recorded. Select to inspect.' : stateAt(event, time) === 'running' ? 'Call in progress…' : 'No completed response at this position.'}</p>;
}

function FileContent({ run, entry, label }) {
  const { data, error } = useLiveJson(entry?.blob ? `/api/observe/runs/${run}/replay?blob=${entry.blob}` : null, null, false);
  return <section><h4>{label}</h4>{error && <Alert type="warning" title={error} />}
    {!entry ? <p>File does not exist at this version.</p> : entry.omitted ? <p>Content unavailable: {entry.omitted}</p>
      : entry.type === 'directory' ? <p>Directory</p> : !data ? <p>Loading file version…</p>
        : <>{entry.redacted && <Tag>Credentials redacted</Tag>}{data.truncated && <Tag>Preview truncated</Tag>}<pre>{data.text ?? 'Binary content'}</pre></>}
  </section>;
}

export default function CaseReplay({ run }) {
  const [reload, setReload] = useState(0);
  const data = useReplay(run, reload);
  const evaluation = useLiveJson(run ? `/api/observe/runs/${run}/evaluation` : null, reload, false);
  const sdk = evaluation.data?.process?.sdk;
  const userLabel = typeof sdk === 'string' && sdk.trim() ? `User (${sdk.trim()})` : 'User';
  const model = useMemo(() => replayModel(data.rows, data.archive), [data.rows, data.archive]);
  const [position, setPosition] = useState(null), [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1), [skipWait, setSkipWait] = useState(true);
  const [selection, setSelection] = useState(null), [file, setFile] = useState(null);
  const [network, setNetwork] = useState(false), [models, setModels] = useState(false), [tracks, setTracks] = useState(false);
  const [limit, setLimit] = useState(40);
  const time = Math.min(model.end, Math.max(model.start, position ?? model.start));
  const tail = useRef(null);
  const entries = useMemo(() => filesAt(data.archive || {}, time), [data.archive, time]);
  const active = model.events.filter(event => event.time <= time);
  const selected = active.find(event => event.id === selection);
  const feedEvents = active.filter(event => (network || event.kind !== 'http')
    && (models || event.kind !== 'chat') && event.source !== 'file');
  const visible = feedEvents.slice(-limit);
  const fileEntry = entries.find(([name]) => name === file)?.[1];
  const fileEvents = active.filter(event => event.source === 'file' && event.event.changes.length);
  const changes = useMemo(() => fileEvents.flatMap(event => event.event.changes), [data.archive, time]);
  const lastChange = changes.findLast(change => change.path === file);

  useEffect(() => {
    if (!playing) return undefined;
    let previous = performance.now();
    const timer = setInterval(() => {
      const now = performance.now(), elapsed = (now - previous) * speed;
      previous = now;
      setPosition(value => advancePosition(model, value ?? model.start, elapsed, skipWait));
    }, 80);
    return () => clearInterval(timer);
  }, [playing, model, speed, skipWait]);
  useEffect(() => { if (time >= model.end) setPlaying(false); }, [time, model.end]);
  useEffect(() => { if (playing) tail.current?.scrollIntoView({ block: 'nearest' }); }, [active.length, playing]);

  const seek = value => { setPlaying(false); setPosition(value); };
  if (!run) return <Empty description="This attempt has no execution records yet." />;
  if (data.error) return <Alert type="error" title={data.error} action={<Button onClick={() => setReload(n => n + 1)}>Retry</Button>} />;
  if (!data.archive) return <p>Loading replay records…</p>;
  return <section className="case-replay" aria-label="Agent behavior replay">
    {!data.archive.available && <Alert type="info" title="No workspace recording" description="Only the saved conversation and calls can be replayed for this run." />}
    {!!data.warnings.length && <Alert type="warning" title="Recording coverage" description={data.warnings.join(' ')} />}
    <div className="replay-shell">
    <div className="replay-panels">
      <ReplayFiles entries={entries} changes={changes} latestEvent={fileEvents.at(-1)?.event}
        workspace={data.archive.manifest?.workspace} selected={file}
        onSelect={path => { setPlaying(false); setSelection(null); setFile(path); }} />
      <section className="replay-feed" aria-label="Conversation and activity">
        <div className="replay-feed-title"><h3>Conversation</h3><div className="replay-feed-actions">
          <Popover trigger="click" placement="bottomRight" content={<div className="replay-options">
            <Checkbox checked={models} onChange={e => setModels(e.target.checked)}>Model calls</Checkbox>
            <Checkbox checked={network} onChange={e => setNetwork(e.target.checked)}>Network calls</Checkbox>
            <Checkbox checked={skipWait} onChange={e => setSkipWait(e.target.checked)}>Skip long waits</Checkbox>
            <small>File times are observed times; brief writes may be merged.</small>
            <small>Recording: {data.archive.manifest?.status || 'not available'}</small>
          </div>}><Button type="text" size="small" icon={<SettingOutlined />} aria-label="Display options" /></Popover>
          <Button type="text" size="small" icon={<ReloadOutlined />} aria-label="Refresh records" onClick={() => { setPlaying(false); setReload(n => n + 1); }} />
        </div></div>
        <div className="replay-messages">
        {feedEvents.length > limit && <Button size="small" onClick={() => setLimit(n => n + 40)}>Show earlier events</Button>}
        {visible.map(event => {
          const inspect = () => { setPlaying(false); setFile(null); setSelection(event.id); };
          if (event.kind === 'judge') return <EventContent key={event.id} run={run} event={event} time={time} onInspect={inspect} />;
          const user = event.kind === 'input';
          const message = ['input', 'output', 'chat'].includes(event.kind);
          const Icon = user ? UserOutlined : message ? RobotOutlined : event.kind === 'http' ? GlobalOutlined : ToolOutlined;
          const status = stateAt(event, time);
          return <article key={event.id} aria-label={user ? 'User message' : message ? 'Agent message' : event.title}
            className={`replay-event ${message ? `replay-message replay-${user ? 'user' : 'agent'}` : 'replay-activity'} ${selected?.id === event.id ? 'selected' : ''}`}>
            <button type="button" className="replay-event-heading" title={`View evidence: ${event.title}`}
              aria-label={`View evidence: ${user ? userLabel : message ? 'Agent' : event.title} at ${stamp(event.time - model.start)}`}
              onClick={inspect}>
              <Icon /><strong>{user ? userLabel : message ? 'Agent' : event.title}</strong>
              {event.kind === 'chat' && <span className="replay-event-context">Model</span>}
              <time>{stamp(event.time - model.start)}</time><span className="replay-evidence-link">↗</span>
            </button>
            {message && <div className="replay-message-body"><EventContent run={run} event={event} time={time} /></div>}
            {(!message || status === 'running' || status === 'failed' || event.time_basis === 'file_mtime') &&
              <small className="replay-event-status">{status}{event.time_basis === 'file_mtime' && ' · approximate time'}</small>}
          </article>;
        })}<div ref={tail} />
        {!visible.length && <p>Press Play or step forward to follow this run.</p>}
        </div>
      </section>
    </div>
    <div className="replay-controls">
      <div className="replay-transport">
        <Button type="text" size="small" aria-label="Previous event" icon={<StepBackwardOutlined />} disabled={!model.points.length || time <= model.start} onClick={() => seek(nextPosition(model.points, time, -1))} />
        <Button type="primary" size="small" aria-label={playing ? 'Pause' : 'Play'} icon={playing ? <PauseOutlined /> : <CaretRightOutlined />}
          disabled={!model.points.length} onClick={() => { if (time >= model.end) setPosition(model.start); setPlaying(value => !value); }} />
        <Button type="text" size="small" aria-label="Next event" icon={<StepForwardOutlined />} disabled={!model.points.length || time >= model.end} onClick={() => seek(nextPosition(model.points, time, 1))} />
        <span className="replay-clock">{stamp(time - model.start)} <span>/ {stamp(model.end - model.start)}</span></span>
        <Slider ariaLabelForHandle="Playback position" min={0} max={Math.max(1, model.end - model.start)} value={time - model.start}
          onChange={value => seek(model.start + value)} tooltip={{ formatter: value => stamp(value) }} />
        <Select aria-label="Playback speed" size="small" variant="borderless" value={speed} onChange={setSpeed} options={[0.5, 1, 2, 4, 8].map(value => ({ value, label: `${value}×` }))} />
        <Button type="text" size="small" aria-expanded={tracks} onClick={() => setTracks(value => !value)}>Timeline {tracks ? '▴' : '▾'}</Button>
      </div>
      {tracks && <div className="replay-tracks">{lanes.map((kinds, index) => <div className="replay-track" key={labels[index]}><span>{labels[index]}</span><div>
        {model.events.filter(event => kinds.includes(event.kind)).map(event => <button key={event.id} title={`${event.title} · ${stamp(event.time - model.start)}`}
          aria-label={`Seek to ${event.title}`} onClick={() => seek(event.time)}
          className={`track-${index}`} style={{ left: `${100 * (event.time - model.start) / Math.max(1, model.end - model.start)}%`,
            width: `${Math.max(0.4, 100 * ((event.end || event.time) - event.time) / Math.max(1, model.end - model.start))}%` }} />)}
        <i style={{ left: `${100 * (time - model.start) / Math.max(1, model.end - model.start)}%` }} /></div></div>)}</div>}
    </div>
    </div>
    <Drawer title={file || (selected?.kind === 'judge' ? 'Judge report' : 'Event evidence')} open={Boolean(file || selected)}
      onClose={() => { setFile(null); setSelection(null); }} size={560} rootClassName="replay-inspector">
      {file ? <><FileContent key={fileEntry?.blob || 'absent'} run={run} entry={fileEntry} label="At playback position" />
        {lastChange && <details><summary>Previous captured version</summary><FileContent key={lastChange.before?.blob || 'absent'} run={run} entry={lastChange.before} label="Before this change" /></details>}</>
        : <EventContent key={selected?.id || 'none'} run={run} event={selected} time={time} details />}
    </Drawer>
  </section>;
}
