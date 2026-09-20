import { useEffect, useState } from 'react';
import { Alert, Button, ConfigProvider, DatePicker, Drawer, Input, Pagination, Select, Space, Switch, Table, Tag } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import useLiveJson from './useLiveJson.js';
import InteractionDetails from './interactions/InteractionDetails.jsx';
import './interactions/interactions.css';

const labels = { chat: 'Chat', tool: 'Tool execution', tool_call: 'Tool call',
  callback: 'Framework callback', http: 'HTTP', sdk: 'SDK evaluation', case: 'Case generation',
  input: 'Input', output: 'Output', submission: 'Submission', judge: 'Judge', event: 'Other event' };
const colors = { chat: 'blue', tool: 'orange', tool_call: 'gold', callback: 'purple', http: 'default', sdk: 'cyan', case: 'geekblue', input: 'cyan', output: 'green', submission: 'volcano', judge: 'green' };
const states = { complete: 'Completed', failed: 'Failed', pending: 'Waiting for response', recorded: 'Recorded', unknown: 'Insufficient information' };
const primary = ['chat', 'tool', 'http', 'sdk', 'case', 'input', 'output', 'submission', 'judge'];

function Page({ url, revision, live, page, size, onPage, onSelect, onFacets }) {
  const { data, error } = useLiveJson(url, revision, live);
  const [snapshot, setSnapshot] = useState(null);
  useEffect(() => { if (data && !snapshot) setSnapshot(data); }, [data, snapshot]);
  useEffect(() => { if (data) onFacets(data); }, [data, onFacets]);
  const changed = data && snapshot && data.revision !== snapshot.revision;
  const columns = [
    { title: 'Time / relative start', dataIndex: 'timestamp', width: 168, render: (value, row) => {
      const date = new Date(value), origin = new Date(snapshot?.origin);
      return <div className="call-time" title={value || 'No timestamp'}><time>{value ? date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, fractionalSecondDigits: 3 }) : 'Not recorded'}</time>
        <small>{value && snapshot?.origin ? `+${((date - origin) / 1000).toFixed(3)}s` : 'Unknown time'}{row.time_basis === 'file_mtime' ? ' · file time' : ''}</small></div>;
    } },
    { title: 'Interaction', dataIndex: 'title', render: (title, row) => <div className="call-title"><Space size={[0, 4]} wrap>{row.tags.map(tag => <Tag key={tag} color={colors[tag]}>{labels[tag] || tag}</Tag>)}</Space>
      <Button type="link" className="call-open" onClick={() => onSelect(row.id)}>{title}</Button>
      <small>{row.chunk_count ? `${row.chunk_count} streaming chunks · ` : ''}{row.record_count} raw records{row.completeness === 'legacy_address_only' ? ' · legacy record contains only an address' : ''}</small></div> },
    { title: 'Input link', dataIndex: 'input_id', width: 145, render: (value, row) => <div><code>{value || 'Not linked'}</code><small className="cell-note">{row.link_evidence === 'framework_span_id' ? 'Span ID matched' : row.link_evidence === 'record_input_id' ? 'Input ID matched' : row.link_evidence ? 'Same Input directory' : row.case_id ? 'Case known · Input unknown' : 'No explicit ID evidence'}</small></div> },
    { title: 'Duration', dataIndex: 'duration_ms', width: 90, render: value => value == null ? '—' : value < 1000 ? `${value.toFixed(0)} ms` : `${(value / 1000).toFixed(2)} s` },
    { title: 'Status', dataIndex: 'status', width: 108, render: value => <Tag color={value === 'failed' ? 'red' : value === 'complete' ? 'green' : 'default'}>{states[value] || value}</Tag> },
  ];
  return <>
    {error && <Alert type="error" title={error} description="Existing data was retained. Refresh to retry." />}
    {changed && <Alert className="update-banner" type="info" title={`Run records changed${data.total_records > snapshot.total_records ? ` · ${data.total_records - snapshot.total_records} new raw events` : ''}`}
      action={<Button size="small" onClick={() => setSnapshot(data)}>Load updates</Button>} description="The current page and viewing position stay unchanged. Changing pages or filters loads the latest records." />}
    {snapshot?.warnings?.length > 0 && <Alert type="warning" title={`${snapshot.warnings.length} collection warnings`} description={snapshot.warnings.join('\n')} />}
    <Table className="call-table" rowKey="id" columns={columns} dataSource={snapshot?.items || []} loading={!snapshot && !error}
      pagination={false} size="middle" scroll={{ x: 820, y: 'max(260px, calc(100vh - 520px))' }} locale={{ emptyText: 'No interactions match the current filters. Adjust filters or wait for collection.' }} />
    <div className="call-pagination"><Pagination current={page} pageSize={size} total={snapshot?.total || 0} showSizeChanger showQuickJumper
      pageSizeOptions={[10, 20, 50, 100]} showTotal={(total, range) => `${range[0]}–${range[1]} of ${total} interactions`}
      onChange={onPage} /></div>
  </>;
}

