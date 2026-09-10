// PROTOTYPE: compare spatial map, sequence lanes, and focused reading on #view=flow.
// ?variant=A|B|C selects the design. Uses existing read-only APIs; no new trace writes.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ReactFlow, Background, Controls, Handle, Position, MarkerType } from '@xyflow/react';
import { Alert, Button, ConfigProvider, Drawer, Pagination, Select, Tag } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import InteractionDetails from '../interactions/InteractionDetails.jsx';
import JsonValue from '../interactions/JsonValue.jsx';
import { branches, descendants, elapsed, inputKey, kinds, makeModel, metrics, spanKind, statusText, time } from './model.js';
import '@xyflow/react/dist/style.css';
import '../interactions/interactions.css';
import './prototype.css';

const variants = { A: '流程地图', B: '时序泳道', C: '聚焦阅读' };
async function read(url, signal) {
  const response = await fetch(url, { signal, cache: 'no-store' });
  if (!response.ok) throw new Error(`读取失败：HTTP ${response.status}`);
  return response.json();
}

function FlowNode({ data }) {
  return <div className={`fp-node fp-${data.kind} ${data.active ? 'fp-active' : ''}`}>
    <Handle type="target" position={data.vertical ? Position.Top : Position.Left} />
    <div className="fp-node-top"><span className="fp-kind">{kinds[data.kind] || data.kind}</span><span>{data.state}</span></div>
    <strong>{data.title}</strong><p>{data.subtitle}</p>
    <div className="fp-node-bottom"><span>{data.meta}</span><span>{data.action || '查看记录 ↗'}</span></div>
    <Handle type="source" position={data.vertical ? Position.Bottom : Position.Right} />
  </div>;
}
const nodeTypes = { evidence: FlowNode };
function Canvas({ graph, onNode, onEdge, graphKey }) {
  return <div className="fp-canvas" aria-label="执行流程画布"><ReactFlow key={graphKey} nodes={graph.nodes} edges={graph.edges} nodeTypes={nodeTypes}
    fitView fitViewOptions={{ padding: 0.08, maxZoom: 1 }} minZoom={0.25} maxZoom={1.6} nodesDraggable={false} nodesConnectable={false}
    onNodeClick={(_, n) => onNode(n.data)} onEdgeClick={(_, e) => onEdge(e.data)}>
    <Background gap={22} size={1} color="#d8e2de" /><Controls showInteractive={false} />
  </ReactFlow><div className="fp-canvas-key"><span>━ 父子调用</span><span>┄ Input 关联</span><span>点节点展开 · 点连线查依据</span></div></div>;
}

