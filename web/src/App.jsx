import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { eventIdentity, parseTrace, sortEvents } from './trace.js';
import RunSidebar from './RunSidebar.jsx';
import TraceView from './otel/TraceView.jsx';
import EvaluationView from './evaluation/EvaluationView.jsx';
const RawRunView = lazy(() => import('./RawRunView.jsx'));
const FlowPrototype = lazy(() => import('./flow-prototype/FlowPrototype.jsx'));
import useLiveJson from './useLiveJson.js';

const PAGE_SIZE = 100;
const MAX_BYTES = 20 * 1024 * 1024;

export default function App() {
  const suiteEndpoint = document.querySelector('meta[name="abb-result-api"]')?.content || null;
  const bound = Boolean(suiteEndpoint);
  const [events, setEvents] = useState([]);
  const [view, setView] = useState(() => {
    const requested = new URLSearchParams(window.location.hash.slice(1)).get('view');
    return ['otel', 'evaluation', 'raw', 'flow'].includes(requested) ? requested : bound ? 'suite' : 'otel';
  });
  const [imported, setImported] = useState(false);
  const [files, setFiles] = useState([]);
  const [warnings, setWarnings] = useState([]);
  const [query, setQuery] = useState('');
  const [source, setSource] = useState('');
  const [agentFilter, setAgentFilter] = useState('');
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [loading, setLoading] = useState(false);
  const input = useRef(null);
  const request = useRef(0);
  const [runs, setRuns] = useState([]);
  const [selected, setSelected] = useState(null);
  const [listBusy, setListBusy] = useState(false);
  const [listError, setListError] = useState('');
  const [revision, setRevision] = useState(0);
  const catalog = useLiveJson('/api/observe/runs', revision);
  const suite = useLiveJson(suiteEndpoint, revision);
  const runMetadata = useLiveJson(selected ? `/api/observe/runs/${selected}/metadata` : null, revision);
  useEffect(() => {
    if (catalog.data?.runs) {
      setRuns(catalog.data.runs);
      if (!imported) setSelected(previous => previous || catalog.data.default_run || catalog.data.runs[0]?.id || null);
    }
  }, [catalog.data, imported]);

  useEffect(() => {
    setListBusy(!catalog.data && !catalog.error);
    setListError(catalog.error);
  }, [catalog.data, catalog.error]);

  useEffect(() => {
    if (imported || !suite.data) return;
    if (!Array.isArray(suite.data.events)) {
      setWarnings(['运行结果缺少 events 数组']);
      return;
    }
    const parsed = parseTrace(JSON.stringify(suite.data.events), '当前 Suite');
    setEvents(sortEvents(parsed.events));
    setWarnings([...parsed.warnings, ...(suite.data.parse_errors || []).map(error => error.message)]);
    setFiles(['当前 Suite']);
  }, [suite.data, imported]);

  const sources = useMemo(() => [...new Set(events.map(event => event.source))], [events]);
  const filtered = useMemo(() => events.filter(event =>
    (!source || event.source === source) && (!agentFilter || event.agentId === agentFilter)
      && event.search.includes(query.toLowerCase()),
  ), [events, source, query, agentFilter]);
  const eventAgents = useMemo(() => [...new Set(events.map(event => event.agentId).filter(Boolean))], [events]);

  async function loadFiles(selected) {
    if (!selected.length) return;
    setImported(true);
    setSelected(null);
    setView('raw');
    const current = ++request.current;
    setLoading(true);
    const nextEvents = [];
    const nextWarnings = [];
    const names = [];
    let bytes = 0;
    for (const [index, file] of selected.entries()) {
      bytes += file.size;
      if (bytes > MAX_BYTES) {
        nextWarnings.push(`${file.name}：本次导入总大小超过 20 MB，已跳过。`);
        continue;
      }
      try {
        const parsed = parseTrace(await file.text(), file.name);
        nextEvents.push(...parsed.events.map(event => ({ ...event, id: `${index}:${event.id}` })));
        nextWarnings.push(...parsed.warnings);
        names.push(file.name);
      } catch {
        nextWarnings.push(`${file.name}：无法读取文件。`);
      }
    }
    if (request.current !== current) return;
    setEvents(sortEvents(nextEvents));
    setWarnings(nextWarnings);
    setFiles(names);
    setQuery('');
    setSource('');
    setAgentFilter('');
    setLimit(PAGE_SIZE);
    setLoading(false);
  }

  function clear() {
    setImported(false);
    setSelected(null);
    request.current += 1;
    setEvents([]);
    setFiles([]);
    setWarnings([]);
    setQuery('');
    setSource('');
    setAgentFilter('');
    setLoading(false);
  }

  return (
    <div className="workspace">
    <RunSidebar runs={runs} jobs={catalog.data?.jobs || []} selected={selected} busy={listBusy} error={listError}
      onSelect={id => { setImported(false); setView(current => current === 'flow' ? 'flow' : 'otel'); if (id === selected) setRevision(value => value + 1); else setSelected(id); }}
      onRefresh={() => setRevision(value => value + 1)} />
    <main>
      <header>
        <div><div className="brand">AGENT BEHAVIOR BENCH</div><h1>{bound ? 'Benchmark' : 'Trace'}</h1></div>
        <button className="primary" onClick={() => input.current.click()} disabled={loading}>
          {loading ? '读取中…' : '打开 trace 文件'}
        </button>
        <input ref={input} type="file" multiple accept=".jsonl,.json" hidden
          onChange={event => { loadFiles(Array.from(event.target.files)); event.target.value = ''; }} />
      </header>
      <p className="description">{bound ? `Suite ${suite.data?.suite_id || '加载中'} · 每秒自动同步。选择左侧运行查看详细执行过程。` : selected ? `Run ${selected}：选择下方视图查看运行记录。` : '从左侧选择运行记录自动加载，也可以手动打开 trace 文件。'}</p>
      {bound && <div className="summary" role="status">
        <span>{suite.data?.state === 'complete' ? '评测已结束' : suite.data?.state === 'failed' ? '执行失败或已中断' : '评测进行中'}</span>
        {suite.data?.effective_workers != null && <span>Case 并发 {suite.data.effective_workers}（配置上限 {suite.data.configured_workers}）· 共 {suite.data.total_case_count} 个 Case</span>}
        {suite.data?.summary && <span>通过 {suite.data.summary.passed} · 未通过 {suite.data.summary.failed} · 跳过 {suite.data.summary.skipped}</span>}
        {suite.data?.jobs && <span>Case 运行中 {suite.data.jobs.reduce((count, job) => count + (job.counts?.running || 0), 0)} · 排队 {suite.data.jobs.reduce((count, job) => count + (job.counts?.queued || 0), 0)}</span>}
        <span>{suite.updated ? `同步于 ${suite.updated}` : '连接中…'}</span>
      </div>}
      {suite.error && <p role="alert">{suite.error}；已显示的数据保留，连接恢复后继续同步。</p>}
      {suite.data?.suite_error && <p role="alert">{suite.data.suite_error.message}</p>}

      <nav className="trace-tabs" aria-label="Trace 视图">{bound && <button aria-pressed={view === 'suite'} onClick={() => { setImported(false); setView('suite'); }}>Suite 进度</button>}<button aria-pressed={view === 'otel'} onClick={() => setView('otel')}>OTel 调用树</button><button aria-pressed={view === 'evaluation'} onClick={() => setView('evaluation')}>Case / SDK / Judge</button><button aria-pressed={view === 'raw'} onClick={() => setView('raw')}>交互时间线</button><button aria-pressed={view === 'flow'} onClick={() => { setView('flow'); const url = new URL(location.href); const hash = new URLSearchParams(url.hash.slice(1)); hash.set('view', 'flow'); url.hash = hash.toString(); history.replaceState(null, '', url); }}>执行流程 · 原型</button></nav>
      {view !== 'suite' && !selected && !imported && <p role="status">{listBusy ? '正在读取运行目录…' : listError ? `运行目录不可用：${listError}` : '此结果没有登记可查看的证据目录。可能尚未产出，或来源未提供；请在 Suite 进度查看已保存的输入和判决。'}</p>}
      {view !== 'suite' && Object.entries(runMetadata.data?.evidence_availability || {}).filter(([, value]) => value.status !== 'available').map(([kind, value]) => <p role="status" key={kind}>{kind}: {value.status}{value.reason ? ` — ${value.reason}` : ''}</p>)}
      {view === 'flow' ? <Suspense fallback={<p>正在加载执行流程…</p>}><FlowPrototype key={selected} run={selected} revision={revision} /></Suspense> : view === 'otel' ? <TraceView run={selected} revision={revision} /> : view === 'evaluation' ? <EvaluationView run={selected} revision={revision} /> : view === 'raw' && selected ? <Suspense fallback={<p>正在加载交互时间线…</p>}><RawRunView key={selected} run={selected} revision={revision} /></Suspense> : <>
      <section className="toolbar" aria-label="筛选 trace">
        <label className="search"><span className="sr-only">搜索 trace</span>
          <input type="search" placeholder="搜索事件、节点、run ID 或内容…" value={query}
            onChange={event => { setQuery(event.target.value); setLimit(PAGE_SIZE); }} />
        </label>
        {!!eventAgents.length && <label><span className="sr-only">Agent</span><select value={agentFilter}
          onChange={event => { setAgentFilter(event.target.value); setLimit(PAGE_SIZE); }}>
          <option value="">全部 Agent</option>{eventAgents.map(agent => <option key={agent} value={agent}>{agent}</option>)}
        </select></label>}
        <label><span className="sr-only">来源</span><select value={source}
          onChange={event => { setSource(event.target.value); setLimit(PAGE_SIZE); }}>
          <option value="">全部来源</option>
          {sources.map(item => <option key={item} value={item}>{item}</option>)}
        </select></label>
        <button onClick={clear} disabled={!files.length && !warnings.length && !loading}>清空</button>
      </section>

      <div className="summary" role="status">
        <span>{filtered.length} / {events.length} 条事件</span>
        <span className="filenames" title={files.join(' · ')}>{files.length ? files.join(' · ') : '尚未载入文件'}</span>
      </div>

      {warnings.length > 0 && <details className="warnings" open={!events.length}><summary>{warnings.length} 条读取提示</summary>
        <ul>{warnings.slice(0, 100).map((warning, index) => <li key={index}>{warning}</li>)}</ul>
        {warnings.length > 100 && <p>仅展示前 100 条提示。</p>}
      </details>}

      {!events.length ? <section className="empty">
        <h2>{loading ? '正在加载任务 trace…' : selected ? '此任务暂无可显示的事件' : '选择左侧任务查看 trace'}</h2>
        {selected ? <p>运行产生 trace 后，点击左侧「刷新」重新读取。</p> : <>
          <p>也可以打开 <code>framework.jsonl</code> 或 <code>network.jsonl</code>。</p>
          <p>点击事件展开完整 JSON，单次读取总大小不超过 20 MB。</p>
        </>}
      </section> : !filtered.length ? <section className="empty"><h2>没有匹配的事件</h2><p>试试其他关键词或来源。</p></section> :
        <section className="events" aria-label="Trace 事件列表">
          {filtered.slice(0, limit).map(event => <details className="event" key={event.id}>
            <summary>
              <span className={`event-name ${/error|fail/i.test(event.event) ? 'error' : ''}`}>{event.event}</span>
              <span className="source">{event.source}</span>
              <time dateTime={event.timestamp || undefined}>{event.timestamp || '无时间戳'}</time>
            </summary>
            <div className="event-meta">{event.filename}{eventIdentity(event) && ` · ${eventIdentity(event)}`}</div>
            <pre>{JSON.stringify(event.raw, null, 2)}</pre>
          </details>)}
          {filtered.length > limit && <button className="more" onClick={() => setLimit(value => value + PAGE_SIZE)}>再显示 {Math.min(PAGE_SIZE, filtered.length - limit)} 条</button>}
        </section>}
      </>}
      <footer>ABB / OBSERVE <span>本地只读 · 运行记录每秒自动同步</span></footer>
    </main>
    </div>
  );
}
