import { useState } from 'react';
import { Alert, Descriptions, Pagination, Space, Tabs, Tag, Button } from 'antd';
import useLiveJson from '../useLiveJson.js';
import JsonValue from './JsonValue.jsx';
import { requestMessages, responseMessages } from './protocols.js';

export function Messages({ messages }) {
  if (!messages.length) return <p>This record contains no recognized chat messages. View the structured data or raw records instead.</p>;
  return <div className="conversation">{messages.map((m, i) => <article className="message" key={m.id || i}>
    <div className="message-heading"><Tag color={m.role === 'tool' ? 'orange' : m.role === 'assistant' ? 'green' : 'blue'}>{m.role}</Tag>
      {m.tool_call_id && <code>{m.tool_call_id}</code>}</div>
    {m.content !== '' && m.content != null && (typeof m.content === 'string' ? <div className="message-text">{m.content}</div> : <JsonValue value={m.content} label="Message content" />)}
    {m.reasoning && <JsonValue value={m.reasoning} label="Recorded reasoning" />}
    {m.tool_calls?.map((tool, j) => <section className="tool-message" key={tool.id || j}><Tag color="orange">Tool call · request</Tag>
      <strong>{tool.function?.name || tool.name || 'Unnamed tool'}</strong><code>{tool.id}</code>
      <JsonValue value={tool.function?.arguments ?? tool.arguments ?? tool} label="Tool arguments" />
      <small>This is the tool call requested by the model. See the Tool execution record for the actual result.</small></section>)}
  </article>)}</div>;
}