function MapVariant({ model, rows, roots, focus, setFocus, inspect, inspectEdge }) {
  const [branchPage, setBranchPage] = useState(1);
  useEffect(() => setBranchPage(1), [focus]);
  const current = model.nodes.get(focus);
  const graph = { nodes: [], edges: [] };
  const add = (id, position, data) => graph.nodes.push({ id, position, type: 'evidence', data });
  const spanData = n => {
    const count = metrics(n);
    return { title: n.span.name, subtitle: `${count.chats} 次关联 Chat · ${count.tools} 次 Tool`, meta: `${count.spans} 个 span`,
      state: n.span.live ? '执行中' : n.span.status?.status_code === 'ERROR' ? '异常' : '已结束', kind: spanKind(n), node: n, action: n.children.length ? '展开调用 →' : '查看证据 ↗' };
  };
  const visibleBranches = current ? branches(current) : [];
  if (current) {
    const children = visibleBranches.slice((branchPage - 1) * 5, branchPage * 5);
    add(current.id, { x: Math.max(0, (children.length - 1) * 140), y: 0 }, { ...spanData(current), vertical: children.length > 0, active: true, action: '查看本层证据 ↗' });
    for (const [{ target, via }, index] of children.map((v, i) => [v, i])) {
      add(target.id, { x: index * 280, y: 260 }, { ...spanData(target), vertical: true });
      const label = via.length ? `经 ${via.length} 层调用` : '直接子调用';
      graph.edges.push({ id: `${current.id}>${target.id}`, source: current.id, target: target.id, type: 'smoothstep', label,
        markerEnd: { type: MarkerType.ArrowClosed, color: '#52796a' }, style: { stroke: '#52796a', strokeWidth: 1.5 },
        data: { title: label, description: '每一跳均由同一 trace 中的 parent_span_id 证明。中间的单分支框架包装层折叠展示。',
          evidence: [current, ...via, target].map(n => ({ name: n.span.name, span_id: n.span.span_id, parent_span_id: n.span.parent_span_id, trace_id: n.span.trace_id })) } });
    }
    if (!children.length) {
      current.rows.forEach((r, i) => {
        add(r.id, { x: 405, y: i * 160 }, rowData(r));
        graph.edges.push({ id: `${current.id}>${r.id}`, source: current.id, target: r.id, type: 'smoothstep', label: 'Span ID 匹配',
          style: { stroke: '#668fba', strokeDasharray: '5 4' }, data: { title: '网络 / 回调关联', description: '交互记录的 framework_span_id 与 OTel 属性 abb.framework_span_id 相同。',
            evidence: { framework_span_id: r.framework_span_id, otel_span_id: current.span.span_id, call_id: r.call_id } } });
      });
    }
  } else {
    const groups = [
      { title: 'Case / Input', kind: 'case', rows: rows.filter(r => ['case', 'input'].includes(r.kind)) },
      { title: 'Agent 执行', kind: 'span', roots },
      { title: '输出 / 提交', kind: 'submission', rows: rows.filter(r => ['output', 'submission', 'judge'].includes(r.kind)) },
    ];
    groups.forEach((g, col) => {
      if (g.roots) g.roots.forEach((n, i) => add(n.id, { x: col * 335, y: i * 175 + 155 }, spanData(n)));
      else g.rows.forEach((r, i) => add(r.id, { x: col * 335, y: i * 165 }, rowData(r)));
    });
    for (const caseRow of rows.filter(r => r.kind === 'case' && !r.input_id && r.case_id)) {
      for (const inputRow of rows.filter(r => r.kind === 'case' && r.input_id && r.case_id === caseRow.case_id)) {
        graph.edges.push({ id: `${caseRow.id}~${inputRow.id}`, source: caseRow.id, target: inputRow.id, type: 'smoothstep',
          style: { stroke: '#9badb2', strokeDasharray: '5 5' }, data: { title: 'Case 与 Input 关联', description: '两个原始快照中的 case_id 相同。', evidence: { case_id: caseRow.case_id, input_id: inputRow.input_id } } });
      }
    }
    // These dashed, arrowless links express membership only, not data causality.
    for (const n of roots) if (n.inputKey) for (const r of rows.filter(r => ['input', 'output', 'submission', 'case'].includes(r.kind) && inputKey(r) === n.inputKey)) {
      const inbound = ['input', 'case'].includes(r.kind);
      graph.edges.push({ id: `${n.id}~${r.id}`, source: inbound ? r.id : n.id, target: inbound ? n.id : r.id, type: 'smoothstep',
        style: { stroke: '#9badb2', strokeDasharray: '5 5' }, data: { title: '同一 Input 的记录',
          description: '快照属于这个 Input；执行目录通过已匹配的 framework_span_id 关联到该 Input。虚线不表示已验证的字段传递。',
          evidence: { input_id: r.input_id, case_id: r.case_id, invocation: n.span.invocation, snapshot: r.title } } });
    }
  }
  const chain = []; let cursor = current;
  while (cursor) { chain.unshift(cursor); cursor = cursor.parent; }
  return <div className="fp-map">
    <div className="fp-map-toolbar"><div className="fp-breadcrumb"><button onClick={() => setFocus(null)}>运行概览</button>{chain.map(n => <span key={n.id}> / <button onClick={() => setFocus(n.id)}>{n.span.name}</button></span>)}</div>
      {current && <Button size="small" onClick={() => inspect({ node: current })}>本层输入 / 输出</Button>}</div>
    {!current && <div className="fp-phase-headings"><span>01 / 输入与出题</span><span>02 / Agent 调用</span><span>03 / 结果与评测</span></div>}
    <Canvas graph={graph} graphKey={`${focus}:${branchPage}:${rows.length}`} onEdge={inspectEdge} onNode={data => {
      if (data.node && data.node.id !== focus && data.node.children.length) setFocus(data.node.id);
      else inspect(data.node?.rows.length === 1 ? { row: data.node.rows[0] } : data);
    }} />
    {visibleBranches.length > 5 && <div className="fp-branch-pages"><span>同一父调用下共 {visibleBranches.length} 个分支，展开后查看完整记录</span><Pagination size="small" current={branchPage} total={visibleBranches.length} pageSize={5} showSizeChanger={false} onChange={setBranchPage} /></div>}
    {current && <div className="fp-footnote">此层包含 {metrics(current).spans} 个 span。分支按开始时间排列；左右排列不表示依次执行。</div>}
  </div>;
}

