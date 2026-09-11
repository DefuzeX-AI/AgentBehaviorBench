import { useEffect, useState } from 'react';
import { Alert, Button, ConfigProvider, DatePicker, Drawer, Input, Pagination, Select, Space, Switch, Table, Tag } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import useLiveJson from './useLiveJson.js';
import InteractionDetails from './interactions/InteractionDetails.jsx';
import './interactions/interactions.css';

const labels = { chat: 'Chat · 聊天', tool: 'Tool · 工具执行', tool_call: 'Tool call · 调用请求',
  callback: 'Callback · 框架回调', http: 'HTTP · 网络', sdk: 'SDK · 评测服务', case: 'Case · 出题',
  input: 'Input · 输入', output: 'Output · 输出', submission: 'Submission · 提交', judge: 'Judge · 判分', event: '其他事件' };
const colors = { chat: 'blue', tool: 'orange', tool_call: 'gold', callback: 'purple', http: 'default', sdk: 'cyan', case: 'geekblue', input: 'cyan', output: 'green', submission: 'volcano', judge: 'green' };
const states = { complete: '已完成', failed: '失败', pending: '等待响应', recorded: '已记录', unknown: '信息不足' };
const primary = ['chat', 'tool', 'http', 'sdk', 'case', 'input', 'output', 'submission', 'judge'];

function Page({ url, revision, live, page, size, onPage, onSelect, onFacets }) {
  const { data, error } = useLiveJson(url, revision, live);
  const [snapshot, setSnapshot] = useState(null);
  useEffect(() => { if (data && !snapshot) setSnapshot(data); }, [data, snapshot]);
  useEffect(() => { if (data) onFacets(data); }, [data, onFacets]);
  const changed = data && snapshot && data.revision !== snapshot.revision;
  const columns = [
    { title: '时间 / 相对开始', dataIndex: 'timestamp', width: 168, render: (value, row) => {
      const date = new Date(value), origin = new Date(snapshot?.origin);
      return <div className="call-time" title={value || '没有时间戳'}><time>{value ? date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, fractionalSecondDigits: 3 }) : '未记录'}</time>
        <small>{value && snapshot?.origin ? `+${((date - origin) / 1000).toFixed(3)}s` : '时间未知'}{row.time_basis === 'file_mtime' ? ' · 文件时间' : ''}</small></div>;
    } },
    { title: '交互', dataIndex: 'title', render: (title, row) => <div className="call-title"><Space size={[0, 4]} wrap>{row.tags.map(tag => <Tag key={tag} color={colors[tag]}>{labels[tag] || tag}</Tag>)}</Space>
      <Button type="link" className="call-open" onClick={() => onSelect(row.id)}>{title}</Button>
      <small>{row.chunk_count ? `${row.chunk_count} 个流式片段 · ` : ''}{row.record_count} 条原始记录{row.completeness === 'legacy_address_only' ? ' · 历史记录仅含地址' : ''}</small></div> },
    { title: 'Input 关联', dataIndex: 'input_id', width: 145, render: (value, row) => <div><code>{value || '未关联'}</code><small className="cell-note">{row.link_evidence === 'framework_span_id' ? 'Span ID 已匹配' : row.link_evidence === 'payload_input_id' ? 'Input ID 已匹配' : row.link_evidence ? '同一 Input 目录' : '无明确 ID 证据'}</small></div> },
    { title: '耗时', dataIndex: 'duration_ms', width: 90, render: value => value == null ? '—' : value < 1000 ? `${value.toFixed(0)} ms` : `${(value / 1000).toFixed(2)} s` },
    { title: '状态', dataIndex: 'status', width: 108, render: value => <Tag color={value === 'failed' ? 'red' : value === 'complete' ? 'green' : 'default'}>{states[value] || value}</Tag> },
  ];
  return <>
    {error && <Alert type="error" title={error} description="已有数据保留，可刷新重试。" />}
    {changed && <Alert className="update-banner" type="info" title={`运行记录有更新${data.total_records > snapshot.total_records ? ` · 新增 ${data.total_records - snapshot.total_records} 条原始事件` : ''}`}
      action={<Button size="small" onClick={() => setSnapshot(data)}>载入更新</Button>} description="当前页与查看位置保持不变。切换页码或筛选会读取最新记录。" />}
    {snapshot?.warnings?.length > 0 && <Alert type="warning" title={`${snapshot.warnings.length} 条采集提示`} description={snapshot.warnings.join('\n')} />}
    <Table className="call-table" rowKey="id" columns={columns} dataSource={snapshot?.items || []} loading={!snapshot && !error}
      pagination={false} size="middle" scroll={{ x: 820, y: 'max(260px, calc(100vh - 520px))' }} locale={{ emptyText: '当前条件下没有交互记录；可调整筛选或等待采集。' }} />
    <div className="call-pagination"><Pagination current={page} pageSize={size} total={snapshot?.total || 0} showSizeChanger showQuickJumper
      pageSizeOptions={[10, 20, 50, 100]} showTotal={(total, range) => `第 ${range[0]}–${range[1]} 条，共 ${total} 次交互`}
      onChange={onPage} /></div>
  </>;
}