export default function RawRunView({ run, revision }) {
  const [page, setPage] = useState(1), [size, setSize] = useState(20), [live, setLive] = useState(true);
  const [kinds, setKinds] = useState(primary), [query, setQuery] = useState(''), [input, setInput] = useState('');
  const [inputScope, setInputScope] = useState('');
  const [status, setStatus] = useState(''), [dates, setDates] = useState(null), [selected, setSelected] = useState(null);
  const [facets, setFacets] = useState(null), [refresh, setRefresh] = useState(0);
  const params = new URLSearchParams({ page, page_size: size, kinds: kinds.join(','), q: query, input_id: input, input_scope: inputScope, status });
  if (dates?.[0]) params.set('start', dates[0].toISOString());
  if (dates?.[1]) params.set('end', dates[1].toISOString());
  const url = `/api/observe/runs/${run}/interactions?${params}`;
  const reset = setter => value => { setter(value); setPage(1); };
  return <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: '#244d3d', borderRadius: 6, fontSize: 13 }, components: { Table: { cellPaddingBlock: 12 } } }}>
    <section className="interaction-timeline">
      <div className="interaction-heading"><div><h2>Interaction timeline</h2><p>Trace data from Case generation through models, tools, and submission using recorded times and IDs.</p></div>
        <Space><span>Check for updates</span><Switch checked={live} onChange={setLive} aria-label="Check for live updates" /><Button onClick={() => setRefresh(r => r + 1)}>Refresh</Button></Space></div>
      <div className="interaction-counts"><span>{facets?.total_interactions ?? '—'} interactions</span><span>from {facets?.total_records ?? '—'} raw events</span>
        <span>Local timezone · chronological order · streaming chunks grouped by call_id</span></div>
      <Space className="interaction-presets" wrap>
        <Button size="small" onClick={() => { setKinds(primary); setPage(1); }}>Primary interactions</Button>
        {['chat', 'tool', 'http', 'sdk', 'submission'].map(kind => <Button size="small" key={kind}
          type={kinds.length === 1 && kinds[0] === kind ? 'primary' : 'default'}
          onClick={() => { setKinds([kind]); setPage(1); }}>{labels[kind]} · {facets?.kinds?.[kind] || 0}</Button>)}
      </Space>
      <div className="interaction-filters">
        <Input.Search allowClear placeholder="Search messages, JSON, tools, or IDs" onSearch={reset(setQuery)} aria-label="Search interactions" />
        <Select mode="multiple" allowClear value={kinds} onChange={reset(setKinds)} maxTagCount="responsive" placeholder="All interaction types" aria-label="Interaction type"
          options={[...new Set([...Object.keys(facets?.kinds || {}), ...primary, 'callback', 'tool_call'])].map(value => ({ value, label: labels[value] || value }))} />
        <Select allowClear value={input || undefined} onChange={reset(v => { setInput(v || ''); setInputScope(''); })} placeholder="All Inputs" aria-label="Select Input"
          options={(facets?.inputs || []).filter(i => i.input_id).map(i => ({ value: i.input_id, label: i.input_id }))} />
        <Select allowClear value={status || undefined} onChange={reset(v => setStatus(v || ''))} placeholder="All statuses" aria-label="Interaction status"
          options={Object.entries(states).map(([value, label]) => ({ value, label }))} />
        <DatePicker.RangePicker showTime onChange={reset(setDates)} placeholder={['Start time', 'End time']} />
        <Button onClick={() => { setKinds([]); setPage(1); }}>Include all callbacks</Button>
      </div>
      {input && facets?.unassigned_request_count > 0 && <Alert type="warning"
        title={`${facets.unassigned_request_count} requests in this Case have no confirmed Input`}
        description={inputScope ? 'Showing requests whose Input is unknown.' : 'These requests are outside the selected Input results.'}
        action={<Button onClick={() => { setInputScope(inputScope ? '' : 'unassigned'); setPage(1); }}>{inputScope ? 'Show selected Input' : 'Show unassigned requests'}</Button>} />}
      <Page key={`${url}:${refresh}`} url={url} revision={revision} live={live} page={page} size={size} onFacets={setFacets}
        onPage={(p, s) => { setPage(size === s ? p : 1); setSize(s); }} onSelect={setSelected} />
      <Drawer className="interaction-drawer" title="Interaction details" open={Boolean(selected)} size="large" onClose={() => setSelected(null)} destroyOnHidden>
        {selected && <InteractionDetails key={selected} run={run} id={selected} revision={revision} live={live} onNavigate={setSelected} />}
      </Drawer>
    </section>
  </ConfigProvider>;
}
