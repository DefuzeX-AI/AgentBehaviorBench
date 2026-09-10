import { useEffect, useMemo, useState } from 'react';
import { traceTree, duration } from './tree.js';
import './trace.css';
import useLiveJson from '../useLiveJson.js';
import ExecutionGraph from './ExecutionGraph.jsx';

function Node({ span, onSelect, selected }) {
  return <li><div className="span-row">
    <button aria-pressed={selected === span.span_id} onClick={() => onSelect(span)}>
      <span>{span.name}</span><small>{duration(span)?.toFixed(1) ?? '?'} ms</small>
      {span.status?.status_code === 'ERROR' && <em>异常</em>}
    </button></div>
    {span.children.length > 0 && <details open><summary>{span.children.length} 个子步骤</summary>
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
      .then(async r => { const body = await r.json(); if (!r.ok) throw new Error(body.error || '无法读取载荷'); return body; })
      .then(body => { if (!controller.signal.aborted) setPayload(body); })
      .catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [run, span.span_id, label, span.live, span.attributes?.[`abb.${label}_ref`]]);
  return <aside className="span-details"><h3>{span.name}</h3>
    <p>{span.status?.status_code} · {duration(span)?.toFixed(1)} ms</p>
    <p className="span-id">Trace {span.trace_id}<br />Span {span.span_id}<br />父节点 {span.parent_span_id || '无'}</p>
    <div className="payload-buttons">{['input', 'output', 'error', 'metadata', 'events'].filter(k => span.attributes?.[`abb.${k}_ref`]).map(k =>
      <button key={k} aria-pressed={k === label} onClick={() => setLabel(k)}>{{ input: '输入', output: '输出', error: '异常', metadata: '元数据', events: '事件' }[k]}</button>)}</div>
    {error && <p role="alert">{error}</p>}
    {label && !error && <pre>{payload ? JSON.stringify(payload.payload, null, 2) : '读取完整载荷…'}</pre>}
    <details><summary>原始 OTel span</summary><pre>{JSON.stringify({ ...span, children: undefined }, null, 2)}</pre></details>
  </aside>;
}

export default function TraceView({ run, revision }) {
  const [selected, setSelected] = useState(null), [live, setLive] = useState(true), [mode, setMode] = useState('graph');
  const { data, error, updated } = useLiveJson(run ? `/api/observe/runs/${run}/otel` : null, revision, live);
  useEffect(() => { setSelected(null); }, [run]);
  const current = data?.spans.find(s => s.span_id === selected?.span_id && s.trace_id === selected?.trace_id) || selected;
  const roots = useMemo(() => traceTree(data?.spans || []), [data]);
  if (!run) return <section className="empty">选择左侧运行记录查看 OTel。</section>;
  if (error && !data) return <p role="alert">{error}（自动重试中）</p>;
  if (!data) return <p>正在加载 OTel 步骤索引…</p>;
  return <section aria-label="OTel 执行追踪">
    <div className="trace-tabs">
      <button onClick={() => setLive(v => !v)} aria-pressed={live}>{live ? '实时 · 每秒检查' : '已暂停'}</button>
      <button onClick={() => setMode('graph')} aria-pressed={mode === 'graph'}>执行图</button>
      <button onClick={() => setMode('tree')} aria-pressed={mode === 'tree'}>调用树</button>
      <small>最近同步 {updated || '等待中'}</small>
    </div>
    {error && <p role="alert">{error}，保留上次数据并重试。</p>}
    <p>箭头表示真实父子调用，不代表节点之间的数据依赖。新执行会显示运行中节点；旧记录只含已结束节点。</p>
    <p>{data.spans.length} 个真实 OTel spans · 载荷按需读取</p>
    {data.statuses.map(s => <p key={s.invocation}>{s.invocation}：{s.status}{s.error && ` · ${s.error}`}</p>)}
    {data.warnings.map((w,i) => <p key={i} role="alert">{w}</p>)}
    {!roots.length ? <section className="empty">此运行没有 OTel 记录。旧运行不会自动转成 OTel；请使用更新后的镜像重新执行。</section> :
      <div className={`otel-layout ${current ? 'has-selection' : ''}`}>{mode === 'graph' ? <ExecutionGraph key={run} spans={data.spans} onSelect={setSelected} /> : <ul className="span-tree">{roots.map(s => <Node key={`${s.trace_id}:${s.span_id}`} span={s} selected={selected?.span_id} onSelect={setSelected} />)}</ul>}
        {current ? <div className="detail-panel"><button onClick={() => setSelected(null)}>关闭详情 · 展开画布</button><SpanDetails key={`${run}:${current.span_id}`} run={run} span={current} /></div> : <p className="graph-hint">点击节点查看详情；滚轮缩放，拖动画布。左下角可缩放至全图。</p>}</div>}
  </section>;
}
