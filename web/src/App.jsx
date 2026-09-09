import { useEffect, useMemo, useRef, useState } from 'react';
import { parseTrace, sortEvents } from './trace.js';
import RunSidebar from './RunSidebar.jsx';

const PAGE_SIZE = 100;
const MAX_BYTES = 20 * 1024 * 1024;

export default function App() {
  const [events, setEvents] = useState([]);
  const [files, setFiles] = useState([]);
  const [warnings, setWarnings] = useState([]);
  const [query, setQuery] = useState('');
  const [source, setSource] = useState('');
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [loading, setLoading] = useState(false);
  const input = useRef(null);
  const request = useRef(0);
  const [runs, setRuns] = useState([]);
  const [selected, setSelected] = useState(null);
  const [listBusy, setListBusy] = useState(false);
  const [listError, setListError] = useState('');
  const [revision, setRevision] = useState(0);
  const bound = Boolean(document.querySelector('meta[name="abb-result-api"]'));

  useEffect(() => {
    if (bound) return;
    const controller = new AbortController();
    setListBusy(true);
    fetch('/api/observe/runs', { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error('任务接口不可用，请使用 web 下的 npm run dev 或 npm run preview');
      const result = await response.json();
      if (!Array.isArray(result.runs)) throw new Error('任务接口不可用');
      if (controller.signal.aborted) return;
      setRuns(result.runs);
      setListError('');
      if (revision === 0) setSelected(previous => previous || result.runs[0]?.id || null);
    }).catch(error => { if (!controller.signal.aborted) setListError(error.message); })
      .finally(() => { if (!controller.signal.aborted) setListBusy(false); });
    return () => controller.abort();
  }, [bound, revision]);

  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    const current = ++request.current;
    setLoading(true);
    setEvents([]); setFiles([]); setWarnings([]);
    setQuery(''); setSource(''); setLimit(PAGE_SIZE);
    fetch(`/api/observe/runs/${encodeURIComponent(selected)}`, { signal: controller.signal }).then(async response => {
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || '无法读取任务');
      const parsed = result.files.map(file => parseTrace(file.content, file.name));
      if (request.current !== current || controller.signal.aborted) return;
      setEvents(sortEvents(parsed.flatMap(item => item.events)));
      setFiles(result.files.map(file => file.name));
      setWarnings([...(result.warnings || []), ...parsed.flatMap(item => item.warnings)]);
    }).catch(error => {
      if (!controller.signal.aborted && request.current === current) setWarnings([error.message]);
    }).finally(() => {
      if (!controller.signal.aborted && request.current === current) setLoading(false);
    });
    return () => controller.abort();
  }, [selected, revision]);

  useEffect(() => {
    // Only the local Python viewer injects this marker. Vite/file import mode
    // does not probe a backend or upload file contents.
    const endpoint = document.querySelector('meta[name="abb-result-api"]')?.content;
    if (!endpoint?.startsWith('/api/')) return;
    const controller = new AbortController();
    const current = ++request.current;
    setLoading(true);
    fetch(endpoint, { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const result = await response.json();
      if (!Array.isArray(result.events)) throw new Error('运行结果缺少 events 数组');
      const parsed = parseTrace(JSON.stringify(result.events), '当前运行');
      if (request.current !== current) return;
      setEvents(sortEvents(parsed.events));
      setWarnings([...parsed.warnings, ...(result.parse_errors || []).map(error => error.message)]);
      setFiles(['当前运行']);
    }).catch(error => {
      if (!controller.signal.aborted && request.current === current) setWarnings([`无法读取当前运行：${error.message}`]);
    }).finally(() => {
      if (!controller.signal.aborted && request.current === current) setLoading(false);
    });
    return () => controller.abort();
  }, []);

  const sources = useMemo(() => [...new Set(events.map(event => event.source))], [events]);
  const filtered = useMemo(() => events.filter(event =>
    (!source || event.source === source) && event.search.includes(query.toLowerCase()),
  ), [events, source, query]);

  async function loadFiles(selected) {
    if (!selected.length) return;
    setSelected(null);
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
    setLimit(PAGE_SIZE);
    setLoading(false);
  }

  function clear() {
    setSelected(null);
    request.current += 1;
    setEvents([]);
    setFiles([]);
    setWarnings([]);
    setQuery('');
    setSource('');
    setLoading(false);
  }

  return (
    <div className={bound ? '' : 'workspace'}>
    {!bound && <RunSidebar runs={runs} selected={selected} busy={listBusy} error={listError}
      onSelect={id => { if (id === selected) setRevision(value => value + 1); else setSelected(id); }}
      onRefresh={() => setRevision(value => value + 1)} />}
    <main>
      <header>
        <div><div className="brand">AGENT BEHAVIOR BENCH</div><h1>Trace</h1></div>
        <button className="primary" onClick={() => input.current.click()} disabled={loading}>
          {loading ? '读取中…' : '打开 trace 文件'}
        </button>
        <input ref={input} type="file" multiple accept=".jsonl,.json" hidden
          onChange={event => { loadFiles(Array.from(event.target.files)); event.target.value = ''; }} />
      </header>
      <p className="description">{selected ? `Run ${selected}：${loading ? '正在读取运行记录。' : files.length ? '已加载可用 trace，按时间排列。' : '暂无可用 trace。'}` : '从左侧选择运行记录自动加载，也可以手动打开 trace 文件。'}</p>

      <section className="toolbar" aria-label="筛选 trace">
        <label className="search"><span className="sr-only">搜索 trace</span>
          <input type="search" placeholder="搜索事件、节点、run ID 或内容…" value={query}
            onChange={event => { setQuery(event.target.value); setLimit(PAGE_SIZE); }} />
        </label>
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
            <div className="event-meta">{event.filename}{event.runId && ` · run ${event.runId}`}</div>
            <pre>{JSON.stringify(event.raw, null, 2)}</pre>
          </details>)}
          {filtered.length > limit && <button className="more" onClick={() => setLimit(value => value + PAGE_SIZE)}>再显示 {Math.min(PAGE_SIZE, filtered.length - limit)} 条</button>}
        </section>}
      <footer>ABB / OBSERVE <span>本地只读 · 点击刷新获取最新记录</span></footer>
    </main>
    </div>
  );
}