function OriginalRecords({ endpoint, revision, live, section = 'records' }) {
  const [page, setPage] = useState(1), [size, setSize] = useState(10);
  const { data, error } = useLiveJson(`${endpoint}&section=${section}&page=${page}&page_size=${size}`, revision, live);
  return <>{section === 'records' && <p>Raw events are retained in full, including each chunk's sequence number, byte count, and duration.</p>}{error && <Alert type="error" title={error} />}
    <Pagination current={page} pageSize={size} total={data?.total || 0} showSizeChanger showQuickJumper pageSizeOptions={[10, 20, 50, 100]}
      onChange={(p, s) => { setPage(s === size ? p : 1); setSize(s); }} />
    {data?.records.map(r => <JsonValue key={`${r.file}:${r.line}`} label={r.line == null ? r.file : `${r.file}:${r.line}`} value={r.raw} />)}</>;
}

export default function InteractionDetails({ run, id, revision, live, onNavigate }) {
  const endpoint = `/api/observe/runs/${run}/interactions?id=${id}`;
  const { data: d, error } = useLiveJson(endpoint, revision, live);
  if (error) return <Alert type="error" title={error} />;
  if (!d) return <p>Loading the complete interaction…</p>;
  const reply = responseMessages(d.response?.client_payload ?? d.response?.payload);
  const request = requestMessages(d.request?.payload);
  const context = d.context;
  const tabs = [
    { key: 'messages', label: 'Interaction content', children: <>
      {d.kind === 'chat' ? <><h3>Agent → LLM</h3><Messages messages={request} />
        <h3>{d.response?.client_payload ? 'LLM → Agent · client response' : 'LLM response · upstream record'}</h3><Messages messages={reply.messages} />
        {!d.response?.client_payload && <p>The upstream response is shown here; a separate client conversion result was not recorded.</p>}
        {!reply.parsed && <JsonValue value={d.response?.payload} label="Response (unrecognized protocol)" />}
        {reply.usage && <JsonValue value={reply.usage} label="Token / Usage" />}</>
        : d.artifact_file ? <>
          {d.artifact?.file_evidence && <><h3>File changes</h3>
            <Tag color={d.artifact.file_evidence.complete ? 'green' : 'orange'}>{d.artifact.file_evidence.complete ? 'Complete' : 'Partial'}</Tag>
            {d.artifact.file_evidence.changes.map((file, i) => <section key={i}><h4>{file.change_type} · {file.path}</h4>
              {file.diff ? <pre>{file.diff}</pre> : <p>{file.reason || 'No text diff supplied'}</p>}</section>)}</>}
          {typeof d.artifact?.content === 'string' && <pre>{d.artifact.content}</pre>}
          <JsonValue label={d.artifact_file} value={d.artifact} /></>
        : <><JsonValue label="Input / request" value={d.request?.payload ?? d.request?.input ?? d.request} />
          <JsonValue label="Output / response" value={d.response?.payload ?? d.response?.output ?? d.response} /></>}
    </> },
    { key: 'request', label: 'Request and response JSON', children: <>
      <JsonValue label="Emitted tool relationships" value={d.tool_relations} />
      <JsonValue label="Original Agent request (before conversion)" value={d.request?.source_payload} />
      <JsonValue label="Request actually sent" value={d.request?.payload ?? d.request} />
      <JsonValue label="Upstream response" value={d.response?.payload ?? d.response} />
      <JsonValue label="Converted client response (when recorded)" value={d.response?.client_payload} />
      {d.response?.raw_body != null && <JsonValue label="Complete raw response / SSE" value={d.response.raw_body} />}
    </> },
    { key: 'flow', label: 'Case data flow', children: context ? <>
      <Alert type="info" title={`Link evidence: ${d.link_evidence === 'framework_span_id' ? "the network record's framework_span_id matches this Input callback ID" : d.link_evidence === 'record_input_id' ? 'a unique input_id / case_id match in the record envelope' : d.link_evidence === 'native_response_id' ? 'native inspector response ID matches this Input and network response' : d.link_evidence === 'emitted_tool_id' ? 'new response tool IDs match this Input’s recorded tool calls' : 'the artifact directory for the same Input'}`} />
      <p>This confirms only that the records are linked. The field matches below separately show whether content entered the model request.</p>
      {d.input_matches.length ? <Alert type="success" title="Found the complete Input value in the request actually sent" description={d.input_matches.map(m => <div key={m.path}><code>{m.path}</code> · {m.method === 'exact_value' ? 'exact value match' : 'contains the complete original text'}</div>)} />
        : <Alert type="warning" title="No complete Input value match found" description="The input may have been transformed, used only in part, or omitted from the captured request. This alone does not prove an omission." />}
      <div className="flow-path">SDK Input → Agent Input → this interaction → Agent Output → SDK Submission</div>
      <JsonValue label="SDK Case" value={context.case} /><JsonValue label="SDK Input" value={context.input} /><JsonValue label="Mapped Input" value={context.mapped} />
      <JsonValue label="Agent invocation envelope" value={context.invocation} /><JsonValue label="Final Agent result" value={context.result} />
      <JsonValue label="Submission snapshot received by the SDK" value={context.submission} />
      <Space wrap>{d.related.map(row => <Button key={row.id} onClick={() => onNavigate(row.id)}>{row.title}</Button>)}</Space>
    </> : <Alert type="warning" title="Insufficient ID evidence to link this record to an Input" description="The record remains unlinked; proximity in time or matching tool names are not used as evidence." /> },
    { key: 'callbacks', label: `Framework callbacks${d.callbacks.count ? ` (${d.callbacks.count})` : ''}`, children: <>
      <p>Framework callback input and output are shown separately from the data actually sent over the network. SDK submissions appear under Case data flow.</p>
      <JsonValue label="Callback input" value={d.callbacks.input ?? d.request?.input} />
      <JsonValue label="Callback output" value={d.callbacks.output ?? d.response?.output} />
      {d.callbacks.count > 0 && <OriginalRecords endpoint={endpoint} revision={revision} live={live} section="callbacks" />}
    </> },
    { key: 'raw', label: `Raw records (${d.record_count})`, children: <OriginalRecords endpoint={endpoint} revision={revision} live={live} /> },
  ];
  return <div className="interaction-detail">
    {d.optional_operation && d.status === 'failed' && <Alert type="warning" title="Optional service operation failed" description="This is separate from the main model request status. The original HTTP failure remains in the evidence." />}
    {d.completeness === 'legacy_address_only' && <Alert type="warning" title="The legacy record contains only an address" description="Without a call_id, request body, or response body, the complete network interaction cannot be reconstructed. Rebuild the runtime image before collecting new records." />}
    {d.completeness === 'missing_response' && <Alert type="info" title="No response has been recorded yet" description="The call may still be running, or collection may have ended before it completed." />}
    <Descriptions size="small" column={2} items={[
      { key: 'time', label: 'Start time', children: d.timestamp || 'Not recorded' },
      { key: 'basis', label: 'Time basis', children: d.time_basis === 'file_mtime' ? 'File modification time (not an exact event time)' : 'Collection timestamp' },
      { key: 'id', label: 'Call / Span', children: <code>{d.call_id || d.framework_span_id || 'Not recorded'}</code> },
      { key: 'purpose', label: 'Purpose', children: [d.purpose, d.purpose_evidence].filter(Boolean).join(' · ') || 'Unknown' },
      { key: 'session', label: 'Native session', children: d.native_session_id || 'Unknown' },
      { key: 'case', label: 'Case', children: d.case_id || 'Unknown' },
      { key: 'input', label: 'Input', children: d.input_id || 'Unlinked' },
      { key: 'association', label: 'Association', children: d.association_status || d.link_evidence || 'Unknown' },
    ]} />
    <Tabs items={tabs} destroyOnHidden />
  </div>;
}
