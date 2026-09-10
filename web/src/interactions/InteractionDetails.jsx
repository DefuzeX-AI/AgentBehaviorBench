import { useState } from 'react';
import { Alert, Descriptions, Pagination, Space, Tabs, Tag, Button } from 'antd';
import useLiveJson from '../useLiveJson.js';
import JsonValue from './JsonValue.jsx';
import { requestMessages, responseMessages } from './protocols.js';

export function Messages({ messages }) {
  if (!messages.length) return <p>此记录没有可识别的聊天消息，请查看结构化数据或原始记录。</p>;
  return <div className="conversation">{messages.map((m, i) => <article className="message" key={m.id || i}>
    <div className="message-heading"><Tag color={m.role === 'tool' ? 'orange' : m.role === 'assistant' ? 'green' : 'blue'}>{m.role}</Tag>
      {m.tool_call_id && <code>{m.tool_call_id}</code>}</div>
    {m.content !== '' && m.content != null && (typeof m.content === 'string' ? <div className="message-text">{m.content}</div> : <JsonValue value={m.content} label="消息内容" />)}
    {m.reasoning && <JsonValue value={m.reasoning} label="记录中的 reasoning" />}
    {m.tool_calls?.map((tool, j) => <section className="tool-message" key={tool.id || j}><Tag color="orange">Tool call · 调用请求</Tag>
      <strong>{tool.function?.name || tool.name || '未命名工具'}</strong><code>{tool.id}</code>
      <JsonValue value={tool.function?.arguments ?? tool.arguments ?? tool} label="工具参数" />
      <small>这是模型发出的工具调用请求；实际执行结果请查看 Tool 执行记录。</small></section>)}
  </article>)}</div>;
}

function OriginalRecords({ endpoint, revision, live, section = 'records' }) {
  const [page, setPage] = useState(1), [size, setSize] = useState(10);
  const { data, error } = useLiveJson(`${endpoint}&section=${section}&page=${page}&page_size=${size}`, revision, live);
  return <>{section === 'records' && <p>原始事件完整保留，包括每条 chunk 的序号、字节数和耗时。</p>}{error && <Alert type="error" title={error} />}
    <Pagination current={page} pageSize={size} total={data?.total || 0} showSizeChanger showQuickJumper pageSizeOptions={[10, 20, 50, 100]}
      onChange={(p, s) => { setPage(s === size ? p : 1); setSize(s); }} />
    {data?.records.map(r => <JsonValue key={`${r.file}:${r.line}`} label={r.line == null ? r.file : `${r.file}:${r.line}`} value={r.raw} />)}</>;
}

