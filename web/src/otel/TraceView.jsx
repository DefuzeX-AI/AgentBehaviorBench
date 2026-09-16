import { useEffect, useMemo, useState } from 'react';
import { traceTree, duration } from './tree.js';
import './trace.css';
import useLiveJson from '../useLiveJson.js';
import ExecutionGraph from './ExecutionGraph.jsx';

function Node({ span, onSelect, selected }) {
  return <li><div className="span-row">
    <button aria-pressed={selected === span.span_id} onClick={() => onSelect(span)}>
      <span>{span.name}</span><small>{duration(span)?.toFixed(1) ?? '?'} ms</small>
      {span.status?.status_code === 'ERROR' && <em>Error</em>}
    </button></div>
    {span.children.length > 0 && <details open><summary>{span.children.length} child steps</summary>
      <ul>{span.children.map(child => <Node key={child.span_id} span={child} onSelect={onSelect} selected={selected} />)}</ul>
    </details>}</li>;
}

function SpanDetails({ run, span }) {
  const [payload, setPayload] = useState(null), [label, setLabel] = useState(''), [error, setError] = useState('');
  useEffect(() => {
    setPayload(null); setError('');
    if (!label) return;
    const controller = new AbortController();
    fetch(`/api/observe/runs/${run}/otel/${span.span_id}/payload/${label}`, { signal: controller.signal })
      .then(async r => { const body = await r.json(); if (!r.ok) throw new Error(body.error || 'Unable to read payload'); return body; })
      .then(body => { if (!controller.signal.aborted) setPayload(body); })
      .catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [run, span.span_id, label, span.live, span.attributes?.[`abb.${label}_ref`]]);
  return <aside className="span-details"><h3>{span.name}</h3>
    <p>{span.status?.status_code} · {duration(span)?.toFixed(1)} ms</p>
    <p className="span-id">Trace {span.trace_id}<br />Span {span.span_id}<br />Parent {span.parent_span_id || 'None'}</p>
    <div className="payload-buttons">{['input', 'output', 'error', 'metadata', 'events'].filter(k => span.attributes?.[`abb.${k}_ref`]).map(k =>
      <button key={k} aria-pressed={k === label} onClick={() => setLabel(k)}>{{ input: 'Input', output: 'Output', error: 'Error', metadata: 'Metadata', events: 'Events' }[k]}</button>)}</div>
    {error && <p role="alert">{error}</p>}
    {label && !error && <pre>{payload ? JSON.stringify(payload.payload, null, 2) : 'Loading complete payload…'}</pre>}
    <details><summary>Raw OTel span</summary><pre>{JSON.stringify({ ...span, children: undefined }, null, 2)}</pre></details>
  </aside>;
}

export default function TraceView({ run, revision }) {
  const [selected, setSelected] = useState(null), [live, setLive] = useState(true), [mode, setMode] = useState('graph');
  const { data, error, updated } = useLiveJson(run ? `/api/observe/runs/${run}/otel` : null, revision, live);
  useEffect(() => { setSelected(null); }, [run]);
  const current = data?.spans.find(s => s.span_id === selected?.span_id && s.trace_id === selected?.trace_id) || selected;
  const roots = useMemo(() => traceTree(data?.spans || []), [data]);
  if (!run) return <section className="empty">Select a run on the left to inspect OTel.</section>;
  if (error && !data) return <p role="alert">{error} (retrying automatically)</p>;
  if (!data) return <p>Loading the OTel step index…</p>;
  return <section aria-label="OTel execution trace">
    <div className="trace-tabs">
      <button onClick={() => setLive(v => !v)} aria-pressed={live}>{live ? 'Live · checks every second' : 'Paused'}</button>
      <button onClick={() => setMode('graph')} aria-pressed={mode === 'graph'}>Execution graph</button>
      <button onClick={() => setMode('tree')} aria-pressed={mode === 'tree'}>Call tree</button>
      <small>Last synced {updated || 'waiting'}</small>
    </div>
    {error && <p role="alert">{error}; retaining the last data and retrying.</p>}
    <p>Arrows show real parent-child calls, not data dependencies between nodes. New executions show running nodes; older records contain only completed nodes.</p>
    <p>{data.spans.length} real OTel spans · payloads loaded on demand</p>
    {data.statuses.map(s => <p key={s.invocation}>{s.invocation}: {s.status}{s.error && ` · ${s.error}`}</p>)}
    {data.warnings.map((w,i) => <p key={i} role="alert">{w}</p>)}
    {!roots.length ? <section className="empty">This run has no OTel records. Older runs are not converted automatically; rerun with the updated image.</section> :
      <div className={`otel-layout ${current ? 'has-selection' : ''}`}>{mode === 'graph' ? <ExecutionGraph key={run} spans={data.spans} onSelect={setSelected} /> : <ul className="span-tree">{roots.map(s => <Node key={`${s.trace_id}:${s.span_id}`} span={s} selected={selected?.span_id} onSelect={setSelected} />)}</ul>}
        {current ? <div className="detail-panel"><button onClick={() => setSelected(null)}>Close details · expand canvas</button><SpanDetails key={`${run}:${current.span_id}`} run={run} span={current} /></div> : <p className="graph-hint">Select a node for details. Use the wheel to zoom and drag the canvas. The lower-left control fits the full graph.</p>}</div>}
  </section>;
}