function rowData(row) {
  return { kind: row.kind, title: row.title, subtitle: time(row.timestamp), state: statusText(row.status),
    meta: row.duration_ms != null ? elapsed(row.duration_ms) : row.time_basis === 'file_mtime' ? '文件时间' : `${row.record_count} 条事件`, row };
}

function SequenceVariant({ rows, model, inspect }) {
  const [page, setPage] = useState(1), [filter, setFilter] = useState('calls');
  const records = rows.filter(r => filter === 'all' || ['chat', 'tool', 'case', 'input', 'output', 'submission', 'judge'].includes(r.kind));
  const lanes = ['SDK / 数据', 'Agent / 框架', 'LLM', 'Tools / HTTP'];
  return <div className="fp-sequence">
    <div className="fp-map-toolbar"><span>沿时间向下阅读 · 行间距不代表耗时 · 未关联的事件不画调用箭头</span>
      <Select value={filter} onChange={v => { setFilter(v); setPage(1); }} options={[{ value: 'calls', label: '主要交互' }, { value: 'all', label: '包括 HTTP' }]} /></div>
    <div className="fp-lane-head"><span>本地时间</span>{lanes.map(l => <strong key={l}>{l}</strong>)}</div>
    <div className="fp-sequence-scroll">{records.slice((page - 1) * 15, page * 15).map(r => {
      const destination = r.kind === 'chat' ? 2 : ['tool', 'http'].includes(r.kind) ? 3 : ['input', 'output'].includes(r.kind) ? 1 : 0;
      const linked = model.attached.has(r.id) && (r.kind === 'tool' || (['chat', 'http'].includes(r.kind) && r.link_evidence === 'framework_span_id'));
      return <div className="fp-sequence-row" key={r.id}><time>{time(r.timestamp)}<small>{r.time_basis === 'file_mtime' ? '文件时间' : elapsed(r.duration_ms)}</small></time>
        <div className="fp-lane-body"><div className="fp-lane-lines">{lanes.map(l => <i key={l} />)}</div>
          {linked && <svg className="fp-wire" viewBox="0 0 800 100" preserveAspectRatio="none" aria-label="请求及响应">
            <path d={`M 300 34 H ${destination === 2 ? 395 : 595} l -7 -4 m 7 4 l -7 4`} fill="none" stroke="#507caa" />
            {r.status === 'complete' && <path d={`M ${destination === 2 ? 395 : 595} 68 H 300 l 7 -4 m -7 4 l 7 4`} fill="none" stroke="#82a49a" strokeDasharray="4 3" />}
          </svg>}
          <button className={`fp-sequence-card fp-${r.kind}`} style={{ left: `${destination * 25 + 1}%` }} onClick={() => inspect({ row: r })}>
            <span className="fp-kind">{kinds[r.kind]}</span><strong>{r.title}</strong><small>{r.tags.includes('tool_call') ? '含 Tool call · ' : ''}{statusText(r.status)}{!r.link_evidence ? ' · 未关联' : ''}</small>
          </button>
        </div></div>;
    })}</div><div className="fp-sequence-pages"><Pagination current={page} pageSize={15} total={records.length} showSizeChanger={false} showQuickJumper onChange={setPage} /></div>
  </div>;
}