export default function RawRunView({ run, revision }) {
  const [page, setPage] = useState(1), [size, setSize] = useState(20), [live, setLive] = useState(true);
  const [kinds, setKinds] = useState(primary), [query, setQuery] = useState(''), [input, setInput] = useState('');
  const [status, setStatus] = useState(''), [dates, setDates] = useState(null), [selected, setSelected] = useState(null);
  const [facets, setFacets] = useState(null), [refresh, setRefresh] = useState(0);
  const params = new URLSearchParams({ page, page_size: size, kinds: kinds.join(','), q: query, input_id: input, status });
  if (dates?.[0]) params.set('start', dates[0].toISOString());
  if (dates?.[1]) params.set('end', dates[1].toISOString());
  const url = `/api/observe/runs/${run}/interactions?${params}`;
  const reset = setter => value => { setter(value); setPage(1); };
  return <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: '#244d3d', borderRadius: 6, fontSize: 13 }, components: { Table: { cellPaddingBlock: 12 } } }}>
    <section className="interaction-timeline">
      <div className="interaction-heading"><div><h2>交互时间线</h2><p>从 Case 到模型、工具与提交，按记录中的时间和 ID 追踪数据。</p></div>
        <Space><span>检测更新</span><Switch checked={live} onChange={setLive} aria-label="检测实时更新" /><Button onClick={() => setRefresh(r => r + 1)}>刷新</Button></Space></div>
      <div className="interaction-counts"><span>{facets?.total_interactions ?? '—'} 次交互</span><span>来自 {facets?.total_records ?? '—'} 条原始事件</span>
        <span>本地时区 · 按时间正序 · 流式片段按 call_id 聚合</span></div>
      <Space className="interaction-presets" wrap>
        <Button size="small" onClick={() => { setKinds(primary); setPage(1); }}>主要交互</Button>
        {['chat', 'tool', 'http', 'sdk', 'submission'].map(kind => <Button size="small" key={kind}
          type={kinds.length === 1 && kinds[0] === kind ? 'primary' : 'default'}
          onClick={() => { setKinds([kind]); setPage(1); }}>{labels[kind]} · {facets?.kinds?.[kind] || 0}</Button>)}
      </Space>
      <div className="interaction-filters">
        <Input.Search allowClear placeholder="搜索消息、JSON、工具或 ID" onSearch={reset(setQuery)} aria-label="搜索交互" />
        <Select mode="multiple" allowClear value={kinds} onChange={reset(setKinds)} maxTagCount="responsive" placeholder="全部交互类型" aria-label="交互类型"
          options={[...new Set([...Object.keys(facets?.kinds || {}), ...primary, 'callback', 'tool_call'])].map(value => ({ value, label: labels[value] || value }))} />
        <Select allowClear value={input || undefined} onChange={reset(v => setInput(v || ''))} placeholder="全部 Input" aria-label="选择 Input"
          options={(facets?.inputs || []).filter(i => i.input_id).map(i => ({ value: i.input_id, label: i.input_id }))} />
        <Select allowClear value={status || undefined} onChange={reset(v => setStatus(v || ''))} placeholder="全部状态" aria-label="交互状态"
          options={Object.entries(states).map(([value, label]) => ({ value, label }))} />
        <DatePicker.RangePicker showTime onChange={reset(setDates)} placeholder={['开始时间', '结束时间']} />
        <Button onClick={() => { setKinds([]); setPage(1); }}>包括所有回调</Button>
      </div>
      <Page key={`${url}:${refresh}`} url={url} revision={revision} live={live} page={page} size={size} onFacets={setFacets}
        onPage={(p, s) => { setPage(size === s ? p : 1); setSize(s); }} onSelect={setSelected} />
      <Drawer className="interaction-drawer" title="交互详情" open={Boolean(selected)} size="large" onClose={() => setSelected(null)} destroyOnHidden>
        {selected && <InteractionDetails key={selected} run={run} id={selected} revision={revision} live={live} onNavigate={setSelected} />}
      </Drawer>
    </section>
  </ConfigProvider>;
}
