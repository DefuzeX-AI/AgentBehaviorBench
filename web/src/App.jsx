import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { eventIdentity, parseTrace, sortEvents } from './trace.js';
import RunSidebar from './RunSidebar.jsx';
import TraceView from './otel/TraceView.jsx';
import EvaluationView from './evaluation/EvaluationView.jsx';
const RawRunView = lazy(() => import('./RawRunView.jsx'));
const FlowPrototype = lazy(() => import('./flow-prototype/FlowPrototype.jsx'));
import useLiveJson from './useLiveJson.js';
import useSuiteLive from './suite/useSuiteLive.js';
import SuiteOverview from './suite/SuiteOverview.jsx';

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
  const suite = useSuiteLive(suiteEndpoint, revision);
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
      setWarnings(['Run result is missing the events array']);
      return;
    }
    const parsed = parseTrace(JSON.stringify(suite.data.events), 'Current Suite');
    setEvents(sortEvents(parsed.events));
    setWarnings([...parsed.warnings, ...(suite.data.parse_errors || []).map(error => error.message)]);
    setFiles(['Current Suite']);
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
        nextWarnings.push(`${file.name}: skipped because this import exceeds 20 MB.`);
        continue;
      }
      try {
        const parsed = parseTrace(await file.text(), file.name);
        nextEvents.push(...parsed.events.map(event => ({ ...event, id: `${index}:${event.id}` })));
        nextWarnings.push(...parsed.warnings);
        names.push(file.name);
      } catch {
        nextWarnings.push(`${file.name}: unable to read file.`);
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
    <RunSidebar runs={runs} jobs={suite.data?.jobs || catalog.data?.jobs || []} selected={selected} busy={listBusy} error={listError}
      onSelect={id => { setImported(false); setView(current => current === 'flow' ? 'flow' : 'otel'); if (id === selected) setRevision(value => value + 1); else setSelected(id); }}
      onRefresh={() => setRevision(value => value + 1)} />
    <main>
      <header>
        <div><div className="brand">AGENT BEHAVIOR BENCH</div><h1>{bound ? 'Benchmark' : 'Trace'}</h1></div>
        <button className="primary" onClick={() => input.current.click()} disabled={loading}>
          {loading ? 'Reading…' : 'Open trace files'}
        </button>
        <input ref={input} type="file" multiple accept=".jsonl,.json" hidden
          onChange={event => { loadFiles(Array.from(event.target.files)); event.target.value = ''; }} />
      </header>
      <p className="description">{bound ? `Suite ${suite.data?.suite_id || 'loading'} · syncs every second. Expand Cases to compare attempts and Judge results.` : selected ? `Run ${selected}: choose a view below to inspect its records.` : 'Select a run on the left to load it automatically, or open trace files manually.'}</p>
      {suite.error && <p role="alert">{suite.error}; displayed data is retained and will resume syncing when the connection recovers.</p>}
      {suite.data?.suite_error && <p role="alert">{suite.data.suite_error.message}</p>}

      <nav className="trace-tabs" aria-label="Trace views">{bound && <button aria-pressed={view === 'suite'} onClick={() => { setImported(false); setView('suite'); }}>Suite progress</button>}<button aria-pressed={view === 'otel'} onClick={() => setView('otel')}>OTel call tree</button><button aria-pressed={view === 'evaluation'} onClick={() => setView('evaluation')}>Case / SDK / Judge</button><button aria-pressed={view === 'raw'} onClick={() => setView('raw')}>Interaction timeline</button><button aria-pressed={view === 'flow'} onClick={() => { setView('flow'); const url = new URL(location.href); const hash = new URLSearchParams(url.hash.slice(1)); hash.set('view', 'flow'); url.hash = hash.toString(); history.replaceState(null, '', url); }}>Execution flow · prototype</button></nav>
      {view !== 'suite' && !selected && !imported && <p role="status">{listBusy ? 'Reading run directory…' : listError ? `Run directory unavailable: ${listError}` : 'This result does not identify a viewable evidence directory. It may not exist yet or the source did not provide it; use Suite progress to inspect saved inputs and verdicts.'}</p>}
      {view !== 'suite' && Object.entries(runMetadata.data?.evidence_availability || {}).filter(([, value]) => value.status !== 'available').map(([kind, value]) => <p role="status" key={kind}>{kind}: {value.status}{value.reason ? ` — ${value.reason}` : ''}</p>)}
      {view !== 'suite' && runMetadata.data?.artifacts?.received_report?.host_accepted === false && <p role="alert">
        Judge report retained ({runMetadata.data.artifacts.received_report.status}), but the host rejected this execution.
        Open “Case / SDK / Judge” for the original report. Rejection reason: {runMetadata.data.error || 'inspect the run diagnostics'}.
      </p>}
      {view === 'suite' ? <SuiteOverview /> : view === 'flow' ? <Suspense fallback={<p>Loading execution flow…</p>}><FlowPrototype key={selected} run={selected} revision={revision} /></Suspense> : view === 'otel' ? <TraceView run={selected} revision={revision} /> : view === 'evaluation' ? <EvaluationView run={selected} revision={revision} /> : view === 'raw' && selected ? <Suspense fallback={<p>Loading interaction timeline…</p>}><RawRunView key={selected} run={selected} revision={revision} /></Suspense> : <>
      <section className="toolbar" aria-label="Filter traces">
        <label className="search"><span className="sr-only">Search traces</span>
          <input type="search" placeholder="Search events, nodes, run IDs, or content…" value={query}
            onChange={event => { setQuery(event.target.value); setLimit(PAGE_SIZE); }} />
        </label>
        {!!eventAgents.length && <label><span className="sr-only">Agent</span><select value={agentFilter}
          onChange={event => { setAgentFilter(event.target.value); setLimit(PAGE_SIZE); }}>
          <option value="">All Agents</option>{eventAgents.map(agent => <option key={agent} value={agent}>{agent}</option>)}
        </select></label>}
        <label><span className="sr-only">Source</span><select value={source}
          onChange={event => { setSource(event.target.value); setLimit(PAGE_SIZE); }}>
          <option value="">All sources</option>
          {sources.map(item => <option key={item} value={item}>{item}</option>)}
        </select></label>
        <button onClick={clear} disabled={!files.length && !warnings.length && !loading}>Clear</button>
      </section>

      <div className="summary" role="status">
        <span>{filtered.length} / {events.length} events</span>
        <span className="filenames" title={files.join(' · ')}>{files.length ? files.join(' · ') : 'No files loaded'}</span>
      </div>

      {warnings.length > 0 && <details className="warnings" open={!events.length}><summary>{warnings.length} read warnings</summary>
        <ul>{warnings.slice(0, 100).map((warning, index) => <li key={index}>{warning}</li>)}</ul>
        {warnings.length > 100 && <p>Only the first 100 warnings are shown.</p>}
      </details>}

      {!events.length ? <section className="empty">
        <h2>{loading ? 'Loading run traces…' : selected ? 'This run has no displayable events' : 'Select a run on the left to inspect traces'}</h2>
        {selected ? <p>After the run produces traces, click “Refresh” on the left.</p> : <>
          <p>You can also open <code>framework.jsonl</code> or <code>network.jsonl</code>.</p>
          <p>Click an event to expand its full JSON. Each import is limited to 20 MB.</p>
        </>}
      </section> : !filtered.length ? <section className="empty"><h2>No matching events</h2><p>Try another keyword or source.</p></section> :
        <section className="events" aria-label="Trace event list">
          {filtered.slice(0, limit).map(event => <details className="event" key={event.id}>
            <summary>
              <span className={`event-name ${/error|fail/i.test(event.event) ? 'error' : ''}`}>{event.event}</span>
              <span className="source">{event.source}</span>
              <time dateTime={event.timestamp || undefined}>{event.timestamp || 'No timestamp'}</time>
            </summary>
            <div className="event-meta">{event.filename}{eventIdentity(event) && ` · ${eventIdentity(event)}`}</div>
            <pre>{JSON.stringify(event.raw, null, 2)}</pre>
          </details>)}
          {filtered.length > limit && <button className="more" onClick={() => setLimit(value => value + PAGE_SIZE)}>Show {Math.min(PAGE_SIZE, filtered.length - limit)} more</button>}
        </section>}
      </>}
      <footer>ABB / OBSERVE <span>{suite.data?.capabilities?.can_control ? 'Local Suite · execution and recovery progress sync automatically' : 'Local read-only · run records sync every second'}</span></footer>
    </main>
    </div>
  );
}