function FocusVariant({ model, rows, roots, inspect, run, revision }) {
  const [chosen, setChosen] = useState(null);
  const candidates = roots.flatMap(descendants);
  const node = model.nodes.get(chosen) || roots[0];
  const chain = []; let cursor = node;
  while (cursor) { chain.unshift(cursor); cursor = cursor.parent; }
  return <div className="fp-reading">
    <div className="fp-outline"><div className="fp-section-label">调用导航 / {candidates.length}</div>{candidates.map(n => <button key={n.id} className={node?.id === n.id ? 'selected' : ''} onClick={() => setChosen(n.id)}>
      <span className={`fp-kind fp-${spanKind(n)}`}>{kinds[spanKind(n)]}</span><strong>{n.span.name}</strong><small>{time(n.span.start_time)}</small></button>)}</div>
    <div className="fp-reading-main">{node ? <><div className="fp-section-label">当前焦点</div><h3>{node.span.name}</h3>
      <div className="fp-reading-path">{chain.map(n => <button key={n.id} onClick={() => setChosen(n.id)}>{n.span.name} {n.id !== node.id ? '→' : ''}</button>)}</div>
      {node.rows.length ? <InteractionDetails key={node.rows[0].id} run={run} id={node.rows[0].id} live={false} revision={revision} onNavigate={id => inspect({ row: model.rows.find(r => r.id === id) })} />
        : <SpanEvidence key={node.id} run={run} node={node} />}</> : <div className="fp-empty">没有框架调用记录。可以从下方记录区查看已采集的交互。</div>}</div>
    <div className="fp-next"><div className="fp-section-label">直接子调用 / {node?.children.length || 0}</div>{node?.children.map(n => <button key={n.id} onClick={() => setChosen(n.id)}><strong>{n.span.name}</strong><span>进入 →</span></button>)}
      {!node?.children.length && <p>已到达当前调用的末端。</p>}
      <div className="fp-section-label">关联交互</div>{node?.rows.map(r => <button key={r.id} onClick={() => inspect({ row: r })}>{kinds[r.kind]} · {r.title}</button>)}</div>
  </div>;
}

function SpanEvidence({ run, node }) {
  const [field, setField] = useState('input'), [data, setData] = useState(null), [error, setError] = useState('');
  const supported = ['input', 'output', 'error', 'metadata', 'events'].filter(k => node.span.attributes?.[`abb.${k}_ref`]);
  useEffect(() => {
    const controller = new AbortController(); setData(null); setError('');
    if (supported.includes(field)) read(`/api/observe/runs/${run}/otel/${node.span.span_id}/payload/${field}`, controller.signal).then(setData).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [run, node.id, field]);
  return <><p className="fp-footnote">{time(node.span.start_time)} — {time(node.span.end_time)} · {node.span.live ? '执行中' : '已结束'}</p>
    <div className="fp-payload-tabs">{supported.map(k => <Button key={k} type={field === k ? 'primary' : 'default'} onClick={() => setField(k)}>{{ input: '输入', output: '输出', error: '错误', metadata: '元数据', events: '事件' }[k]}</Button>)}</div>
    {error && <Alert type="error" title={error} />}
    {data ? <JsonValue label={field} value={data.payload} /> : <p className="fp-footnote">{supported.includes(field) ? '读取完整内容…' : '此字段没有记录'}</p>}
    <JsonValue label="原始 OTel span" value={node.span} /></>;
}

function PrototypeSwitcher({ variant, change }) {
  const cycle = useCallback(step => { const keys = Object.keys(variants); change(keys[(keys.indexOf(variant) + step + keys.length) % keys.length]); }, [variant, change]);
  useEffect(() => {
    const handler = e => {
      if (e.defaultPrevented || e.target.closest('input, textarea, select, button, [contenteditable="true"], [role="dialog"], .react-flow')) return;
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); cycle(e.key === 'ArrowLeft' ? -1 : 1); }
    };
    window.addEventListener('keydown', handler); return () => window.removeEventListener('keydown', handler);
  }, [cycle]);
  if (!import.meta.env.DEV) return null;
  return <div className="fp-switcher"><button aria-label="上一个设计" onClick={() => cycle(-1)}>←</button><span>UI 原型</span>{Object.entries(variants).map(([key, name]) => <button key={key} aria-pressed={variant === key} onClick={() => change(key)}>{key} / {name}</button>)}<button aria-label="下一个设计" onClick={() => cycle(1)}>→</button></div>;
}