export default function InteractionDetails({ run, id, revision, live, onNavigate }) {
  const endpoint = `/api/observe/runs/${run}/interactions?id=${id}`;
  const { data: d, error } = useLiveJson(endpoint, revision, live);
  if (error) return <Alert type="error" title={error} />;
  if (!d) return <p>正在读取完整交互…</p>;
  const reply = responseMessages(d.response?.client_payload ?? d.response?.payload);
  const request = requestMessages(d.request?.payload);
  const context = d.context;
  const tabs = [
    { key: 'messages', label: '交互内容', children: <>
      {d.kind === 'chat' ? <><h3>Agent → LLM</h3><Messages messages={request} />
        <h3>{d.response?.client_payload ? 'LLM → Agent · 客户端响应' : 'LLM 响应 · 上游记录'}</h3><Messages messages={reply.messages} />
        {!d.response?.client_payload && <p>当前展示上游响应；独立的客户端转换结果未记录。</p>}
        {!reply.parsed && <JsonValue value={d.response?.payload} label="响应（未识别的协议）" />}
        {reply.usage && <JsonValue value={reply.usage} label="Token / Usage" />}</>
        : d.artifact_file ? <JsonValue label={d.artifact_file} value={d.artifact} />
        : <><JsonValue label="输入 / 请求" value={d.request?.payload ?? d.request?.input ?? d.request} />
          <JsonValue label="输出 / 响应" value={d.response?.payload ?? d.response?.output ?? d.response} /></>}
    </> },
    { key: 'request', label: '请求与响应 JSON', children: <>
      <JsonValue label="Agent 原始请求（转换前）" value={d.request?.source_payload} />
      <JsonValue label="实际发送的请求" value={d.request?.payload ?? d.request} />
      <JsonValue label="上游响应" value={d.response?.payload ?? d.response} />
      <JsonValue label="转换后客户端响应（若有记录）" value={d.response?.client_payload} />
      {d.response?.raw_body != null && <JsonValue label="完整响应原文 / SSE" value={d.response.raw_body} />}
    </> },
    { key: 'flow', label: 'Case 数据传递', children: context ? <>
      <Alert type="info" title={`关联依据：${d.link_evidence === 'framework_span_id' ? '网络记录的 framework_span_id 与本次 Input 的回调 ID 一致' : d.link_evidence === 'payload_input_id' ? '记录中的 input_id / case_id 唯一匹配' : '同一 Input 的 artifact 目录'}`} />
      <p>这里只确认记录关联。内容是否进入模型请求，由下面的实际字段匹配单独说明。</p>
      {d.input_matches.length ? <Alert type="success" title="在实际发送的请求中找到完整 Input 值" description={d.input_matches.map(m => <div key={m.path}><code>{m.path}</code> · {m.method === 'exact_value' ? '值完全相同' : '包含完整原文'}</div>)} />
        : <Alert type="warning" title="未找到完整 Input 值匹配" description="可能经过转换、只使用了部分内容，或没有采集到请求；不能据此判断遗漏。" />}
      <div className="flow-path">SDK Input → Agent Input → 本次交互 → Agent Output → SDK Submission</div>
      <JsonValue label="SDK Case" value={context.case} /><JsonValue label="SDK Input" value={context.input} /><JsonValue label="映射后的 Input" value={context.mapped} />
      <JsonValue label="Agent 调用 envelope" value={context.invocation} /><JsonValue label="Agent 最终结果" value={context.result} />
      <JsonValue label="SDK 收到的提交快照" value={context.submission} />
      <Space wrap>{d.related.map(row => <Button key={row.id} onClick={() => onNavigate(row.id)}>{row.title}</Button>)}</Space>
    </> : <Alert type="warning" title="没有足够的 ID 证据关联到某个 Input" description="保留为未关联，不使用时间接近或相同工具名称猜测。" /> },
    { key: 'callbacks', label: `框架回调${d.callbacks.count ? ` (${d.callbacks.count})` : ''}`, children: <>
      <p>框架回调中的输入与输出，和网络实际发送的数据分别展示。SDK 提交内容位于「Case 数据传递」。</p>
      <JsonValue label="Callback 输入" value={d.callbacks.input ?? d.request?.input} />
      <JsonValue label="Callback 输出" value={d.callbacks.output ?? d.response?.output} />
      {d.callbacks.count > 0 && <OriginalRecords endpoint={endpoint} revision={revision} live={live} section="callbacks" />}
    </> },
    { key: 'raw', label: `原始记录 (${d.record_count})`, children: <OriginalRecords endpoint={endpoint} revision={revision} live={live} /> },
  ];
  return <div className="interaction-detail">
    {d.completeness === 'legacy_address_only' && <Alert type="warning" title="历史记录仅保存了地址" description="没有 call_id、请求体或响应体，无法还原完整网络交互。新采集需要重新构建运行镜像后生效。" />}
    {d.completeness === 'missing_response' && <Alert type="info" title="尚未记录响应" description="调用可能仍在执行，或本次采集未完整结束。" />}
    <Descriptions size="small" column={2} items={[
      { key: 'time', label: '开始时间', children: d.timestamp || '未记录' },
      { key: 'basis', label: '时间依据', children: d.time_basis === 'file_mtime' ? '文件更新时间（非精确事件时间）' : '采集时间戳' },
      { key: 'id', label: 'Call / Span', children: <code>{d.call_id || d.framework_span_id || '未记录'}</code> },
      { key: 'input', label: 'Input', children: d.input_id || '未关联' },
    ]} />
    <Tabs items={tabs} destroyOnHidden />
  </div>;
}
