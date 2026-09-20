import { ConfigProvider } from 'antd';
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { eventIdentity, parseTrace, sortEvents } from './trace.js';
import RunSidebar from './RunSidebar.jsx';
import SuiteSidebar from './navigation/SuiteSidebar.jsx';
import TraceView from './otel/TraceView.jsx';
import EvaluationView from './evaluation/EvaluationView.jsx';
import CaseDetailsPage from './cases/CaseDetailsPage.jsx';
import useLiveJson from './useLiveJson.js';
import useSuiteLive from './suite/useSuiteLive.js';
import SuiteOverview from './suite/SuiteOverview.jsx';
import { actions } from './suite/store.js';
import { normalizeCases } from './suite/model.js';

const RawRunView = lazy(() => import('./RawRunView.jsx'));
const FlowPrototype = lazy(() => import('./flow-prototype/FlowPrototype.jsx'));
const PAGE_SIZE = 100;
const MAX_BYTES = 20 * 1024 * 1024;

function setSuiteHash(item, tab = 'overview') {
  const params = new URLSearchParams();
  if (item) {
    params.set('agent', item.agent_id);
    params.set('case', String(item.case_index));
    params.set('tab', tab);
  }
  history.replaceState(null, '', `${location.pathname}${location.search}${params.size ? `#${params}` : ''}`);
}

function BoundSuiteApp({ endpoint }) {
  const dispatch = useDispatch();
  const { selectedCaseKey, detailTab } = useSelector(state => state.suite);
  const [revision, setRevision] = useState(0);
  const suite = useSuiteLive(endpoint, revision);
  const cases = useMemo(() => normalizeCases(suite.data), [suite.data]);
  const selectedCase = cases.find(item => item.key === selectedCaseKey) || null;
  const hydrated = useRef(false);

  useEffect(() => {
    if (!suite.data || hydrated.current) return;
    hydrated.current = true;
    const params = new URLSearchParams(location.hash.slice(1));
    const requested = cases.find(item => item.agent_id === params.get('agent') && item.case_index === Number(params.get('case')));
    if (requested) {
      dispatch(actions.caseSelected(requested));
      const tab = params.get('tab');
      if (['overview', 'conversation', 'tools', 'judge', 'trace', 'json'].includes(tab)) dispatch(actions.detailTabChanged(tab));
    }
  }, [cases, dispatch, suite.data]);

  useEffect(() => {
    if (hydrated.current) setSuiteHash(selectedCase, detailTab);
  }, [selectedCase, detailTab]);

  const selectCase = item => { dispatch(actions.caseSelected(item)); window.scrollTo({ top: 0, behavior: 'instant' }); };
  const selectSuite = () => { dispatch(actions.suiteSelected()); window.scrollTo({ top: 0, behavior: 'instant' }); };
  return <div className="workspace suite-workspace">
    <SuiteSidebar snapshot={suite.data} selectedCaseKey={selectedCaseKey} busy={!suite.data && !suite.error} error={suite.error}
      onSuiteSelect={selectSuite} onCaseSelect={selectCase} onRefresh={() => setRevision(value => value + 1)} />
    <main className="suite-main">
      <header className="suite-shell-header"><div><div className="brand">AGENT BEHAVIOR BENCH</div><span>{suite.data?.suite_id || 'Loading Suite'}</span></div>
        <span className="suite-live-dot"><i />Live result</span></header>
      {selectedCase ? <CaseDetailsPage item={selectedCase} revision={revision} onBack={selectSuite} /> : <SuiteOverview onCaseSelect={selectCase} />}
      <footer>ABB / OBSERVE <span>{suite.data?.capabilities?.can_control ? 'Local Suite, execution and recovery progress sync automatically' : 'Local read-only Suite'}</span></footer>
    </main>
  </div>;
}

function TraceExplorer() {
  const [events, setEvents] = useState([]);
  const [view, setView] = useState(() => {
    const requested = new URLSearchParams(window.location.hash.slice(1)).get('view');
    return ['otel', 'evaluation', 'raw', 'flow'].includes(requested) ? requested : 'otel';
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
  const [selected, setSelected] = useState(null);
  const [revision, setRevision] = useState(0);
  const catalog = useLiveJson('/api/observe/runs', revision);
  const runMetadata = useLiveJson(selected ? `/api/observe/runs/${selected}/metadata` : null, revision);
  const runs = catalog.data?.runs || [];

  useEffect(() => {
    if (!imported && runs.length) setSelected(previous => previous || catalog.data.default_run || runs[0]?.id || null);
  }, [catalog.data, imported, runs]);

  const sources = useMemo(() => [...new Set(events.map(event => event.source))], [events]);
  const filtered = useMemo(() => events.filter(event => (!source || event.source === source)
    && (!agentFilter || event.agentId === agentFilter) && event.search.includes(query.toLowerCase())), [events, source, query, agentFilter]);
  const eventAgents = useMemo(() => [...new Set(events.map(event => event.agentId).filter(Boolean))], [events]);

  async function loadFiles(selectedFiles) {
    if (!selectedFiles.length) return;
    setImported(true); setSelected(null); setView('raw'); setLoading(true);
    const current = ++request.current, nextEvents = [], nextWarnings = [], names = [];
    let bytes = 0;
    for (const [index, file] of selectedFiles.entries()) {
      bytes += file.size;
      if (bytes > MAX_BYTES) { nextWarnings.push(`${file.name}: skipped because this import exceeds 20 MB.`); continue; }
      try {
        const parsed = parseTrace(await file.text(), file.name);
        nextEvents.push(...parsed.events.map(event => ({ ...event, id: `${index}:${event.id}` })));
        nextWarnings.push(...parsed.warnings); names.push(file.name);
      } catch { nextWarnings.push(`${file.name}: unable to read file.`); }
    }
    if (request.current !== current) return;
    setEvents(sortEvents(nextEvents)); setWarnings(nextWarnings); setFiles(names);
    setQuery(''); setSource(''); setAgentFilter(''); setLimit(PAGE_SIZE); setLoading(false);
  }

  function clear() {
    setImported(false); setSelected(null); request.current += 1; setEvents([]); setFiles([]); setWarnings([]);
    setQuery(''); setSource(''); setAgentFilter(''); setLoading(false);
  }

  return <div className="workspace">
    <RunSidebar runs={runs} selected={selected} busy={!catalog.data && !catalog.error} error={catalog.error}
      onSelect={id => { setImported(false); setView(current => current === 'flow' ? 'flow' : 'otel'); if (id === selected) setRevision(value => value + 1); else setSelected(id); }}
      onRefresh={() => setRevision(value => value + 1)} />
    <main><header><div><div className="brand">AGENT BEHAVIOR BENCH</div><h1>Trace</h1></div>
      <button className="primary" onClick={() => input.current.click()} disabled={loading}>{loading ? 'Reading…' : 'Open trace files'}</button>
      <input ref={input} type="file" multiple accept=".jsonl,.json" hidden onChange={event => { loadFiles(Array.from(event.target.files)); event.target.value = ''; }} /></header>
      <p className="description">{selected ? `Run ${selected}: choose a view below to inspect its records.` : 'Select a run on the left to load it automatically, or open trace files manually.'}</p>
      <nav className="trace-tabs" aria-label="Trace views"><button aria-pressed={view === 'otel'} onClick={() => setView('otel')}>OTel call tree</button><button aria-pressed={view === 'evaluation'} onClick={() => setView('evaluation')}>Case / SDK / Judge</button><button aria-pressed={view === 'raw'} onClick={() => setView('raw')}>Interaction timeline</button><button aria-pressed={view === 'flow'} onClick={() => setView('flow')}>Execution flow</button></nav>
      {!selected && !imported && <p role="status">{!catalog.data && !catalog.error ? 'Reading run directory…' : catalog.error ? `Run directory unavailable: ${catalog.error}` : 'Select a run or open trace files.'}</p>}
      {Object.entries(runMetadata.data?.evidence_availability || {}).filter(([, value]) => value.status !== 'available').map(([kind, value]) => <p role="status" key={kind}>{kind}: {value.status}{value.reason ? `, ${value.reason}` : ''}</p>)}
      {runMetadata.data?.artifacts?.received_report?.host_accepted === false && <p role="alert">Judge report retained ({runMetadata.data.artifacts.received_report.status}), but the host rejected this execution. Rejection reason: {runMetadata.data.error || 'inspect the run diagnostics'}.</p>}
      {view === 'flow' ? <Suspense fallback={<p>Loading execution flow…</p>}><FlowPrototype key={selected} run={selected} revision={revision} /></Suspense>
        : view === 'otel' ? <TraceView run={selected} revision={revision} />
          : view === 'evaluation' ? <EvaluationView run={selected} revision={revision} />
            : view === 'raw' && selected ? <Suspense fallback={<p>Loading interaction timeline…</p>}><RawRunView key={selected} run={selected} revision={revision} /></Suspense> : <>
              <section className="toolbar" aria-label="Filter traces"><label className="search"><span className="sr-only">Search traces</span><input type="search" placeholder="Search events, nodes, run IDs, or content…" value={query} onChange={event => { setQuery(event.target.value); setLimit(PAGE_SIZE); }} /></label>
                {!!eventAgents.length && <label><span className="sr-only">Agent</span><select value={agentFilter} onChange={event => { setAgentFilter(event.target.value); setLimit(PAGE_SIZE); }}><option value="">All Agents</option>{eventAgents.map(agent => <option key={agent} value={agent}>{agent}</option>)}</select></label>}
                <label><span className="sr-only">Source</span><select value={source} onChange={event => { setSource(event.target.value); setLimit(PAGE_SIZE); }}><option value="">All sources</option>{sources.map(item => <option key={item} value={item}>{item}</option>)}</select></label><button onClick={clear}>Clear</button></section>
              <div className="summary" role="status"><span>{filtered.length} / {events.length} events</span><span className="filenames">{files.length ? files.join(' · ') : 'No files loaded'}</span></div>
              {warnings.length > 0 && <details className="warnings"><summary>{warnings.length} read warnings</summary><ul>{warnings.slice(0, 100).map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>}
              {!events.length ? <section className="empty"><h2>{loading ? 'Loading run traces…' : 'No imported trace events'}</h2><p>Open framework.jsonl or network.jsonl to inspect standalone traces.</p></section> : <section className="events">{filtered.slice(0, limit).map(event => <details className="event" key={event.id}><summary><span className={`event-name ${/error|fail/i.test(event.event) ? 'error' : ''}`}>{event.event}</span><span className="source">{event.source}</span><time>{event.timestamp || 'No timestamp'}</time></summary><div className="event-meta">{event.filename}{eventIdentity(event) && ` · ${eventIdentity(event)}`}</div><pre>{JSON.stringify(event.raw, null, 2)}</pre></details>)}</section>}
            </>}
      <footer>ABB / OBSERVE <span>Local run records</span></footer>
    </main>
  </div>;
}

export default function App() {
  const endpoint = document.querySelector('meta[name="abb-result-api"]')?.content || null;
  return <ConfigProvider theme={{ token: { colorPrimary: '#244d3d', borderRadius: 6, fontSize: 13, colorText: '#202623', colorBgLayout: '#fafbf9' }, components: { Table: { headerBg: '#f0f3ef', headerColor: '#58655c' } } }}>
    {endpoint ? <BoundSuiteApp endpoint={endpoint} /> : <TraceExplorer />}
  </ConfigProvider>;
}