export default function FlowPrototype({ run, revision }) {
  const [data, setData] = useState(null), [error, setError] = useState(''), [refresh, setRefresh] = useState(0);
  const [input, setInput] = useState(''), [focus, setFocus] = useState(null), [selection, setSelection] = useState(null), [edge, setEdge] = useState(null);
  const [variant, setVariant] = useState(() => new URLSearchParams(location.search).get('variant') || 'A');
  const [railPage, setRailPage] = useState(1), [railKind, setRailKind] = useState('chat');
  const change = useCallback(value => { setVariant(value); const url = new URL(location.href); url.searchParams.set('variant', value); history.replaceState(null, '', url); }, []);
  useEffect(() => {
    if (!run) return;
    const c = new AbortController(); setError('');
    (async () => {
      const base = `/api/observe/runs/${run}`;
      const [first, otel] = await Promise.all([read(`${base}/interactions?page_size=100&kinds=chat,tool,http,sdk,case,input,output,submission,judge`, c.signal), read(`${base}/otel`, c.signal)]);
      const pages = await Promise.all(Array.from({ length: Math.max(0, Math.ceil(first.total / 100) - 1) }, (_, i) => read(`${base}/interactions?page_size=100&page=${i + 2}&kinds=chat,tool,http,sdk,case,input,output,submission,judge`, c.signal)));
      const snapshots = [first, ...pages];
      const changed = new Set(snapshots.map(p => p.revision)).size > 1;
      if (!c.signal.aborted) setData({ rows: [...new Map(snapshots.flatMap(p => p.items).map(r => [r.id, r])).values()], spans: otel.spans, snapshot: first, updated: new Date(), warnings: [...first.warnings, ...otel.warnings, ...(changed ? ['读取期间记录有变化，可更新快照重新查看。'] : [])] });
    })().catch(e => { if (!c.signal.aborted) setError(e.message); });
    return () => c.abort();
  }, [run, revision, refresh]);
  const model = useMemo(() => data ? makeModel(data.rows, data.spans) : null, [data]);
  if (!run) return <div className="fp-empty">选择左侧运行记录，查看执行流程。</div>;
  if (!data) return <div className="fp-empty">{error || '正在整理真实调用与数据关联…'}</div>;
  const rows = model.rows.filter(r => !input || inputKey(r) === input);
  const roots = model.roots.filter(n => !input || n.inputKey === input);
  const detached = model.rows.filter(r => ['chat', 'tool', 'http', 'sdk'].includes(r.kind) && !model.attached.has(r.id));
  const rail = (railKind === 'unlinked' ? detached : rows.filter(r => r.kind === railKind));
  const props = { model, rows, roots, focus, setFocus, inspect: setSelection, inspectEdge: setEdge, run, revision: `${revision}:${refresh}` };
  return <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: '#285c4d', borderRadius: 6, fontSize: 13 } }}><section className="flow-prototype">
    <div className="fp-heading"><div><div className="fp-eyebrow">EXECUTION ATLAS <Tag>UI 原型</Tag></div><h2>一次运行的调用地图</h2><p>从输入进入调用，沿证据理解每一步。</p></div>
      <div className="fp-heading-actions"><small>快照 {data.updated.toLocaleTimeString()} · {run.slice(0, 8)}</small><Button onClick={() => setRefresh(n => n + 1)}>更新快照</Button></div></div>
    <div className="fp-controls"><Select aria-label="流程 Input" value={input} style={{ minWidth: 190 }} onChange={v => { setInput(v); setFocus(null); setRailPage(1); }} options={[{ value: '', label: '整个 Run' }, ...model.inputs.map(i => ({ value: i.key, label: `${i.label} · ${i.caseId?.slice(0, 13) || 'Case 未知'}` }))]} />
      <div className="fp-counts"><span><b>{data.spans.length}</b> spans</span><span><b>{data.snapshot.kinds.chat || 0}</b> Chat</span><span><b>{data.snapshot.kinds.tool || 0}</b> Tool</span><span><b>{detached.length}</b> 未关联调用</span></div>
      <Select aria-label="选择流程设计" value={variants[variant] ? variant : 'A'} onChange={change} options={Object.entries(variants).map(([value, label]) => ({ value, label: `${value} / ${label}` }))} /></div>
    {error && <Alert type="error" title={error} />}{data.warnings.length > 0 && <Alert type="warning" title={`${data.warnings.length} 条采集提示`} description={data.warnings.join('；')} />}
    {variant === 'B' ? <SequenceVariant key={input} {...props} /> : variant === 'C' ? <FocusVariant key={input} {...props} /> : <MapVariant {...props} />}
    <div className="fp-record-dock"><div className="fp-dock-heading"><div><div className="fp-section-label">证据抽屉</div><p>选择一条记录，查看消息、工具参数和 Case 字段。</p></div><Select aria-label="证据类型" value={railKind} onChange={v => { setRailKind(v); setRailPage(1); }} options={['chat', 'tool', 'case', 'input', 'output', 'submission', 'judge', 'unlinked'].map(k => ({ value: k, label: k === 'unlinked' ? `未关联调用 (${detached.length})` : kinds[k] }))} /></div>
      <div className="fp-records">{rail.slice((railPage - 1) * 4, railPage * 4).map((r, i) => <button className={`fp-record fp-${r.kind}`} key={r.id} onClick={() => setSelection({ row: r })}><div><span className="fp-kind">{kinds[r.kind]}</span><small>{String((railPage - 1) * 4 + i + 1).padStart(2, '0')}</small></div><strong>{r.title}</strong><span>{time(r.timestamp)} · {elapsed(r.duration_ms)}</span><small>{r.input_id || 'Input 未关联'} · {statusText(r.status)}</small></button>)}</div>
      {!rail.length && <p className="fp-footnote">当前范围没有此类记录。</p>}
      {rail.length > 4 && <Pagination size="small" current={railPage} total={rail.length} pageSize={4} showSizeChanger={false} onChange={setRailPage} />}
    </div>
    <Drawer className="interaction-drawer" title={edge?.title || selection?.row?.title || selection?.node?.span.name || '交互证据'} open={Boolean(selection || edge)} onClose={() => { setSelection(null); setEdge(null); }} size="large" destroyOnHidden>
      {edge ? <><p>{edge.description}</p><JsonValue label="连线依据" value={edge.evidence} /></> : selection?.row ? <InteractionDetails key={selection.row.id} run={run} id={selection.row.id} live={false} revision={`${revision}:${refresh}`} onNavigate={id => setSelection({ row: model.rows.find(r => r.id === id) })} /> : selection?.node ? <><div className="fp-payload-tabs">{selection.node.rows.map(r => <Button key={r.id} onClick={() => setSelection({ row: r })}>{kinds[r.kind]} · {r.title}</Button>)}</div><SpanEvidence key={selection.node.id} run={run} node={selection.node} /></> : null}
    </Drawer>
    <PrototypeSwitcher variant={variant} change={change} />
  </section></ConfigProvider>;
}
